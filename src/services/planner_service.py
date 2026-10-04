from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload

from src.infrastructure.db.models import (
    DEFAULT_PROFILE_ID,
    ExerciseAlternativeTable,
    ExerciseTable,
    PerformedExerciseTable,
    PlanExerciseTable,
    PlanScheduleTable,
    SessionTable,
    SetTable,
    WorkoutPlanTable,
)

logger = logging.getLogger(__name__)


class PlannerService:
    """
    Planner service aligned with the current MyGymV2 V2 database schema.

    The service intentionally uses the fields that actually exist in the DB:
    - WorkoutPlanTable.enabled
    - PlanExerciseTable.order_index
    - target_weight_mode
    - fixed_weight / fixed_reps
    - PlanScheduleTable.schedule_type / interval_days / days_mask
    """

    VALID_WEIGHT_MODES = {
        "LAST_SESSION",
        "FIXED",
        "FIXED_WEIGHT",
        "INCREASE_WEIGHT",
        "INCREASE_REPS",
    }

    def __init__(self, db: Session, profile_id: str = DEFAULT_PROFILE_ID):
        self.db = db
        self.profile_id = profile_id

    # ------------------------------------------------------------------
    # Plans
    # ------------------------------------------------------------------

    def get_all_plans(self, active_only: bool = False) -> List[WorkoutPlanTable]:
        query = self.db.query(WorkoutPlanTable).filter(
            WorkoutPlanTable.profile_id == self.profile_id
        )
        if active_only:
            query = query.filter(WorkoutPlanTable.enabled.is_(True))

        return query.order_by(WorkoutPlanTable.created_at.desc()).all()

    def get_plan_by_id(self, plan_id: str) -> Optional[WorkoutPlanTable]:
        return (
            self.db.query(WorkoutPlanTable)
            .filter(
                WorkoutPlanTable.id == plan_id,
                WorkoutPlanTable.profile_id == self.profile_id,
            )
            .first()
        )

    get_plan = get_plan_by_id

    def create_plan(
        self,
        name: str,
        description: Optional[str] = None,
    ) -> WorkoutPlanTable:
        name = (name or "").strip()
        if not name:
            raise ValueError("Plan name is required")

        plan = WorkoutPlanTable(
            profile_id=self.profile_id,
            name=name,
            description=description,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(plan)
        self.db.flush()
        return plan

    def update_plan(
        self,
        plan_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        exercises: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[WorkoutPlanTable]:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return None

        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("Plan name cannot be empty")
            plan.name = name

        if description is not None:
            plan.description = description

        if exercises is not None:
            plan.plan_exercises.clear()
            self.db.flush()

            for item in exercises:
                self._add_exercise(
                    plan_id=plan.id,
                    exercise_id=item["exercise_id"],
                    order_index=item.get("order_index", 0),
                    target_sets=item.get("target_sets"),
                    target_reps=item.get("target_reps"),
                    target_weight_mode=item.get(
                        "target_weight_mode", "LAST_SESSION"
                    ),
                    fixed_weight=item.get("fixed_weight"),
                    fixed_reps=item.get("fixed_reps"),
                    rest_seconds=item.get("rest_seconds"),
                )

        self.db.flush()
        return plan

    def delete_plan(self, plan_id: str) -> bool:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return False

        self.db.delete(plan)
        self.db.flush()
        return True

    def enable_plan(
        self,
        plan_id: str,
        enabled: bool,
    ) -> Optional[WorkoutPlanTable]:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return None

        plan.enabled = bool(enabled)
        self.db.flush()
        return plan

    # ------------------------------------------------------------------
    # Plan exercises
    # ------------------------------------------------------------------

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
            raise ValueError("Plan not found or access denied")

        return self._add_exercise(
            plan_id=plan.id,
            exercise_id=exercise_id,
            order_index=order_index,
            target_sets=target_sets,
            target_reps=target_reps,
            target_weight_mode=target_weight_mode,
            fixed_weight=fixed_weight,
            fixed_reps=fixed_reps,
            rest_seconds=rest_seconds,
        )

    def _add_exercise(
        self,
        plan_id: str,
        exercise_id: str,
        order_index: int,
        target_sets: Optional[int],
        target_reps: Optional[int],
        target_weight_mode: str,
        fixed_weight: Optional[Decimal],
        fixed_reps: Optional[int],
        rest_seconds: Optional[int],
    ) -> PlanExerciseTable:
        exercise = (
            self.db.query(ExerciseTable)
            .filter(
                ExerciseTable.id == exercise_id,
                ExerciseTable.is_active.is_(True),
            )
            .first()
        )
        if not exercise:
            raise ValueError("Exercise not found or inactive")

        mode = (target_weight_mode or "LAST_SESSION").upper()
        if mode not in self.VALID_WEIGHT_MODES:
            raise ValueError(
                f"Unsupported target_weight_mode: {target_weight_mode}. "
                f"Allowed: {', '.join(sorted(self.VALID_WEIGHT_MODES))}"
            )

        if fixed_weight is not None and fixed_weight < 0:
            raise ValueError("fixed_weight cannot be negative")
        if target_sets is not None and target_sets < 1:
            raise ValueError("target_sets must be >= 1")
        if target_reps is not None and target_reps < 1:
            raise ValueError("target_reps must be >= 1")
        if fixed_reps is not None and fixed_reps < 1:
            raise ValueError("fixed_reps must be >= 1")
        if rest_seconds is not None and rest_seconds < 0:
            raise ValueError("rest_seconds cannot be negative")

        duplicate = (
            self.db.query(PlanExerciseTable)
            .filter(
                PlanExerciseTable.plan_id == plan_id,
                PlanExerciseTable.exercise_id == exercise_id,
            )
            .first()
        )
        if duplicate:
            raise ValueError("Exercise already exists in this plan")

        pe = PlanExerciseTable(
            plan_id=plan_id,
            exercise_id=exercise_id,
            order_index=order_index,
            target_sets=target_sets,
            target_reps=target_reps,
            target_weight_mode=mode,
            fixed_weight=fixed_weight,
            fixed_reps=fixed_reps,
            rest_seconds=rest_seconds,
        )
        self.db.add(pe)
        self.db.flush()
        return pe

    # ------------------------------------------------------------------
    # Details / scheduling
    # ------------------------------------------------------------------

    def get_plan_with_details(self, plan_id: str) -> Dict[str, Any]:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return {}

        exercises = (
            self.db.query(PlanExerciseTable)
            .options(joinedload(PlanExerciseTable.exercise))
            .filter(PlanExerciseTable.plan_id == plan.id)
            .order_by(
                PlanExerciseTable.order_index.asc(),
                PlanExerciseTable.id.asc(),
            )
            .all()
        )

        schedule = (
            self.db.query(PlanScheduleTable)
            .filter(PlanScheduleTable.plan_id == plan.id)
            .order_by(PlanScheduleTable.id.asc())
            .first()
        )

        return {
            "plan": plan,
            "exercises": exercises,
            "exercise_names": {
                pe.exercise_id: (
                    pe.exercise.name if pe.exercise else "Unknown"
                )
                for pe in exercises
            },
            "schedule": schedule,
        }

    def add_schedule(
        self,
        plan_id: str,
        schedule_type: str = "manual",
        interval_days: Optional[int] = None,
        days_mask: Optional[int] = None,
    ) -> PlanScheduleTable:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            raise ValueError("Plan not found or access denied")

        schedule_type = (schedule_type or "manual").lower()
        if schedule_type not in {"manual", "weekly", "interval"}:
            raise ValueError(
                "schedule_type must be manual, weekly, or interval"
            )

        if interval_days is not None and interval_days < 1:
            raise ValueError("interval_days must be >= 1")

        if days_mask is not None and not 0 <= days_mask <= 127:
            raise ValueError("days_mask must be between 0 and 127")

        schedule = PlanScheduleTable(
            plan_id=plan.id,
            schedule_type=schedule_type,
            interval_days=interval_days,
            days_mask=days_mask,
        )
        self.db.add(schedule)
        self.db.flush()
        return schedule

    def get_today_plan(
        self,
        target_date: Optional[date] = None,
    ) -> Optional[Dict[str, Any]]:
        target_date = target_date or date.today()

        # Python weekday: Mon=0 ... Sun=6.
        # Existing API uses Sunday as bit 0, Monday as bit 1, etc.
        day_bit_index = (target_date.weekday() + 1) % 7
        today_mask = 1 << day_bit_index

        plans = (
            self.db.query(WorkoutPlanTable)
            .filter(
                WorkoutPlanTable.profile_id == self.profile_id,
                WorkoutPlanTable.enabled.is_(True),
            )
            .order_by(WorkoutPlanTable.created_at.desc())
            .all()
        )

        for plan in plans:
            schedule = (
                self.db.query(PlanScheduleTable)
                .filter(PlanScheduleTable.plan_id == plan.id)
                .order_by(PlanScheduleTable.id.asc())
                .first()
            )
            if (
                schedule
                and schedule.days_mask is not None
                and (schedule.days_mask & today_mask)
            ):
                return self.get_plan_with_details(plan.id)

        return None

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def start_planned_session(
        self,
        plan_id: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            raise ValueError("Plan not found or access denied")

        if not plan.enabled:
            raise ValueError("Plan is disabled")

        active = (
            self.db.query(SessionTable)
            .filter(
                SessionTable.profile_id == self.profile_id,
                SessionTable.plan_id == plan.id,
                SessionTable.status == "ACTIVE",
            )
            .first()
        )
        if active:
            raise ValueError(
                "An active session already exists for this plan"
            )

        session = SessionTable(
            profile_id=self.profile_id,
            plan_id=plan.id,
            status="ACTIVE",
            started_at=datetime.now(timezone.utc),
            notes=notes,
        )
        self.db.add(session)
        self.db.flush()

        exercises = (
            self.db.query(PlanExerciseTable)
            .options(joinedload(PlanExerciseTable.exercise))
            .filter(PlanExerciseTable.plan_id == plan.id)
            .order_by(
                PlanExerciseTable.order_index.asc(),
                PlanExerciseTable.id.asc(),
            )
            .all()
        )

        last_sets = self._get_bulk_last_sets(
            [pe.exercise_id for pe in exercises]
        )

        planned = []

        for pe in exercises:
            suggestion = self._calculate_suggestion(
                pe,
                last_sets.get(pe.exercise_id),
            )

            performed = PerformedExerciseTable(
                session_id=session.id,
                exercise_id=pe.exercise_id,
                display_order=pe.order_index,
            )
            self.db.add(performed)

            planned.append(
                self._planned_exercise_dict(
                    pe,
                    suggestion,
                    False,
                )
            )

        self.db.flush()

        return {
            "session_id": session.id,
            "planned_exercises": planned,
        }

    def get_session_plan_progress(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        session = (
            self.db.query(SessionTable)
            .filter(
                SessionTable.id == session_id,
                SessionTable.profile_id == self.profile_id,
            )
            .first()
        )

        if not session or not session.plan_id:
            raise ValueError(
                "Session not found or not linked to a plan"
            )

        details = self.get_plan_with_details(session.plan_id)
        if not details:
            raise ValueError(
                "Plan associated with session not found"
            )

        plan_exercises = details["exercises"]

        last_sets = self._get_bulk_last_sets(
            [pe.exercise_id for pe in plan_exercises]
        )

        performed_rows = (
            self.db.query(PerformedExerciseTable)
            .options(joinedload(PerformedExerciseTable.sets))
            .filter(
                PerformedExerciseTable.session_id == session.id
            )
            .all()
        )

        performed_map = {
            pe.exercise_id: pe
            for pe in performed_rows
        }

        planned = []

        for pe in plan_exercises:
            suggestion = self._calculate_suggestion(
                pe,
                last_sets.get(pe.exercise_id),
            )

            performed = performed_map.get(pe.exercise_id)

            completed = bool(
                performed
                and any(
                    getattr(s, "set_type", None) != "WARMUP"
                    for s in (performed.sets or [])
                )
            )

            planned.append(
                self._planned_exercise_dict(
                    pe,
                    suggestion,
                    completed,
                )
            )

        return {
            "session_id": session.id,
            "planned_exercises": planned,
        }

    def _planned_exercise_dict(
        self,
        pe: PlanExerciseTable,
        suggestion: Dict[str, Any],
        is_completed: bool,
    ) -> Dict[str, Any]:
        return {
            "plan_exercise_id": pe.id,
            "exercise_id": pe.exercise_id,
            "name": (
                pe.exercise.name
                if pe.exercise
                else "Unknown"
            ),
            "order": pe.order_index,
            "target_sets": pe.target_sets,
            "target_reps": pe.target_reps,
            "suggested_weight": suggestion["suggested_weight"],
            "suggested_reps": suggestion["suggested_reps"],
            "rest_seconds": pe.rest_seconds,
            "is_completed": is_completed,
        }

    # ------------------------------------------------------------------
    # Progressive overload
    # ------------------------------------------------------------------

    def _get_bulk_last_sets(
        self,
        exercise_ids: List[str],
    ) -> Dict[str, SetTable]:
        if not exercise_ids:
            return {}

        subq = (
            select(
                PerformedExerciseTable.exercise_id.label(
                    "exercise_id"
                ),
                func.max(SessionTable.ended_at).label(
                    "max_ended_at"
                ),
            )
            .join(
                SessionTable,
                PerformedExerciseTable.session_id
                == SessionTable.id,
            )
            .where(
                PerformedExerciseTable.exercise_id.in_(
                    exercise_ids
                ),
                SessionTable.profile_id == self.profile_id,
                SessionTable.status == "COMPLETED",
                SessionTable.ended_at.is_not(None),
            )
            .group_by(
                PerformedExerciseTable.exercise_id
            )
            .subquery()
        )

        rows = (
            self.db.query(
                PerformedExerciseTable.exercise_id,
                SetTable,
            )
            .join(
                SessionTable,
                PerformedExerciseTable.session_id
                == SessionTable.id,
            )
            .join(
                subq,
                and_(
                    subq.c.exercise_id
                    == PerformedExerciseTable.exercise_id,
                    subq.c.max_ended_at
                    == SessionTable.ended_at,
                ),
            )
            .join(
                SetTable,
                SetTable.performed_exercise_id
                == PerformedExerciseTable.id,
            )
            .filter(
                SessionTable.profile_id
                == self.profile_id
            )
            .order_by(SetTable.set_order.desc())
            .all()
        )

        result: Dict[str, SetTable] = {}

        for exercise_id, set_obj in rows:
            result.setdefault(exercise_id, set_obj)

        return result

    def _calculate_suggestion(
        self,
        pe: PlanExerciseTable,
        last_set: Optional[SetTable],
    ) -> Dict[str, Any]:
        mode = (
            pe.target_weight_mode or "LAST_SESSION"
        ).upper()

        target_reps = pe.target_reps

        fixed_reps = pe.fixed_reps

        fixed_weight = (
            Decimal(str(pe.fixed_weight))
            if pe.fixed_weight is not None
            else None
        )

        if mode in {"FIXED", "FIXED_WEIGHT"}:
            return {
                "suggested_weight": fixed_weight,
                "suggested_reps": (
                    fixed_reps
                    if fixed_reps is not None
                    else target_reps
                ),
            }

        if not last_set:
            return {
                "suggested_weight": fixed_weight,
                "suggested_reps": (
                    fixed_reps
                    if fixed_reps is not None
                    else target_reps
                ),
            }

        last_weight = Decimal(str(last_set.weight))
        last_reps = int(last_set.reps)

        if mode == "INCREASE_WEIGHT":
            return {
                "suggested_weight": (
                    last_weight + Decimal("2.5")
                ),
                "suggested_reps": (
                    target_reps or last_reps
                ),
            }

        if mode == "INCREASE_REPS":
            return {
                "suggested_weight": last_weight,
                "suggested_reps": last_reps + 1,
            }

        if mode == "LAST_SESSION":
            return {
                "suggested_weight": last_weight,
                "suggested_reps": (
                    target_reps or last_reps
                ),
            }

        raise ValueError(
            f"Unsupported target_weight_mode: {mode}"
        )

    # ------------------------------------------------------------------
    # Alternatives
    # ------------------------------------------------------------------

    def get_alternatives(
        self,
        exercise_id: str,
    ) -> List[ExerciseAlternativeTable]:
        return (
            self.db.query(ExerciseAlternativeTable)
            .filter(
                ExerciseAlternativeTable.exercise_id
                == exercise_id
            )
            .order_by(
                ExerciseAlternativeTable.id.asc()
            )
            .all()
        )

    def add_alternative(
        self,
        exercise_id: str,
        alternative_exercise_id: str,
    ) -> ExerciseAlternativeTable:
        if exercise_id == alternative_exercise_id:
            raise ValueError(
                "An exercise cannot be its own alternative"
            )

        source = (
            self.db.query(ExerciseTable)
            .filter(
                ExerciseTable.id == exercise_id,
                ExerciseTable.is_active.is_(True),
            )
            .first()
        )

        alternative = (
            self.db.query(ExerciseTable)
            .filter(
                ExerciseTable.id
                == alternative_exercise_id,
                ExerciseTable.is_active.is_(True),
            )
            .first()
        )

        if not source or not alternative:
            raise ValueError(
                "Exercise or alternative exercise not found"
            )

        existing = (
            self.db.query(ExerciseAlternativeTable)
            .filter(
                ExerciseAlternativeTable.exercise_id
                == exercise_id,
                ExerciseAlternativeTable.alternative_exercise_id
                == alternative_exercise_id,
            )
            .first()
        )

        if existing:
            raise ValueError(
                "Alternative already exists"
            )

        row = ExerciseAlternativeTable(
            exercise_id=exercise_id,
            alternative_exercise_id=alternative_exercise_id,
        )

        self.db.add(row)
        self.db.flush()
        return row

    def remove_alternative(
        self,
        alternative_id: str,
    ) -> bool:
        row = (
            self.db.query(ExerciseAlternativeTable)
            .filter(
                ExerciseAlternativeTable.id
                == alternative_id
            )
            .first()
        )

        if not row:
            return False

        self.db.delete(row)
        self.db.flush()
        return True
