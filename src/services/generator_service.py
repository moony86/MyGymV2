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
    def generate_plan_for_profile(self, profile, template_id=None):
        import json
        from src.services.generator_selection import prescription,minutes,VERSION
        from src.infrastructure.db.models import PlanOptionsTable
        self.warnings=[];self.report={}
        self.planner=PlannerService(self.db,profile_id=profile.id)
        from src.services.coaching import preferences
        from types import SimpleNamespace
        self.coaching_preferences=preferences(self.db,profile.id)
        if self.coaching_preferences:
            choices=self.coaching_preferences
            if choices['has_restrictions'] and not choices['avoid_movements']:raise ValueError('Specify restricted movements with your qualified professional before automatic generation')
            if choices['recent_training'] in ['new','returning'] or choices['technique_confidence']=='learning' or choices['recent_sessions']<4:
                profile=SimpleNamespace(id=profile.id,experience_level='BEGINNER',training_days_per_week=profile.training_days_per_week,primary_goal=profile.primary_goal,session_duration_minutes=profile.session_duration_minutes)
        template=self._resolve_template(profile,template_id)
        days=int(profile.training_days_per_week)
        preferred=(self.coaching_preferences or {}).get("preferred_days",[])
        if preferred and len(preferred)!=days:raise ValueError("Update preferred weekdays after changing training days")
        if profile.experience_level=='BEGINNER' and days>4:self.warnings.append('beginner_high_frequency_review_recovery')
        if template.id=='template.upper_lower' and days%2:self.warnings.append('odd_upper_lower_cycle_is_asymmetric')
        # Resolve all days before writing any plan: missing catalogue cannot leave empty days.
        selections=[self._select_exercises_for_day(profile,template,day) for day in range(1,days+1)]
        if any(not items for items in selections):raise ValueError('Cannot generate an empty training day')
        group=str(uuid6.uuid7());plans=[];reports=[]
        for index,items in enumerate(selections,1):
            plan=self.planner.create_plan(name=f'{template.name} - \u0627\u0644\u064a\u0648\u0645 {index}',description=f'برنامج مبدئي من {days} أيام؛ راجع التمارين واختر أوزانًا مناسبة.')
            plan.program_group_id=group;plan.day_index=index
            for order,(exercise,variant,row,sets,reps) in enumerate(items):
                self.planner.add_exercise_to_plan(plan_id=plan.id,exercise_id=row.id,order_index=order,target_sets=sets,target_reps=reps,target_weight_mode='LAST_SESSION',rest_seconds=prescription(profile,exercise)[2])
            report=dict(day=index,plan_id=plan.id,estimated_minutes=minutes(items,profile),time_budget_minutes=min(90,profile.session_duration_minutes),working_sets=sum(item[3] for item in items),movements=[item[0].movement_pattern for item in items],method_version=VERSION)
            schedules=[]
            preferred=(self.coaching_preferences or {}).get('preferred_days',[])
            if preferred:
                if len(preferred)!=days:raise ValueError('Update preferred weekdays after changing training days')
                schedules=[dict(schedule_type='weekly',days_of_week=[sorted(preferred)[index-1]])]
            self.db.add(PlanOptionsTable(plan_id=plan.id,payload=json.dumps(dict(alternatives={},schedules=schedules,generation=report))))
            reports.append(report);plans.append(plan)
        if self.coaching_preferences:
            from src.infrastructure.db.models import CoachingProfileTable
            preference_row=self.db.get(CoachingProfileTable,profile.id)
            updated=json.loads(preference_row.payload);updated['active_program_group_id']=group;preference_row.payload=json.dumps(updated)
        self.db.flush()
        self.report=dict(method_version=VERSION,program_group_id=group,template_id=template.id,days=reports,warnings=list(dict.fromkeys(self.warnings)),schedule_assigned=bool((self.coaching_preferences or {}).get("preferred_days")),assumptions=dict(warmup_minutes=7,setup_minutes_per_exercise=2,seconds_per_set=45,maximum_planning_minutes=90))
        self.db.commit()
        return plans

    def _resolve_template(self, profile: TrainingProfileTable, template_id: Optional[str]):
        if template_id:
            try:template = self.provider.template(template_id)
            except (KeyError,ValueError):raise ValueError('Unknown training template')
            if not template.supported_days['minimum'] <= profile.training_days_per_week <= template.supported_days['maximum']:
                raise ValueError('Requested days are outside the selected template range')
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
        """يُرجع union من: muscle IDs الخام + groups المحوّلة.
        هذا يسمح لـ target_categories باستخدام IDs مباشرة (مثل muscle.calves)."""
        raw = set(getattr(exercise, "primary_muscles", []) or [])
        groups = self._muscle_ids_to_groups(list(raw))
        return raw | groups

    def _exercise_secondary_groups(self, exercise) -> set:
        raw = set(getattr(exercise, "secondary_muscles", []) or [])
        groups = self._muscle_ids_to_groups(list(raw))
        return raw | groups

    # ------------------------------------------------------------------
    # اختيار تمارين اليوم
    # ------------------------------------------------------------------
    def _select_exercises_for_day(self, profile, template, day_num):
        from src.services.generator_selection import select_day
        return select_day(self,profile,template,day_num)

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

    def _balance_session(
        self, selected: list, all_exercises: list,
        target_categories: list, max_count: int,
        is_full_body: bool = True
    ) -> list:
        """إعادة توازن الجلسة:
        - حد أقصى 1 لكل: chest, back, shoulders, legs
        - ضمان وجود calves و abs في كل جلسة
        - ضمان تنوع movement_pattern
        """
        # خريطة: muscle.chest.middle -> chest
        # خذ الجزء الثاني من الـ ID بعد "muscle."
        CAT_MAP = {
            # upper
            'chest': 'chest',
            'lats': 'back', 'upper_back': 'back', 'lower_back': 'back', 'traps': 'back',
            'front_delts': 'shoulders', 'side_delts': 'shoulders', 'rear_delts': 'shoulders',
            'biceps': 'biceps',
            'triceps': 'triceps',
            'forearms': 'forearms',
            # lower
            'quads': 'quads',
            'hamstrings': 'hamstrings',
            'glutes': 'glutes',
            'adductors': 'adductors',
            'calves': 'calves',
            # core
            'abs': 'abs', 'obliques': 'abs', 'transverse_abdominis': 'abs',
        }
        # ═══ حدود ديناميكية حسب نوع اليوم ═══
        if is_full_body:
            # Full Body: 1 لكل عضلة
            MAX_PER_CAT = {
                'chest': 1, 'back': 1, 'shoulders': 1,
                'biceps': 1, 'triceps': 1, 'forearms': 1,
                'quads': 1, 'hamstrings': 1, 'glutes': 1, 'adductors': 1, 'calves': 1,
                'abs': 1,
            }
        else:
            # Split (Upper/Lower/PPL): اسمح بـ 2 للعضلات الكبيرة
            MAX_PER_CAT = {
                'chest': 2, 'back': 2, 'shoulders': 2,
                'biceps': 1, 'triceps': 1, 'forearms': 1,
                'quads': 2, 'hamstrings': 2, 'glutes': 2, 'adductors': 1, 'calves': 1,
                'abs': 1,
            }
        DEFAULT_MAX = 1

        def get_cat(ex):
            """حدد الفئة من primary_muscles (list)."""
            pms = getattr(ex, 'primary_muscles', []) or []
            if not pms:
                return 'other'
            # خذ أول عضلة: "muscle.chest.middle" -> "chest"
            first = pms[0]
            parts = first.split('.')
            # parts = ['muscle', 'chest', 'middle']
            key = parts[1] if len(parts) >= 2 else first
            return CAT_MAP.get(key, 'other')

        # ═══ بناء قائمة CATs مسموحة من target_categories (لأيام Split) ═══
        allowed_cats = set()
        LEG_CATS = {'quads', 'hamstrings', 'glutes', 'adductors'}
        if not is_full_body:
            for tc in (target_categories or []):
                parts = tc.split('.')
                if len(parts) < 2:
                    continue
                if parts[0] == 'muscle':
                    c = CAT_MAP.get(parts[1])
                    if c:
                        allowed_cats.add(c)
                elif parts[0] == 'group':
                    g = parts[1]
                    if g == 'chest':
                        allowed_cats.add('chest')
                    elif g == 'back':
                        allowed_cats.add('back')
                    elif g == 'shoulders':
                        allowed_cats.add('shoulders')
                    elif g == 'arms':
                        allowed_cats.update(['biceps', 'triceps', 'forearms'])
                    elif g == 'legs':
                        allowed_cats.update(LEG_CATS | {'calves'})
                    elif g == 'core':
                        allowed_cats.add('abs')
            # توسيع فئات الأرجل
            if allowed_cats & LEG_CATS:
                allowed_cats.update(LEG_CATS)

        cat_count = {}
        seen_patterns = set()
        balanced = []

        for ex in selected:
            cat = get_cat(ex)

            # فلتر Split: تجاهل الفئات غير المسموحة
            if not is_full_body and allowed_cats and cat != 'other' and cat not in allowed_cats:
                continue
            limit = MAX_PER_CAT.get(cat, DEFAULT_MAX)
            current = cat_count.get(cat, 0)
            pattern = getattr(ex, 'movement_pattern', '') or ''

            # في Split — امنع تكرار hamstrings/quads في نفس اليوم
            skip = False
            if not is_full_body and cat in ('quads', 'hamstrings', 'glutes'):
                # احسب كم leg exercise موجود
                leg_count = sum(cat_count.get(k, 0) for k in ('quads', 'hamstrings', 'glutes'))
                if leg_count >= 2:
                    skip = True

            if not skip and current < limit and pattern not in seen_patterns:
                balanced.append(ex)
                cat_count[cat] = current + 1
                if pattern:
                    seen_patterns.add(pattern)

        # ضمان calves + abs (فقط لأيام Full Body أو Lower)
        leg_cats = {'group.legs', 'muscle.quads', 'muscle.hamstrings',
                    'muscle.glutes', 'muscle.adductors', 'muscle.calves'}
        has_lower = is_full_body or bool(leg_cats & set(target_categories or []))
        if has_lower:
            for req in ['calves', 'abs']:
                if cat_count.get(req, 0) == 0:
                    for ex in all_exercises:
                        if get_cat(ex) == req:
                            pattern = getattr(ex, 'movement_pattern', '') or ''
                            if pattern not in seen_patterns:
                                balanced.append(ex)
                                cat_count[req] = 1
                                if pattern:
                                    seen_patterns.add(pattern)
                                break

        return balanced[:max_count]

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

    def _round_robin_select(self, all_exercises, target_categories: list, max_count: int = None) -> list:
        if not target_categories:
            seen_patterns, fallback = set(), []
            for ex in all_exercises:
                if ex.movement_pattern not in seen_patterns:
                    fallback.append(ex)
                    seen_patterns.add(ex.movement_pattern)
            fallback.sort(key=lambda e: 0 if getattr(e, "exercise_role", "") == "primary" else 1)
            return fallback[:(max_count or MAX_EXERCISES_PER_DAY)]

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
