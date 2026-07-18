import uuid
import uuid6
from decimal import Decimal
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session as DbSession
from sqlalchemy import and_, select, func, or_

from src.infrastructure.db.models import (
    WorkoutPlanTable,
    PlanExerciseTable,
    PlanScheduleTable,
    ExerciseAlternativeTable,
    ExerciseTable,
    SessionTable,
    SetTable,
    PerformedExerciseTable
)
from src.domain.entities import utc_now
from src.services.session_service import SessionService
from src.domain.enums import SessionStatus


class PlannerService:
    def __init__(self, db_session: DbSession):
        self.db = db_session
        self.session_service = SessionService(db_session)

    # ========== إدارة الخطط ==========

    def create_plan(self, name: str, description: Optional[str] = None) -> WorkoutPlanTable:
        plan = WorkoutPlanTable(
            id=str(uuid6.uuid7()),
            name=name,
            description=description,
            created_at=utc_now()
        )
        self.db.add(plan)
        self.db.flush()
        return plan

    def get_all_plans(self, include_disabled: bool = False) -> List[WorkoutPlanTable]:
        query = self.db.query(WorkoutPlanTable)
        if not include_disabled:
            query = query.filter(WorkoutPlanTable.enabled == True)
        return query.order_by(WorkoutPlanTable.name).all()

    def get_plan_by_id(self, plan_id: str) -> Optional[WorkoutPlanTable]:
        return self.db.query(WorkoutPlanTable).filter(WorkoutPlanTable.id == plan_id).first()

    def enable_plan(self, plan_id: str, enabled: bool) -> bool:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return False
        plan.enabled = enabled
        self.db.flush()
        return True

    def delete_plan(self, plan_id: str) -> bool:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return False
        self.db.delete(plan)
        self.db.flush()
        return True

    # ========== إدارة تمارين الخطة ==========

    def add_exercise_to_plan(
        self,
        plan_id: str,
        exercise_id: str,
        order_index: int,
        target_sets: Optional[int] = None,
        target_reps: Optional[int] = None,
        target_weight_mode: str = "LAST_SESSION",
        fixed_weight: Optional[Decimal] = None,
        fixed_reps: Optional[int] = None,
        rest_seconds: Optional[int] = None,
    ) -> PlanExerciseTable:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            raise ValueError("Plan not found")

        exercise = self.db.query(ExerciseTable).filter(
            ExerciseTable.id == exercise_id,
            ExerciseTable.is_active == True
        ).first()
        if not exercise:
            raise ValueError("Exercise not found or inactive")

        # التحقق من عدم التكرار
        existing = self.db.query(PlanExerciseTable).filter(
            PlanExerciseTable.plan_id == plan_id,
            PlanExerciseTable.exercise_id == exercise_id
        ).first()
        if existing:
            raise ValueError("Exercise already exists in this plan")

        pe = PlanExerciseTable(
            id=str(uuid6.uuid7()),
            plan_id=plan_id,
            exercise_id=exercise_id,
            order_index=order_index,
            target_sets=target_sets,
            target_reps=target_reps,
            target_weight_mode=target_weight_mode,
            fixed_weight=fixed_weight,
            fixed_reps=fixed_reps,
            rest_seconds=rest_seconds,
        )
        self.db.add(pe)
        self.db.flush()
        return pe

    def remove_exercise_from_plan(self, plan_exercise_id: str) -> bool:
        pe = self.db.query(PlanExerciseTable).filter(
            PlanExerciseTable.id == plan_exercise_id
        ).first()
        if not pe:
            return False
        self.db.delete(pe)
        self.db.flush()
        return True

    def update_exercise_order(self, plan_exercise_id: str, new_order: int) -> bool:
        pe = self.db.query(PlanExerciseTable).filter(
            PlanExerciseTable.id == plan_exercise_id
        ).first()
        if not pe:
            return False
        pe.order_index = new_order
        self.db.flush()
        return True

    def get_plan_exercises(self, plan_id: str) -> List[PlanExerciseTable]:
        return self.db.query(PlanExerciseTable).filter(
            PlanExerciseTable.plan_id == plan_id
        ).order_by(PlanExerciseTable.order_index).all()

    def get_plan_with_details(self, plan_id: str) -> Dict[str, Any]:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return {}
        exercises = self.get_plan_exercises(plan_id)
        # جلب أسماء التمارين
        exercise_ids = [pe.exercise_id for pe in exercises]
        exercise_names = {}
        if exercise_ids:
            exs = self.db.query(ExerciseTable).filter(ExerciseTable.id.in_(exercise_ids)).all()
            exercise_names = {ex.id: ex.name for ex in exs}
        return {
            "plan": plan,
            "exercises": exercises,
            "exercise_names": exercise_names,
        }

    # ========== الجدولة ==========

    def add_schedule(
        self,
        plan_id: str,
        schedule_type: str = "manual",
        interval_days: Optional[int] = None,
        days_mask: Optional[int] = None,
    ) -> PlanScheduleTable:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            raise ValueError("Plan not found")
        schedule = PlanScheduleTable(
            id=str(uuid6.uuid7()),
            plan_id=plan_id,
            schedule_type=schedule_type,
            interval_days=interval_days,
            days_mask=days_mask,
        )
        self.db.add(schedule)
        self.db.flush()
        return schedule

    def get_today_plan(self) -> Optional[Dict[str, Any]]:
        """
        تعيد الخطة المناسبة لليوم الحالي بناءً على الجدولة.
        إذا لم توجد خطة مجدولة، ترجع None.
        """
        today = date.today()
        weekday = today.isoweekday()  # 1=Monday, 7=Sunday

        # 1. نبحث عن خطط نشطة
        active_plans = self.db.query(WorkoutPlanTable).filter(
            WorkoutPlanTable.enabled == True
        ).all()

        for plan in active_plans:
            schedules = self.db.query(PlanScheduleTable).filter(
                PlanScheduleTable.plan_id == plan.id
            ).all()

            for sched in schedules:
                if sched.schedule_type == "weekly":
                    # days_mask: bitmask, مثلاً الأحد=1, الاثنين=2, الثلاثاء=4, ...
                    if sched.days_mask is not None:
                        # نتحقق من اليوم الحالي
                        if (sched.days_mask & (1 << (weekday - 1))) != 0:
                            return self.get_plan_with_details(plan.id)
                elif sched.schedule_type == "interval":
                    # لا نطبقها حالياً، لكن يمكن حسابها بناءً على تاريخ آخر استخدام
                    # (سنضيفها لاحقاً)
                    pass
                elif sched.schedule_type == "manual":
                    # لا تظهر تلقائياً، بل يدوياً من القائمة
                    pass
        return None

    # ========== إدارة البدائل ==========

    def add_alternative(self, exercise_id: str, alternative_exercise_id: str) -> ExerciseAlternativeTable:
        # التحقق من وجود التمرينين
        ex1 = self.db.query(ExerciseTable).filter(ExerciseTable.id == exercise_id).first()
        ex2 = self.db.query(ExerciseTable).filter(ExerciseTable.id == alternative_exercise_id).first()
        if not ex1 or not ex2:
            raise ValueError("One or both exercises not found")

        # التحقق من عدم التكرار
        existing = self.db.query(ExerciseAlternativeTable).filter(
            ExerciseAlternativeTable.exercise_id == exercise_id,
            ExerciseAlternativeTable.alternative_exercise_id == alternative_exercise_id
        ).first()
        if existing:
            raise ValueError("Alternative already exists")

        alt = ExerciseAlternativeTable(
            id=str(uuid6.uuid7()),
            exercise_id=exercise_id,
            alternative_exercise_id=alternative_exercise_id,
        )
        self.db.add(alt)
        self.db.flush()
        return alt

    def get_alternatives(self, exercise_id: str) -> List[ExerciseAlternativeTable]:
        return self.db.query(ExerciseAlternativeTable).filter(
            ExerciseAlternativeTable.exercise_id == exercise_id
        ).all()

    def remove_alternative(self, alternative_id: str) -> bool:
        alt = self.db.query(ExerciseAlternativeTable).filter(
            ExerciseAlternativeTable.id == alternative_id
        ).first()
        if not alt:
            return False
        self.db.delete(alt)
        self.db.flush()
        return True

    # ========== تنفيذ الخطة (ربط مع V1) ==========

    def start_planned_session(self, plan_id: str, notes: Optional[str] = None) -> Dict[str, Any]:
        """
        1. إنشاء جلسة جديدة عبر SessionService.
        2. إضافة تمارين PerformedExercise حسب ترتيب الخطة.
        3. إرجاع الجلسة وقائمة التمارين المخططة.
        """
        plan_data = self.get_plan_with_details(plan_id)
        if not plan_data:
            raise ValueError("Plan not found or empty")

        # 1. إنشاء جلسة فارغة
        session = self.session_service.create_session(
            notes=notes,
            plan_id=plan_id
        )

        # 2. إضافة تمارين PerformedExercise بالترتيب
        exercises = plan_data["exercises"]
        for idx, pe in enumerate(exercises):
            performed = PerformedExerciseTable(
                id=str(uuid6.uuid7()),
                session_id=str(session.id),
                exercise_id=str(pe.exercise_id),
                display_order=idx,
                notes=f"From plan: {plan_data['plan'].name}"
            )
            self.db.add(performed)
            self.db.flush()

        self.db.commit()

        # 3. تحضير قائمة التمارين المخططة للـ UI
        planned_exercises = []
        for idx, pe in enumerate(exercises):
            # جلب آخر مجموعة لهذا التمرين من تاريخ الجلسات المكتملة
            last_set = self._get_last_set_for_exercise(pe.exercise_id)
            suggestion = self._get_suggestion(
                pe.exercise_id,
                pe.target_weight_mode,
                pe.fixed_weight,
                pe.fixed_reps
            )
            planned_exercises.append({
                "plan_exercise_id": pe.id,
                "exercise_id": pe.exercise_id,
                "name": plan_data["exercise_names"].get(pe.exercise_id, "Unknown"),
                "order": idx,
                "target_sets": pe.target_sets,
                "target_reps": pe.target_reps,
                "suggested_weight": suggestion["weight"],
                "suggested_reps": suggestion["reps"],
                "rest_seconds": pe.rest_seconds,
                "is_completed": False,
            })

        return {
            "session_id": str(session.id),
            "planned_exercises": planned_exercises,
        }

    def get_session_plan_progress(self, session_id: str) -> Dict[str, Any]:
        """
        ترجع تفاصيل الخطة المرتبطة بجلسة نشطة (أو أي جلسة)، مع حالة إنجاز
        كل تمرين محسوبة من الـ Sets المسجلة فعلياً في هذه الجلسة.
        تُستخدم لاستئناف جلسة مخططة بعد تحديث الصفحة / إغلاق التطبيق دون
        فقدان تقدم المستخدم.
        """
        session = self.db.query(SessionTable).filter(SessionTable.id == session_id).first()
        if not session:
            raise ValueError("Session not found")
        if not session.plan_id:
            raise ValueError("This session is not linked to any plan")

        plan_data = self.get_plan_with_details(session.plan_id)
        if not plan_data:
            raise ValueError("Plan not found")

        # التمارين التي سُجلت لها مجموعة واحدة على الأقل ضمن هذه الجلسة
        completed_exercise_ids = set(
            row[0] for row in (
                self.db.query(PerformedExerciseTable.exercise_id)
                .join(SetTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
                .filter(PerformedExerciseTable.session_id == session_id)
                .distinct()
                .all()
            )
        )

        exercises = plan_data["exercises"]
        planned_exercises = []
        for idx, pe in enumerate(exercises):
            is_completed = pe.exercise_id in completed_exercise_ids
            suggestion = self._get_suggestion(
                pe.exercise_id,
                pe.target_weight_mode,
                pe.fixed_weight,
                pe.fixed_reps
            )
            planned_exercises.append({
                "plan_exercise_id": pe.id,
                "exercise_id": pe.exercise_id,
                "name": plan_data["exercise_names"].get(pe.exercise_id, "Unknown"),
                "order": idx,
                "target_sets": pe.target_sets,
                "target_reps": pe.target_reps,
                "suggested_weight": suggestion["weight"],
                "suggested_reps": suggestion["reps"],
                "rest_seconds": pe.rest_seconds,
                "is_completed": is_completed,
            })

        return {
            "session_id": session_id,
            "planned_exercises": planned_exercises,
        }

    def _get_last_set_for_exercise(self, exercise_id: str):
        """ترجع آخر مجموعة مسجلة لهذا التمرين من جلسة مكتملة."""
        subquery = (
            select(PerformedExerciseTable.session_id)
            .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
            .where(
                and_(
                    PerformedExerciseTable.exercise_id == exercise_id,
                    SessionTable.status == SessionStatus.COMPLETED.value
                )
            )
            .order_by(SessionTable.ended_at.desc())
            .limit(1)
        )
        last_set = (
            self.db.query(SetTable)
            .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
            .where(PerformedExerciseTable.session_id.in_(subquery))
            .order_by(SetTable.set_order.desc())
            .limit(1)
        ).first()
        return last_set

    def _get_suggestion(self, exercise_id: str, mode: str, fixed_weight: Optional[Decimal] = None, fixed_reps: Optional[int] = None):
        if mode == "FIXED":
            return {"weight": fixed_weight, "reps": fixed_reps}
        elif mode == "LAST_SESSION":
            last_set = self._get_last_set_for_exercise(exercise_id)
            if last_set:
                return {"weight": last_set.weight, "reps": last_set.reps}
            else:
                return {"weight": None, "reps": None}
        else:  # EMPTY
            return {"weight": None, "reps": None}

    # ========== استعلامات متقدمة ==========

    def get_plan_history(self, plan_id: str, limit: int = 20):
        """ترجع قائمة الجلسات التي تمت باستخدام هذه الخطة."""
        plan_exercises = self.get_plan_exercises(plan_id)
        exercise_ids = [pe.exercise_id for pe in plan_exercises]
        if not exercise_ids:
            return []

        subquery = (
            select(PerformedExerciseTable.session_id)
            .where(PerformedExerciseTable.exercise_id.in_(exercise_ids))
        )
        sessions = (
            self.db.query(SessionTable)
            .filter(SessionTable.id.in_(subquery))
            .order_by(SessionTable.started_at.desc())
            .limit(limit)
            .all()
        )
        return sessions
