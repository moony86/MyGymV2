"""
Generator Service (V9)
=========================================================
جديد بهذي النسخة:
1. template_id اختياري: المستخدم يقدر يختار القالب يدويًا. لو اختاره
   وهو غير مناسب لمستواه/هدفه، يُسجَّل تحذير صريح بدل ما نرفض أو نتجاهل.
2. إصلاح خلل اختيار القالب التلقائي: كان يختار الأبسط (complexity_index
   الأقل) دائمًا، فـ PPL ما كان يُختار أبدًا رغم دعمه لعدد الأيام. الآن
   يُختار الأقرب لـ supported_days.recommended.
3. program_group_id + day_index: تربط كل خطط الأيام الناتجة من نفس
   استدعاء التوليد تحت "برنامج" أسبوعي واحد، تمهيدًا للـ Evaluator لاحقًا.
"""

import uuid6
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session as DbSession

from src.apis.deps import get_knowledge_provider, get_knowledge_queries
from src.infrastructure.db.models import ExerciseTable, TrainingProfileTable, WorkoutPlanTable
from src.services.planner_service import PlannerService

GOAL_TO_TEMPLATE_SUPPORT = {
    "HYPERTROPHY": "hypertrophy",
    "STRENGTH": "strength",
    "FAT_LOSS": "general_fitness",
    "GENERAL_FITNESS": "general_fitness",
}

GOAL_TO_TRAINING_RULES = {
    "HYPERTROPHY": "hypertrophy",
    "STRENGTH": "strength",
    "FAT_LOSS": "hypertrophy",
    "GENERAL_FITNESS": "hypertrophy",
}

MAX_EXERCISES_PER_DAY = 8


class NoSuitableTemplateError(Exception):
    pass


