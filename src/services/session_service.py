import uuid
import uuid6
from decimal import Decimal
from typing import Optional, List
from sqlalchemy.orm import Session as DbSession
from sqlalchemy import and_, select

from src.domain.entities import Session, PerformedExercise, Set, SetType, SessionStatus, utc_now
from src.infrastructure.db.models import SessionTable, PerformedExerciseTable, SetTable, ExerciseTable
from src.services.units_service import WeightFormatter
from src.domain.entities import utc_now

class SessionService:
    def __init__(self, db_session: DbSession):
        self.db = db_session

    # --- المساعدات الداخلية ---
    def _to_domain_session(self, orm_session: SessionTable) -> Session:
        return Session.model_validate(orm_session, from_attributes=True)

    def _to_domain_set(self, orm_set: SetTable) -> Set:
        return Set.model_validate(orm_set, from_attributes=True)

    # --- 1. بدء جلسة جديدة ---
    def create_session(self, notes: Optional[str] = None) -> Session:
        active = self.db.query(SessionTable).filter(SessionTable.status == SessionStatus.ACTIVE.value).first()
        if active:
            raise ValueError("Cannot create new session. An ACTIVE session already exists. Please finish or abandon it first.")

        orm_session = SessionTable(
            id=str(uuid6.uuid7()),
            status=SessionStatus.ACTIVE.value,
            started_at=utc_now(),  # <-- أضف هذا
            notes=notes
        )
        self.db.add(orm_session)
        self.db.commit()
        self.db.refresh(orm_session)
        return self._to_domain_session(orm_session)

    # --- 2. استرجاع الجلسة النشطة (للاستكمال) ---
    def get_active_session(self) -> Optional[Session]:
        orm_session = self.db.query(SessionTable).filter(SessionTable.status == SessionStatus.ACTIVE.value).first()
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
        display_order: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Set:
        orm_session = self.db.query(SessionTable).filter(SessionTable.id == str(session_id)).first()
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

        orm_performed = self.db.query(PerformedExerciseTable).filter(
            and_(
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
            set_order = current_set_count

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
            set_type=set_type.value
        )
        self.db.add(orm_set)
        self.db.commit()
        self.db.refresh(orm_set)

        return self._to_domain_set(orm_set)

    # --- 4. إنهاء الجلسة ---
    def finish_session(self, session_id: uuid.UUID) -> Session:
        orm_session = self.db.query(SessionTable).filter(SessionTable.id == str(session_id)).first()
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
        orm_session = self.db.query(SessionTable).filter(SessionTable.id == str(session_id)).first()
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
        stmt = select(SessionTable).where(SessionTable.status == SessionStatus.ACTIVE.value)
        results = self.db.execute(stmt).scalars().all()
        return [self._to_domain_session(s) for s in results]

     # --- 7. استدعاء الجلسات (Abandon) ---
    def get_completed_sessions(self, limit: int = 30):
        stmt = (
            select(SessionTable)
            .where(SessionTable.status == SessionStatus.COMPLETED.value)
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
            .where(PerformedExerciseTable.session_id == str(session_id))
            .order_by(PerformedExerciseTable.display_order, SetTable.set_order)
        )
        return self.db.execute(stmt).scalars().all()

    def get_all_exercises(self):
        stmt = select(ExerciseTable).where(ExerciseTable.is_active == True).order_by(ExerciseTable.name)
        return self.db.execute(stmt).scalars().all()

    def get_session_with_details(self, session_id: uuid.UUID):
        orm_session = self.db.query(SessionTable).filter(SessionTable.id == str(session_id)).first()
        if not orm_session:
            return None, []
        
        sets = self.get_session_sets(session_id)
        return self._to_domain_session(orm_session), sets

    def get_last_set(self, session_id: uuid.UUID, exercise_id: uuid.UUID):
        orm_performed = self.db.query(PerformedExerciseTable).filter(
            and_(
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
                   set_type: Optional[SetType] = None, rpe: Optional[float] = None):
        orm_set = self.db.query(SetTable).filter(SetTable.id == str(set_id)).first()
        if not orm_set:
            raise ValueError("Set not found.")
        
        if weight is not None:
            orm_set.weight = WeightFormatter.to_decimal(weight)
        if reps is not None:
            orm_set.reps = reps
        if set_type is not None:
            orm_set.set_type = set_type.value
        if rpe is not None:
            orm_set.rpe = rpe
        
        self.db.commit()
        self.db.refresh(orm_set)
        return self._to_domain_set(orm_set)

    def delete_set(self, set_id: uuid.UUID):
        orm_set = self.db.query(SetTable).filter(SetTable.id == str(set_id)).first()
        if not orm_set:
            raise ValueError("Set not found.")
        
        self.db.delete(orm_set)
        self.db.commit()
        return {"deleted": True}

    def delete_session(self, session_id: uuid.UUID):
        orm_session = self.db.query(SessionTable).filter(SessionTable.id == str(session_id)).first()
        if not orm_session:
            raise ValueError("Session not found.")
    # إذا كانت العلاقات بها cascade، فقط احذف الجلسة
        self.db.delete(orm_session)
    # ولكن قد تحتاج إلى حذف PerformedExercise و Sets يدوياً إذا لم تكن cascade مضبوطة
    # للتأكد، يمكننا حذفها يدوياً:
        performed_exercises = self.db.query(PerformedExerciseTable).filter(
            PerformedExerciseTable.session_id == str(session_id)
        ).all()
        for pe in performed_exercises:
        # حذف الـ Sets المرتبطة
            self.db.query(SetTable).filter(SetTable.performed_exercise_id == pe.id).delete()
    # حذف PerformedExercise
        self.db.query(PerformedExerciseTable).filter(
            PerformedExerciseTable.session_id == str(session_id)
        ).delete()
    # ثم حذف Session
        self.db.delete(orm_session)
