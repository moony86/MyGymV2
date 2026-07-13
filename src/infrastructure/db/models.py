import uuid
import uuid6
from decimal import Decimal
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Numeric, Index
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