import uuid
import uuid6
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy.orm import Session as DbSession
from sqlalchemy import and_, select

from src.domain.entities import Session, PerformedExercise, Set, SetType, SessionStatus, utc_now
from src.infrastructure.db.models import SessionTable, PerformedExerciseTable, SetTable, ExerciseTable, DEFAULT_PROFILE_ID
from src.services.units_service import WeightFormatter
from src.domain.profile_context import get_current_profile_id


class SessionService:
    def __init__(self, db_session: DbSession, profile_id: Optional[str] = None):
        self.db = db_session
        self.profile_id = profile_id or get_current_profile_id()

    # --- المساعدات الداخلية ---
    def _to_domain_session(self, orm_session: SessionTable) -> Session:
        return Session.model_validate(orm_session, from_attributes=True)

    def _to_domain_set(self, orm_set: SetTable) -> Set:
        return Set.model_validate(orm_set, from_attributes=True)

    def _auto_abandon_stale_sessions(self, max_hours: int = 12, no_sets_hours: int = 4) -> int:
        """يُلغي تلقائياً الجلسات النشطة القديمة أو الفارغة.
        يُنفَّذ قبل أي عملية تعتمد على الجلسة النشطة.

        Args:
            max_hours: أقصى عمر لجلسة ACTIVE (بأي حال)
            no_sets_hours: أقصى عمر لجلسة ACTIVE بدون أي sets
        Returns:
            عدد الجلسات التي أُلغيت
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        active_sessions = self.db.query(SessionTable).filter(
            SessionTable.status == SessionStatus.ACTIVE.value,
            SessionTable.profile_id == self.profile_id,
        ).all()

        if not active_sessions:
            return 0

        abandoned_count = 0
        for sess in active_sessions:
            try:
                started = sess.started_at
                if isinstance(started, str):
                    started = datetime.fromisoformat(started.replace('Z', ''))
                if started.tzinfo is not None:
                    started = started.replace(tzinfo=None)
                age_hours = (now - started).total_seconds() / 3600
            except Exception:
                age_hours = 0

            sets_count = self.db.query(SetTable).join(PerformedExerciseTable).filter(
                PerformedExerciseTable.session_id == sess.id
            ).count()

            should_abandon = False
            reason = ""

            if age_hours > max_hours:
                should_abandon = True
                reason = f"عمرها {age_hours:.1f} ساعة"
            elif sets_count == 0 and age_hours > no_sets_hours:
                should_abandon = True
                reason = f"فارغة منذ {age_hours:.1f} ساعة"

            if should_abandon:
                sess.status = SessionStatus.ABANDONED.value
                sess.ended_at = utc_now()
                abandoned_count += 1
                print(f"  [auto-abandon] session {sess.id[:8]}... ({reason})")

        if abandoned_count > 0:
            self.db.commit()
        return abandoned_count

    # --- 1. بدء جلسة جديدة ---
    def create_session(
        self,
        notes: Optional[str] = None,
        plan_id: Optional[str] = None
    ) -> Session:
        # أولاً: نظّف الجلسات القديمة/الفارغة تلقائياً
        self._auto_abandon_stale_sessions()

        active = self.db.query(SessionTable).filter(
            SessionTable.status == SessionStatus.ACTIVE.value,
            SessionTable.profile_id == self.profile_id,
        ).first()
        if active:
            raise ValueError("Cannot create new session. An ACTIVE session already exists. Please finish or abandon it first.")

        orm_session = SessionTable(
            id=str(uuid6.uuid7()),
            status=SessionStatus.ACTIVE.value,
            started_at=utc_now(),
            notes=notes,
            plan_id=plan_id,
            profile_id=self.profile_id,
        )
        self.db.add(orm_session)
        self.db.commit()
        self.db.refresh(orm_session)
        return self._to_domain_session(orm_session)

    # --- 2. استرجاع الجلسة النشطة ---
    def get_active_session(self) -> Optional[Session]:
        # نظّف الجلسات القديمة أولاً
        self._auto_abandon_stale_sessions()

        orm_session = self.db.query(SessionTable).filter(
            SessionTable.status == SessionStatus.ACTIVE.value,
            SessionTable.profile_id == self.profile_id,
        ).first()
        if not orm_session:
            return None
        return self._to_domain_session(orm_session)

    # --- 3. إضافة مجموعة (Set) ---
    def add_set(
        self,
        session_id: uuid.UUID,
        exercise_id: uuid.UUID,
        weight: Decimal,
        reps: int,
        set_order: Optional[int] = None,
        set_type: SetType = SetType.WORKING,
        rpe: Optional[float] = None,
        rir: Optional[int] = None,
        display_order: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Set:
        orm_session = self.db.query(SessionTable).filter(
            SessionTable.id == str(session_id),
            SessionTable.profile_id == self.profile_id,
        ).first()
        if not orm_session:
            raise ValueError("Session not found.")
        if orm_session.status == SessionStatus.COMPLETED.value:
            raise ValueError("Cannot add sets to a COMPLETED session (Immutable).")
        if orm_session.status == SessionStatus.ABANDONED.value:
            raise ValueError("Cannot add sets to an ABANDONED session.")

        orm_exercise = self.db.query(ExerciseTable).filter(
            and_(ExerciseTable.id == str(exercise_id), ExerciseTable.is_active == True)
        ).first()
        if not orm_exercise:
            raise ValueError("Exercise not found or is inactive.")

        orm_performed = self.db.query(PerformedExerciseTable).join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id).filter(
            and_(
                SessionTable.profile_id == self.profile_id,
                PerformedExerciseTable.session_id == str(session_id),
                PerformedExerciseTable.exercise_id == str(exercise_id)
            )
        ).first()

        if not orm_performed:
            current_max_order = self.db.query(PerformedExerciseTable).filter(
                PerformedExerciseTable.session_id == str(session_id)
            ).count()
            orm_performed = PerformedExerciseTable(
                id=str(uuid6.uuid7()),
                session_id=str(session_id),
                exercise_id=str(exercise_id),
                display_order=display_order if display_order is not None else current_max_order,
                notes=notes
            )
            self.db.add(orm_performed)
            self.db.flush()

        if set_order is None:
            current_set_count = self.db.query(SetTable).filter(
                SetTable.performed_exercise_id == orm_performed.id
            ).count()
            set_order = current_set_count + 1

        weight_decimal = WeightFormatter.to_decimal(weight)
        if weight_decimal < 0:
            raise ValueError("Weight cannot be negative.")
        if reps <= 0:
            raise ValueError("Reps must be > 0.")

        orm_set = SetTable(
            id=str(uuid6.uuid7()),
            performed_exercise_id=orm_performed.id,
            set_order=set_order,
            weight=weight_decimal,
            reps=reps,
            rpe=rpe,
            rir=rir,
            set_type=set_type.value
        )
        self._to_domain_set(orm_set)  # Validate before the row is added or committed.
        self.db.add(orm_set)
        self.db.flush()
        self.db.refresh(orm_set)

        return self._to_domain_set(orm_set)

    # --- 4. إنهاء الجلسة ---
    def finish_session(self, session_id: uuid.UUID) -> Session:
        orm_session = self.db.query(SessionTable).filter(
            SessionTable.id == str(session_id),
            SessionTable.profile_id == self.profile_id,
        ).first()
        if not orm_session:
            raise ValueError("Session not found.")
        if orm_session.status == SessionStatus.COMPLETED.value:
            raise ValueError("Session is already COMPLETED.")
        if orm_session.status == SessionStatus.ABANDONED.value:
            raise ValueError("Cannot finish an ABANDONED session.")

        set_count = self.db.query(SetTable).join(PerformedExerciseTable).filter(
            PerformedExerciseTable.session_id == str(session_id)
        ).count()

        if set_count == 0:
            raise ValueError("Cannot finish an empty session. Please add at least one set.")

        orm_session.status = SessionStatus.COMPLETED.value
        orm_session.ended_at = utc_now()
        self.db.commit()
        self.db.refresh(orm_session)
        return self._to_domain_session(orm_session)

    # --- 5. إلغاء الجلسة (Abandon) ---
    def abandon_session(self, session_id: uuid.UUID) -> Session:
        orm_session = self.db.query(SessionTable).filter(
            SessionTable.id == str(session_id),
            SessionTable.profile_id == self.profile_id,
        ).first()
        if not orm_session:
            raise ValueError("Session not found.")
        if orm_session.status in [SessionStatus.COMPLETED.value, SessionStatus.ABANDONED.value]:
            raise ValueError(f"Cannot abandon a session with status: {orm_session.status}")

        orm_session.status = SessionStatus.ABANDONED.value
        orm_session.ended_at = utc_now()
        self.db.commit()
        self.db.refresh(orm_session)
        return self._to_domain_session(orm_session)

    # --- 6. Crash Recovery ---
    def recover_active_sessions(self) -> List[Session]:
        stmt = select(SessionTable).where(
            SessionTable.status == SessionStatus.ACTIVE.value,
            SessionTable.profile_id == self.profile_id,
        )
        results = self.db.execute(stmt).scalars().all()
        return [self._to_domain_session(s) for s in results]

    # --- 7. استعلامات واسترجاع الجلسات ---
    def get_completed_sessions(self, limit: int = 30):
        stmt = (
            select(SessionTable)
            .where(
                SessionTable.status == SessionStatus.COMPLETED.value,
                SessionTable.profile_id == self.profile_id,
            )
            .order_by(SessionTable.started_at.desc())
            .limit(limit)
        )
        return [
            self._to_domain_session(session)
            for session in self.db.execute(stmt).scalars().all()
        ]

    def get_session_sets(self, session_id: uuid.UUID):
        stmt = (
            select(SetTable)
            .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
            .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
            .where(PerformedExerciseTable.session_id == str(session_id), SessionTable.profile_id == self.profile_id)
            .order_by(PerformedExerciseTable.display_order, SetTable.set_order)
        )
        return self.db.execute(stmt).scalars().all()

    def get_all_exercises(self):
        stmt = select(ExerciseTable).where(ExerciseTable.is_active == True).order_by(ExerciseTable.name)
        return self.db.execute(stmt).scalars().all()

    def get_session_with_details(self, session_id: uuid.UUID):
        orm_session = self.db.query(SessionTable).filter(
            SessionTable.id == str(session_id),
            SessionTable.profile_id == self.profile_id,
        ).first()
        if not orm_session:
            return None, []

        sets = self.get_session_sets(session_id)
        return self._to_domain_session(orm_session), sets

    def get_last_set(self, session_id: uuid.UUID, exercise_id: uuid.UUID):
        orm_performed = self.db.query(PerformedExerciseTable).join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id).filter(
            and_(
                SessionTable.profile_id == self.profile_id,
                PerformedExerciseTable.session_id == str(session_id),
                PerformedExerciseTable.exercise_id == str(exercise_id)
            )
        ).first()
        if not orm_performed:
            return None

        stmt = (
            select(SetTable)
            .where(SetTable.performed_exercise_id == orm_performed.id)
            .order_by(SetTable.set_order.desc())
            .limit(1)
        )
        result = self.db.execute(stmt).scalar_one_or_none()
        return self._to_domain_set(result) if result else None

    def update_set(self, set_id: uuid.UUID, weight: Optional[Decimal] = None, reps: Optional[int] = None,
                   set_type: Optional[SetType] = None, rpe: Optional[float] = None, rir: Optional[int] = None):
        orm_set = (self.db.query(SetTable)
            .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
            .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
            .filter(SetTable.id == str(set_id), SessionTable.profile_id == self.profile_id).first())
        if not orm_set:
            raise ValueError("Set not found.")

        values = self._to_domain_set(orm_set).model_dump()
        updates = {'weight': weight, 'reps': reps, 'set_type': set_type, 'rpe': rpe, 'rir': rir}
        for field, value in updates.items():
            if value is not None:
                values[field] = WeightFormatter.to_decimal(value) if field == 'weight' else value
        # Validate the complete candidate before touching the tracked ORM row.
        validated = Set.model_validate(values)
        for field, value in updates.items():
            if value is not None:
                setattr(orm_set, field, validated.set_type.value if field == 'set_type' else getattr(validated, field))
        self.db.flush()
        return self._to_domain_set(orm_set)

    def delete_set(self, set_id: uuid.UUID):
        orm_set = (self.db.query(SetTable)
            .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
            .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
            .filter(SetTable.id == str(set_id), SessionTable.profile_id == self.profile_id).first())
        if not orm_set:
            raise ValueError("Set not found.")

        self.db.delete(orm_set)
        self.db.commit()
        return {"deleted": True}

    def delete_session(self, session_id: uuid.UUID):
        orm_session = self.db.query(SessionTable).filter(
            SessionTable.id == str(session_id),
            SessionTable.profile_id == self.profile_id
        ).first()
        if not orm_session:
            raise ValueError("Session not found.")

        self.db.delete(orm_session)
        self.db.commit()
        return {"deleted": True}

    def add_exercise_to_session(self, session_id, exercise_id) -> PerformedExerciseTable:
        session = self.db.query(SessionTable).filter(
            SessionTable.id == str(session_id),
            SessionTable.profile_id == self.profile_id
        ).first()
        if not session:
            raise ValueError("Session not found")

        exercise = self.db.query(ExerciseTable).filter(
            ExerciseTable.id == str(exercise_id),
            ExerciseTable.is_active == True
        ).first()
        if not exercise:
            raise ValueError("Exercise not found or inactive")

        existing = self.db.query(PerformedExerciseTable).filter(
            PerformedExerciseTable.session_id == str(session_id),
            PerformedExerciseTable.exercise_id == str(exercise_id)
        ).first()
        if existing:
            return existing

        max_order = self.db.query(PerformedExerciseTable).filter(
            PerformedExerciseTable.session_id == str(session_id)
        ).count()

        performed = PerformedExerciseTable(
            id=str(uuid6.uuid7()),
            session_id=str(session_id),
            exercise_id=str(exercise_id),
            display_order=max_order,
        )
        self.db.add(performed)
        self.db.commit()
        self.db.refresh(performed)
        return performed
