"""
Generator Service
==================
يربط TrainingProfileTable بالقاعدة المعرفية (عبر KnowledgeProvider/Queries)
وينتج WorkoutPlanTable فعلية عبر PlannerService الموجود مسبقًا.

MVP الحالي: يولّد خطة واحدة "Full Body-style" (تغطي كل الحركات الأساسية
المطلوبة بـ movement_selection.required في generator_rules.yaml) بغض
النظر عن التقسيم الفعلي للقالب (Upper/Lower أو PPL). توليد عدة خطط
لكل يوم بالتقسيمات المتقدمة هو تحسين لاحق منفصل، مو جزء من هذا الملف.

لكل حركة مطلوبة، يجرب كل الـ variants المتاحة بترتيب الأفضلية (حسب
مستوى المستخدم) لين يلقى وحدة مربوطة فعليًا بجدول exercises، بدل ما
يتوقف عند أول variant ما يلقى له ربط. لو فشلت كل المحاولات لحركة
معيّنة، تُسجَّل كتحذير صريح بـ self.warnings (تُطبع بعد التوليد) بدل
ما تختفي بصمت.

الاستخدام:
    service = GeneratorService(db)
    plan = service.generate_plan_for_profile(profile)
"""

from typing import Optional
from sqlalchemy.orm import Session as DbSession

from src.apis.deps import get_knowledge_provider, get_knowledge_queries
from src.infrastructure.db.models import ExerciseTable, TrainingProfileTable, WorkoutPlanTable
from src.services.planner_service import PlannerService

# هدف البروفايل -> مفتاح القوالب/القواعد بالقاعدة المعرفية
# (لا يوجد fat_loss بالقاعدة المعرفية حاليًا -> نعامله كـ general_fitness)
GOAL_TO_TEMPLATE_SUPPORT = {
    "HYPERTROPHY": "hypertrophy",
    "STRENGTH": "strength",
    "FAT_LOSS": "general_fitness",
    "GENERAL_FITNESS": "general_fitness",
}
# مفتاح training_rules.repetitions/weekly_volume (لا يوجد فيها general_fitness)
GOAL_TO_TRAINING_RULES = {
    "HYPERTROPHY": "hypertrophy",
    "STRENGTH": "strength",
    "FAT_LOSS": "hypertrophy",
    "GENERAL_FITNESS": "hypertrophy",
}


class NoSuitableTemplateError(Exception):
    pass