class GeneratorService:
    def __init__(self, db: DbSession):
        self.db = db
        self.provider = get_knowledge_provider()
        self.queries = get_knowledge_queries()
        self.planner = PlannerService(db)
        self.warnings: List[str] = []

    # ------------------------------------------------------------------
    def generate_plan_for_profile(
        self, profile: TrainingProfileTable, template_id: Optional[str] = None
    ) -> List[WorkoutPlanTable]:
        self.warnings = []
        template = self._resolve_template(profile, template_id)

        days_to_generate = profile.training_days_per_week
        program_group_id = str(uuid6.uuid7())  # يربط كل خطط هذا الاستدعاء ببعض
        created_plans = []

        for day_num in range(1, days_to_generate + 1):
            day_name = f"اليوم {day_num}"

            plan = self.planner.create_plan(
                name=f"{template.name} - {day_name}",
                description=f"جدول {day_name} ضمن برنامج {template.name} ({days_to_generate} أيام/أسبوع)",
            )
            # ربط الخطة بمجموعة البرنامج + ترتيبها (نفس السطر يشتغل حتى لو
            # planner.create_plan ما يعرف عن هذين العمودين أصلًا)
            plan.program_group_id = program_group_id
            plan.day_index = day_num

            day_exercises = self._select_exercises_for_day(profile, template, day_num)

            for order_idx, (exercise, variant, exercise_row, sets, reps) in enumerate(day_exercises):
                self.planner.add_exercise_to_plan(
                    plan_id=plan.id,
                    exercise_id=exercise_row.id,
                    order_index=order_idx,
                    target_sets=sets,
                    target_reps=reps,
                    target_weight_mode="LAST_SESSION",
                )

            created_plans.append(plan)

        self.db.commit()

        if self.warnings:
            print("⚠️ تحذيرات أثناء توليد البرنامج:")
            for w in self.warnings:
                print(f"   - {w}")

        return created_plans

    # ------------------------------------------------------------------
    # اختيار القالب (تلقائي أو يدوي مع تحذير)
    # ------------------------------------------------------------------
    def _resolve_template(self, profile: TrainingProfileTable, template_id: Optional[str]):
        if template_id:
            template = self.provider.template(template_id)
            if not self._template_fits_profile(template, profile):
                self.warnings.append(
                    f"⚠️ اخترت القالب '{template.name}' يدويًا، لكنه غير موصى به لمستواك "
                    f"({profile.experience_level}) أو هدفك ({profile.primary_goal}) أو عدد "
                    f"أيامك ({profile.training_days_per_week}). قد لا يعطي أفضل نتيجة، لكن "
                    f"تم التوليد بناءً على اختيارك."
                )
            return template

        return self._select_best_template(profile)

    def _template_fits_profile(self, template, profile: TrainingProfileTable) -> bool:
        level_key = profile.experience_level.lower()
        support_key = GOAL_TO_TEMPLATE_SUPPORT.get(profile.primary_goal, "general_fitness")
        days = template.supported_days
        return (
            template.experience.get(level_key, False)
            and template.supports.get(support_key, False)
            and days["minimum"] <= profile.training_days_per_week <= days["maximum"]
        )

    def _select_best_template(self, profile: TrainingProfileTable):
        """
        الاختيار التلقائي: من بين القوالب المؤهلة (تدعم المستوى/الهدف/عدد
        الأيام)، يُختار الأقرب لـ supported_days.recommended -- مو الأبسط
        (complexity_index) دائمًا. الاختيار بالـ complexity وحده كان يقصي
        PPL دائمًا (نطاقات الأيام متداخلة مع Upper/Lower وFull Body، وPPL
        عنده أعلى complexity فيخسر دائمًا رغم كونه الأنسب لعدد أيام أعلى).
        """
        level_key = profile.experience_level.lower()
        support_key = GOAL_TO_TEMPLATE_SUPPORT.get(profile.primary_goal, "general_fitness")

        candidates = [
            t for t in self.queries.get_templates_for_days(profile.training_days_per_week)
            if t.experience.get(level_key) and t.supports.get(support_key)
        ]
        if not candidates:
            raise NoSuitableTemplateError(
                f"لا يوجد قالب مناسب لـ experience={level_key}, "
                f"days={profile.training_days_per_week}, goal={support_key}"
            )

        candidates.sort(
            key=lambda t: abs(t.supported_days["recommended"] - profile.training_days_per_week)
        )
        return candidates[0]

    # ------------------------------------------------------------------
    # مجموعات العضلات (primary + secondary)
    # ------------------------------------------------------------------
    def _muscle_ids_to_groups(self, muscle_ids) -> set:
        groups = set()
        for muscle_id in muscle_ids or []:
            muscle = self.provider.muscle(muscle_id)
            if muscle and getattr(muscle, "group", None):
                groups.add(muscle.group)
        return groups

    def _exercise_primary_groups(self, exercise) -> set:
        return self._muscle_ids_to_groups(getattr(exercise, "primary_muscles", []))

    def _exercise_secondary_groups(self, exercise) -> set:
        return self._muscle_ids_to_groups(getattr(exercise, "secondary_muscles", []))

    # ------------------------------------------------------------------
    # اختيار تمارين اليوم
    # ------------------------------------------------------------------
    def _select_exercises_for_day(self, profile: TrainingProfileTable, template, day_num: int) -> List[Tuple]:
        gen_rules = self.provider.generator_rules
        training_rules = self.provider.training_rules
        level_key = profile.experience_level.lower()

        variant_rules = gen_rules["variant_selection"].get(level_key, {"allow_all": True})
        avoid_equipment = set(variant_rules.get("avoid", []))
        prefer_order = variant_rules.get("prefer", [])

        rotation_pattern = getattr(template, "rotation_pattern", [])
        target_categories = []
        if rotation_pattern:
            pattern_index = (day_num - 1) % len(rotation_pattern)
            current_slot = rotation_pattern[pattern_index]
            target_categories = current_slot.get("target_categories", [])

        rep_goal_key = GOAL_TO_TRAINING_RULES.get(profile.primary_goal, "hypertrophy")
        all_exercises = self.provider.exercises()

        required_movements = gen_rules.get("movement_selection", {}).get("required", [])
        exercise_limits = gen_rules.get("exercise_limits", {})
        min_per_session = exercise_limits.get("minimum_per_session", 4)
        max_per_session = exercise_limits.get("maximum", MAX_EXERCISES_PER_DAY)

        selected_exercises = self._round_robin_select(all_exercises, target_categories)

        selected_exercises = self._ensure_movement_coverage(
            selected_exercises, all_exercises, required_movements, max_per_session
        )

        if len(selected_exercises) < min_per_session:
            selected_exercises = self._fill_to_minimum(
                selected_exercises, all_exercises, min_per_session, max_per_session
            )

        selected_exercises = selected_exercises[:max_per_session]

        result = []
        for exercise in selected_exercises:
            variant, exercise_row = self._pick_variant_with_linked_row(
                exercise.id, avoid_equipment, prefer_order
            )
            if variant is None or exercise_row is None:
                self.warnings.append(
                    f"اليوم {day_num}: تمرين '{exercise.id}' بدون أي variant مربوط بجدول exercises، تم تجاوزه."
                )
                continue

            sets, reps = self._sets_and_reps(exercise, training_rules, rep_goal_key)
            result.append((exercise, variant, exercise_row, sets, reps))

        return result

    def _ensure_movement_coverage(
        self,
        selected_exercises: list,
        all_exercises: list,
        required_movements: list,
        max_count: int,
    ) -> list:
        covered = {ex.movement_pattern for ex in selected_exercises}
        uncovered = [m for m in required_movements if m not in covered]

        if not uncovered:
            return selected_exercises

        selected_ids = {ex.id for ex in selected_exercises}
        movement_candidates: dict[str, list] = {}
        for ex in all_exercises:
            if ex.id in selected_ids:
                continue
            mp = ex.movement_pattern
            if mp not in movement_candidates:
                movement_candidates[mp] = []
            movement_candidates[mp].append(ex)

        for movement_id in uncovered:
            candidates = movement_candidates.get(movement_id, [])
            for candidate in candidates:
                if len(selected_exercises) >= max_count:
                    last_non_required = None
                    for i, ex in enumerate(selected_exercises):
                        if ex.movement_pattern not in required_movements:
                            last_non_required = i
                            break
                    if last_non_required is not None:
                        removed = selected_exercises[last_non_required]
                        selected_exercises[last_non_required] = candidate
                        selected_ids.discard(removed.id)
                        selected_ids.add(candidate.id)
                        break
                    else:
                        break
                selected_exercises.append(candidate)
                selected_ids.add(candidate.id)
                break

        return selected_exercises

    def _fill_to_minimum(
        self,
        selected_exercises: list,
        all_exercises: list,
        min_count: int,
        max_count: int,
    ) -> list:
        if len(selected_exercises) >= min_count:
            return selected_exercises

        selected_ids = {ex.id for ex in selected_exercises}
        for ex in all_exercises:
            if len(selected_exercises) >= min_count or len(selected_exercises) >= max_count:
                break
            if ex.id in selected_ids:
                continue
            selected_exercises.append(ex)
            selected_ids.add(ex.id)

        return selected_exercises

    def _round_robin_select(self, all_exercises, target_categories: list) -> list:
        if not target_categories:
            seen_patterns, fallback = set(), []
            for ex in all_exercises:
                if ex.movement_pattern not in seen_patterns:
                    fallback.append(ex)
                    seen_patterns.add(ex.movement_pattern)
            fallback.sort(key=lambda e: 0 if getattr(e, "exercise_role", "") == "primary" else 1)
            return fallback[:MAX_EXERCISES_PER_DAY]

        def role_key(e):
            return 0 if getattr(e, "exercise_role", "") == "primary" else 1

        pools = {}
        for cat in target_categories:
            primary_pool = [e for e in all_exercises if cat in self._exercise_primary_groups(e)]
            secondary_pool = [
                e for e in all_exercises
                if cat in self._exercise_secondary_groups(e) and e not in primary_pool
            ]
            primary_pool.sort(key=role_key)
            secondary_pool.sort(key=role_key)
            pools[cat] = primary_pool + secondary_pool

        selected, seen_ids, seen_patterns = [], set(), set()
        cursor = {cat: 0 for cat in target_categories}

        progressed = True
        while len(selected) < MAX_EXERCISES_PER_DAY and progressed:
            progressed = False
            for cat in target_categories:
                pool = pools[cat]
                i = cursor[cat]
                while i < len(pool):
                    candidate = pool[i]
                    i += 1
                    if candidate.id in seen_ids or candidate.movement_pattern in seen_patterns:
                        continue
                    selected.append(candidate)
                    seen_ids.add(candidate.id)
                    seen_patterns.add(candidate.movement_pattern)
                    progressed = True
                    break
                cursor[cat] = i
                if len(selected) >= MAX_EXERCISES_PER_DAY:
                    break

        if not selected:
            selected = all_exercises[:MAX_EXERCISES_PER_DAY]

        return selected

    # ------------------------------------------------------------------
    def _rank_variants(self, exercise_id: str, avoid_equipment: set, prefer_order: list):
        variants = self.queries.get_variants_for_exercise(exercise_id)
        if not variants:
            return []

        preferred = [v for v in variants if v.equipment not in avoid_equipment]
        avoided = [v for v in variants if v.equipment in avoid_equipment]

        def rank(v):
            return prefer_order.index(v.equipment) if v.equipment in prefer_order else len(prefer_order)

        preferred.sort(key=rank)
        avoided.sort(key=rank)
        return preferred + avoided

    def _pick_variant_with_linked_row(self, exercise_id: str, avoid_equipment: set, prefer_order: list):
        for variant in self._rank_variants(exercise_id, avoid_equipment, prefer_order):
            exercise_row = self._get_linked_exercise_row(variant.id)
            if exercise_row is not None:
                return variant, exercise_row
        return None, None

    def _sets_and_reps(self, exercise, training_rules: dict, rep_goal_key: str) -> tuple[int, int]:
        category = "compound" if getattr(exercise, "category", "compound") == "compound" else "isolation"
        sets = training_rules["sets"][category]["recommended"]
        reps_range = training_rules["repetitions"][rep_goal_key]["recommended"]

        if category == "compound":
            reps = reps_range["minimum"] + 1
        else:
            reps = reps_range["maximum"] - 1

        return sets, reps

    def _get_linked_exercise_row(self, variant_id: str) -> Optional[ExerciseTable]:
        return (
            self.db.query(ExerciseTable)
            .filter(ExerciseTable.knowledge_variant_id == variant_id, ExerciseTable.is_active == True)
            .first()
        )
