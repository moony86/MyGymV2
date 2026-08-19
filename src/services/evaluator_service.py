"""
Evaluator Service
==================
يحسب الحجم التدريبي الأسبوعي الفعلي (working sets) لكل عضلة عبر كل
أيام برنامج واحد (program_group_id)، ويقارنه بـ weekly_volume من
training_rules.yaml لمعرفة هل البرنامج يغطي احتياج المستخدم فعليًا.

منهجية الوزن (قرار تصميم صريح، موثّق هنا لأنه أهم افتراض بالحساب):
    - عضلة أساسية (primary_muscles)   -> تُحسب set كاملة (وزن 1.0)
    - عضلة ثانوية (secondary_muscles) -> تُحسب نص set (وزن 0.5)
      لأن التحفيز على العضلة الثانوية أقل من العضلة المستهدفة مباشرة
      (مثال: Overhead Press يبني الكتف (primary) ويحفّز الترايسبس
      (secondary) لكن بدرجة أقل من تمرين ترايسبس مباشر).

الاستخدام:
    evaluator = EvaluatorService(db)
    report = evaluator.evaluate_program(program_group_id, profile)
"""

from collections import defaultdict
from typing import Optional
from sqlalchemy.orm import Session as DbSession

from src.apis.deps import get_knowledge_provider
from src.infrastructure.db.models import ExerciseTable, PlanExerciseTable, WorkoutPlanTable, TrainingProfileTable

SECONDARY_MUSCLE_WEIGHT = 0.5

GOAL_TO_TRAINING_RULES = {
    "HYPERTROPHY": "hypertrophy",
    "STRENGTH": "strength",
    "FAT_LOSS": "hypertrophy",
    "GENERAL_FITNESS": "hypertrophy",
}


class ProgramNotFoundError(Exception):
    pass


class EvaluatorService:
    def __init__(self, db: DbSession):
        self.db = db
        self.provider = get_knowledge_provider()

    # ------------------------------------------------------------------
    def evaluate_program(self, program_group_id: str, profile: TrainingProfileTable) -> dict:
        plans = (
            self.db.query(WorkoutPlanTable)
            .filter(WorkoutPlanTable.program_group_id == program_group_id)
            .all()
        )
        if not plans:
            raise ProgramNotFoundError(f"لا يوجد برنامج بـ program_group_id={program_group_id}")

        muscle_volume, unresolved = self._collect_muscle_volume(plans)
        group_volume = self._roll_up_to_groups(muscle_volume)

        goal_key = GOAL_TO_TRAINING_RULES.get(profile.primary_goal, "hypertrophy")
        volume_rules = self.provider.training_rules["weekly_volume"][goal_key]
        coverage_rules = self.provider.training_rules["muscle_coverage"]

        major_report = self._build_group_report(
            coverage_rules["major_muscles"], group_volume, volume_rules
        )
        optional_report = self._build_muscle_report(
            coverage_rules["optional_muscles"], muscle_volume, volume_rules
        )

        overall_status = "PASS"
        if any(r["status"] == "below_minimum" for r in major_report):
            overall_status = "FAIL"
        elif any(r["status"] in ("below_minimum", "above_maximum") for r in major_report + optional_report):
            overall_status = "WARNING"

        return {
            "program_group_id": program_group_id,
            "days_count": len(plans),
            "goal": profile.primary_goal,
            "overall_status": overall_status,  # PASS / WARNING / FAIL
            "major_muscles": major_report,
            "optional_muscles": optional_report,
            "unresolved_exercises": unresolved,  # تمارين ما قدرنا نحسبها (بدون ربط معرفي)
        }

    # ------------------------------------------------------------------
    def _collect_muscle_volume(self, plans: list) -> tuple[dict, list]:
        muscle_volume: dict = defaultdict(float)
        unresolved: list = []

        plan_ids = [p.id for p in plans]
        plan_exercises = (
            self.db.query(PlanExerciseTable)
            .filter(PlanExerciseTable.plan_id.in_(plan_ids))
            .all()
        )

        for pe in plan_exercises:
            exercise_row = self.db.query(ExerciseTable).filter(ExerciseTable.id == pe.exercise_id).first()
            if not exercise_row or not exercise_row.knowledge_variant_id:
                unresolved.append(exercise_row.name if exercise_row else pe.exercise_id)
                continue

            variant = self.provider.variant(exercise_row.knowledge_variant_id)
            exercise = self.provider.exercise(variant.exercise)
            sets = pe.target_sets or 0

            for muscle_id in exercise.primary_muscles:
                muscle_volume[muscle_id] += sets * 1.0
            for muscle_id in exercise.secondary_muscles:
                muscle_volume[muscle_id] += sets * SECONDARY_MUSCLE_WEIGHT

        return dict(muscle_volume), unresolved

    def _roll_up_to_groups(self, muscle_volume: dict) -> dict:
        group_volume: dict = defaultdict(float)
        for muscle_id, volume in muscle_volume.items():
            muscle = self.provider.muscle(muscle_id)
            if muscle and getattr(muscle, "group", None):
                group_volume[muscle.group] += volume
        return dict(group_volume)

    # ------------------------------------------------------------------
    def _classify(self, volume: float, rules: dict) -> str:
        if volume < rules["minimum_sets_per_muscle"]:
            return "below_minimum"
        if volume > rules["maximum_sets_per_muscle"]:
            return "above_maximum"
        return "ok"

    def _build_group_report(self, group_ids: list, group_volume: dict, rules: dict) -> list:
        report = []
        for group_id in group_ids:
            volume = round(group_volume.get(group_id, 0.0), 1)
            report.append({
                "id": group_id,
                "weekly_sets": volume,
                "recommended_range": rules["recommended_sets"],
                "status": self._classify(volume, rules),
            })
        return report

    def _build_muscle_report(self, muscle_ids: list, muscle_volume: dict, rules: dict) -> list:
        report = []
        for muscle_id in muscle_ids:
            volume = round(muscle_volume.get(muscle_id, 0.0), 1)
            report.append({
                "id": muscle_id,
                "weekly_sets": volume,
                "recommended_range": rules["recommended_sets"],
                "status": self._classify(volume, rules),
            })
        return report