class GeneratorService:
    def __init__(self, db: DbSession):
        self.db = db
        self.provider = get_knowledge_provider()
        self.queries = get_knowledge_queries()
        self.planner = PlannerService(db)

    # ------------------------------------------------------------------
    def generate_plan_for_profile(self, profile: TrainingProfileTable) -> WorkoutPlanTable:
        template = self._select_template(profile)
        selection = self._select_exercises(profile)  # يملأ self.warnings أيضًا

        plan = self.planner.create_plan(
            name=f"خطة تلقائية - {template.name}",
            description=f"تم توليدها تلقائيًا بناءً على بروفايلك ({template.name}، "
                        f"{profile.training_days_per_week} أيام/أسبوع)",
        )

        for order, (exercise, variant, exercise_row, sets, reps) in enumerate(selection):
            self.planner.add_exercise_to_plan(
                plan_id=plan.id,
                exercise_id=exercise_row.id,
                order_index=order,
                target_sets=sets,
                target_reps=reps,
                target_weight_mode="LAST_SESSION",
            )

        self.db.commit()

        if self.warnings:
            print("⚠️  تحذيرات أثناء توليد الخطة:")
            for w in self.warnings:
                print(f"   - {w}")

        return plan

    # ------------------------------------------------------------------
    # اختيار القالب
    # ------------------------------------------------------------------
    def _select_template(self, profile: TrainingProfileTable):
        level_key = profile.experience_level.lower()
        support_key = GOAL_TO_TEMPLATE_SUPPORT[profile.primary_goal]

        candidates = [
            t for t in self.queries.get_templates_for_days(profile.training_days_per_week)
            if t.experience.get(level_key) and t.supports.get(support_key)
        ]
        if not candidates:
            raise NoSuitableTemplateError(
                f"لا يوجد قالب مناسب لـ experience={level_key}, "
                f"days={profile.training_days_per_week}, goal={support_key}"
            )
        # الأبسط أولًا (complexity_index الأقل) -> أنسب لمبتدئ افتراضيًا
        candidates.sort(key=lambda t: t.complexity_index)
        return candidates[0]

    # ------------------------------------------------------------------
    # اختيار التمارين + الـ variants + sets/reps
    # ------------------------------------------------------------------
    def _select_exercises(self, profile: TrainingProfileTable):
        gen_rules = self.provider.generator_rules
        training_rules = self.provider.training_rules

        level_key = profile.experience_level.lower()
        variant_rules = gen_rules["variant_selection"].get(level_key, {"allow_all": True})
        avoid_equipment = set(variant_rules.get("avoid", []))
        prefer_order = variant_rules.get("prefer", [])

        required_movements = gen_rules["movement_selection"]["required"]
        rep_goal_key = GOAL_TO_TRAINING_RULES[profile.primary_goal]

        self.warnings: list[str] = []  # يُقرأ بعد التوليد لمعرفة أي حركة فشلت فعليًا

        result = []
        for movement_id in required_movements:
            exercise = self._pick_exercise_for_movement(movement_id)
            if exercise is None:
                self.warnings.append(f"لا يوجد تمرين معرّف لحركة '{movement_id}' بالقاعدة المعرفية.")
                continue

            variant, exercise_row = self._pick_variant_with_linked_row(
                exercise.id, avoid_equipment, prefer_order
            )
            if variant is None or exercise_row is None:
                self.warnings.append(
                    f"حركة '{movement_id}' (تمرين '{exercise.id}'): كل الـ variants المتاحة "
                    f"غير مربوطة بأي صف بجدول exercises. راجع matching script."
                )
                continue

            sets, reps = self._sets_and_reps(exercise, training_rules, rep_goal_key)
            result.append((exercise, variant, exercise_row, sets, reps))

        return result

    def _pick_exercise_for_movement(self, movement_id: str):
        candidates = [e for e in self.provider.exercises() if e.movement_pattern == movement_id]
        if not candidates:
            return None
        primary = next((e for e in candidates if e.exercise_role == "primary"), None)
        return primary or candidates[0]

    def _rank_variants(self, exercise_id: str, avoid_equipment: set, prefer_order: list):
        """يرجّع كل الـ variants المتاحة لتمرين معيّن، مرتبة من الأفضل للأسوأ
        حسب قواعد المستوى (تجنّب البار الحر للمبتدئ، تفضيل الآلة/الكيبل...)."""
        variants = self.queries.get_variants_for_exercise(exercise_id)
        if not variants:
            return []

        preferred = [v for v in variants if v.equipment not in avoid_equipment]
        avoided = [v for v in variants if v.equipment in avoid_equipment]

        def rank(v):
            return prefer_order.index(v.equipment) if v.equipment in prefer_order else len(prefer_order)

        preferred.sort(key=rank)
        avoided.sort(key=rank)
        return preferred + avoided  # المفضّل أولًا، ثم المتجنَّب كحل أخير أفضل من ولا شي

    def _pick_variant_with_linked_row(self, exercise_id: str, avoid_equipment: set, prefer_order: list):
        """يجرب كل الـ variants بالترتيب لين يلقى وحدة مربوطة فعليًا بجدول exercises.
        هذا يمنع التخطي الصامت لحركة كاملة بسبب variant واحد غير مربوط، طالما
        فيه بديل آخر لنفس التمرين مربوط."""
        for variant in self._rank_variants(exercise_id, avoid_equipment, prefer_order):
            exercise_row = self._get_linked_exercise_row(variant.id)
            if exercise_row is not None:
                return variant, exercise_row
        return None, None

    def _sets_and_reps(self, exercise, training_rules: dict, rep_goal_key: str) -> tuple[int, int]:
        category = "compound" if exercise.category == "compound" else "isolation"
        sets = training_rules["sets"][category]["recommended"]
        reps_range = training_rules["repetitions"][rep_goal_key]["recommended"]
        reps = round((reps_range["minimum"] + reps_range["maximum"]) / 2)
        return sets, reps

    def _get_linked_exercise_row(self, variant_id: str) -> Optional[ExerciseTable]:
        return (
            self.db.query(ExerciseTable)
            .filter(ExerciseTable.knowledge_variant_id == variant_id, ExerciseTable.is_active == True)
            .first()
        )
