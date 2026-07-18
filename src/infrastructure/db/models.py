import uuid
import uuid6
from decimal import Decimal
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Numeric, Index, UniqueConstraint
from sqlalchemy.dialects.sqlite import TEXT  # لتخزين UUID كنص
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone
from sqlalchemy.types import JSON
from src.domain.enums import SessionStatus, SetType

Base = declarative_base()

def utc_now():
    return datetime.now(timezone.utc)

class ExerciseTable(Base):
    __tablename__ = "exercises"

    id = Column(TEXT, primary_key=True, default=lambda: str(uuid6.uuid7()))
    name = Column(String(255), nullable=False, unique=True)
    primary_muscle = Column(String(100))
    secondary_muscles = Column(String(255))
    equipment = Column(String(100))
    movement_pattern = Column(String(100))
    difficulty = Column(String(50))
    is_active = Column(Boolean, default=True)
    aliases = Column(JSON, nullable=True)

    __table_args__ = (
        Index('ix_exercises_name', 'name'),
    )

class SessionTable(Base):
    __tablename__ = "sessions"

    id = Column(TEXT, primary_key=True, default=lambda: str(uuid6.uuid7()))

    plan_id = Column(TEXT, ForeignKey("workout_plans.id", ondelete="SET NULL"),nullable=True)

    plan = relationship("WorkoutPlanTable", back_populates="sessions")

    status = Column(String(20), nullable=False, default=SessionStatus.ACTIVE.value)
    started_at = Column(DateTime, nullable=False, default=utc_now)
    ended_at = Column(DateTime, nullable=True)
    notes = Column(Text)
    # العلاقات
    performed_exercises = relationship("PerformedExerciseTable", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_sessions_status', 'status'),
        Index('ix_sessions_started_at', 'started_at'),
    )

class PerformedExerciseTable(Base):
    __tablename__ = "performed_exercises"

    id = Column(TEXT, primary_key=True, default=lambda: str(uuid6.uuid7()))
    session_id = Column(TEXT, ForeignKey("sessions.id"), nullable=False)
    exercise_id = Column(TEXT, ForeignKey("exercises.id"), nullable=False)
    display_order = Column(Integer, default=0)
    notes = Column(Text)
    is_skipped = Column(Boolean, default=False)
    is_warmup = Column(Boolean, default=False)

    # العلاقات
    session = relationship("SessionTable", back_populates="performed_exercises")
    exercise = relationship("ExerciseTable")
    sets = relationship("SetTable", back_populates="performed_exercise", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_performed_exercises_session', 'session_id'),
    )

class SetTable(Base):
    __tablename__ = "sets"

    id = Column(TEXT, primary_key=True, default=lambda: str(uuid6.uuid7()))
    performed_exercise_id = Column(TEXT, ForeignKey("performed_exercises.id"), nullable=False)
    set_order = Column(Integer, default=0)
    weight = Column(Numeric(6, 2), nullable=False)
    reps = Column(Integer, nullable=False)
    rpe = Column(Float, nullable=True)
    set_type = Column(String(20), nullable=False, default=SetType.WORKING.value)

    # العلاقات
    performed_exercise = relationship("PerformedExerciseTable", back_populates="sets")

    __table_args__ = (
        Index('ix_sets_performed_exercise', 'performed_exercise_id'),
        Index('ix_sets_set_type', 'set_type'),
    )
    
# ==================== =================== ====================
# ==================== PLANNER MODELS (V2) ====================
# ==================== =================== ====================

class WorkoutPlanTable(Base):
    __tablename__ = "workout_plans"

    id = Column(TEXT, primary_key=True, default=lambda: str(uuid6.uuid7()))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    # العلاقات
    plan_exercises = relationship("PlanExerciseTable", back_populates="plan", cascade="all, delete-orphan")
    schedules = relationship("PlanScheduleTable", back_populates="plan", cascade="all, delete-orphan")
    sessions = relationship("SessionTable",back_populates="plan")

    __table_args__ = (
        Index('ix_workout_plans_name', 'name'),
        Index('ix_workout_plans_enabled', 'enabled'),
    )


class PlanExerciseTable(Base):
    __tablename__ = "plan_exercises"

    id = Column(TEXT, primary_key=True, default=lambda: str(uuid6.uuid7()))
    plan_id = Column(TEXT, ForeignKey("workout_plans.id", ondelete="CASCADE"), nullable=False)
    exercise_id = Column(TEXT, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    order_index = Column(Integer, nullable=False, default=0)
    target_sets = Column(Integer, nullable=True)          # عدد المجموعات المخطط لها (إرشادي)
    target_reps = Column(Integer, nullable=True)          # عدد العدات المستهدف (إرشادي)
    target_weight_mode = Column(String(20), nullable=False, default="LAST_SESSION")  # 'LAST_SESSION', 'FIXED', 'EMPTY'
    fixed_weight = Column(Numeric(6, 2), nullable=True)   # للوضع FIXED
    fixed_reps = Column(Integer, nullable=True)           # للوضع FIXED
    rest_seconds = Column(Integer, nullable=True)         # راحة مقترحة

    # العلاقات
    plan = relationship("WorkoutPlanTable", back_populates="plan_exercises")
    exercise = relationship("ExerciseTable", foreign_keys=[exercise_id])

    __table_args__ = (
        Index('ix_plan_exercises_plan_id', 'plan_id'),
        Index('ix_plan_exercises_order', 'order_index'),
        UniqueConstraint('plan_id', 'exercise_id', name='uq_plan_exercise'),
    )


class PlanScheduleTable(Base):
    __tablename__ = "plan_schedules"

    id = Column(TEXT, primary_key=True, default=lambda: str(uuid6.uuid7()))
    plan_id = Column(TEXT, ForeignKey("workout_plans.id", ondelete="CASCADE"), nullable=False)
    schedule_type = Column(String(20), nullable=False, default="manual")  # 'weekly', 'interval', 'manual'
    interval_days = Column(Integer, nullable=True)          # إذا كان النوع interval
    days_mask = Column(Integer, nullable=True)              # بت ماسك للأيام (الأحد=1، الاثنين=2، ...)
    # يمكن إضافة حقل start_date أو وقت محدد لاحقاً

    # العلاقات
    plan = relationship("WorkoutPlanTable", back_populates="schedules")

    __table_args__ = (
        Index('ix_plan_schedules_plan_id', 'plan_id'),
    )


class ExerciseAlternativeTable(Base):
    __tablename__ = "exercise_alternatives"

    id = Column(TEXT, primary_key=True, default=lambda: str(uuid6.uuid7()))
    exercise_id = Column(TEXT, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    alternative_exercise_id = Column(TEXT, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)

    # العلاقات (اختيارية)
    exercise = relationship("ExerciseTable", foreign_keys=[exercise_id])
    alternative = relationship("ExerciseTable", foreign_keys=[alternative_exercise_id])

    __table_args__ = (
        UniqueConstraint('exercise_id', 'alternative_exercise_id', name='uq_exercise_alternative'),
    )
