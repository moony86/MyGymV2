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


DEFAULT_PROFILE_ID = "00000000-0000-0000-0000-000000000001"


class ProfileTable(Base):
    __tablename__ = "profiles"

    id = Column(TEXT, primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

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
    knowledge_variant_id = Column(String(150), nullable=True, index=True)

    __table_args__ = (
        Index('ix_exercises_name', 'name'),
    )

class SessionTable(Base):
    __tablename__ = "sessions"

    id = Column(TEXT, primary_key=True, default=lambda: str(uuid6.uuid7()))

    plan_id = Column(TEXT, ForeignKey("workout_plans.id", ondelete="SET NULL"),nullable=True)
    profile_id = Column(TEXT, nullable=False, index=True, default=DEFAULT_PROFILE_ID)

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
    rir = Column(Integer, nullable=True)
    set_type = Column(String(20), nullable=False, default=SetType.WORKING.value)

    # العلاقات
    performed_exercise = relationship("PerformedExerciseTable", back_populates="sets")

    __table_args__ = (
        Index('ix_sets_performed_exercise', 'performed_exercise_id'),
        Index('ix_sets_set_type', 'set_type'),
    )

class ClientOperationTable(Base):
    __tablename__ = "client_operations"

    operation_id = Column(TEXT, primary_key=True)
    operation_type = Column(String(50), nullable=False)
    resource_id = Column(TEXT, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        Index('ix_client_operations_resource', 'resource_id'),
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
    program_group_id = Column(TEXT, nullable=True, index=True)
    day_index = Column(Integer, nullable=True)
    profile_id = Column(TEXT, nullable=False, index=True, default=DEFAULT_PROFILE_ID)

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


class TrainingProfileTable(Base):
    """
    التطبيق single-user حاليًا: صف واحد فقط، بمعرّف ثابت معروف مسبقًا
    (DEFAULT_PROFILE_ID) — لا اعتماد على .first() الضمني.
    لا user_id لأنه لا يوجد نظام مستخدمين متعدد بعد.

    current_weight_kg مصمم عمدًا كـ "آخر قيمة معروفة فقط" — عندما تُضاف
    WeightHistoryTable لاحقًا، ستكون FK على profile_id بدون أي تعديل هنا.

    birth_year بدل age: العمر يُشتق دائمًا وقت الحاجة (Domain.age property)
    ولا يُخزَّن أبدًا كقيمة ثابتة قد تصبح خاطئة صامتًا بعد سنة.
    """
    __tablename__ = "training_profile"

    id = Column(TEXT, primary_key=True, default=lambda: DEFAULT_PROFILE_ID)

    # --- Identity ---
    sex = Column(String(10), nullable=False)          # 'MALE' | 'FEMALE'
    birth_year = Column(Integer, nullable=False)

    # --- Body Metrics ---
    height_cm = Column(Numeric(5, 2), nullable=False)
    current_weight_kg = Column(Numeric(5, 2), nullable=False)

    # --- Training Preferences (Constraints) ---
    experience_level = Column(String(20), nullable=False)      # BEGINNER | INTERMEDIATE | ADVANCED
    training_days_per_week = Column(Integer, nullable=False)
    session_duration_minutes = Column(Integer, nullable=False)
    primary_goal = Column(String(30), nullable=False)           # HYPERTROPHY | STRENGTH | FAT_LOSS | GENERAL_FITNESS

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_training_profile_updated_at", "updated_at"),
    )


class BodyMeasurementTable(Base):
    __tablename__ = "body_measurements"

    id = Column(TEXT, primary_key=True, default=lambda: str(uuid6.uuid7()))
    profile_id = Column(TEXT, nullable=False, index=True)
    date = Column(DateTime, nullable=False)
    type = Column(String(10), nullable=False)  # 'weekly' | 'monthly'
    goal = Column(String(20), nullable=True)  # 'fat_loss' | 'muscle_gain' | 'maintain'
    weight = Column(Numeric(5, 2), nullable=True)
    waist = Column(Numeric(5, 2), nullable=True)
    narrow_waist = Column(Numeric(5, 2), nullable=True)
    chest = Column(Numeric(5, 2), nullable=True)
    hips = Column(Numeric(5, 2), nullable=True)
    left_arm = Column(Numeric(5, 2), nullable=True)
    right_arm = Column(Numeric(5, 2), nullable=True)
    left_thigh = Column(Numeric(5, 2), nullable=True)
    right_thigh = Column(Numeric(5, 2), nullable=True)
    neck = Column(Numeric(5, 2), nullable=True)
    body_fat = Column(Numeric(5, 2), nullable=True)
    notes = Column(Text, nullable=True)
    conditions = Column(JSON, nullable=True)
    front_photo = Column(Text, nullable=True)
    side_photo = Column(Text, nullable=True)
    back_photo = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_body_measurements_profile_date', 'profile_id', 'date'),
    )
