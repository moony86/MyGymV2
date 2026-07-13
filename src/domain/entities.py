import uuid
import uuid6
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from .enums import SetType, SessionStatus

# --- قاعدة للحصول على UTC الآن ---
def utc_now() -> datetime:
    return datetime.now(timezone.utc)

# --- 1. كيان Exercise (المكتبة) ---
class Exercise(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid6.uuid7)
    name: str
    primary_muscle: Optional[str] = None
    secondary_muscles: Optional[str] = None  # يمكن الفصل بفواصل
    equipment: Optional[str] = None
    movement_pattern: Optional[str] = None
    difficulty: Optional[str] = None
    is_active: bool = True
    aliases: Optional[List[str]] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Exercise name cannot be empty.")
        return v.strip()

    model_config = ConfigDict(frozen=False)

# --- 2. كيان Session (الجلسة) ---
class Session(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid6.uuid7)
    status: SessionStatus = SessionStatus.ACTIVE
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None

    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        if isinstance(v, str):
            return SessionStatus(v)
        return v

    @model_validator(mode='after')
    def check_end_after_start(self):
        if self.ended_at and self.started_at and self.ended_at <= self.started_at:
            raise ValueError("Ended time must be after started time.")
        return self

# --- 3. كيان PerformedExercise (نسخة التمرين داخل الجلسة) ---
class PerformedExercise(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid6.uuid7)
    session_id: uuid.UUID
    exercise_id: uuid.UUID
    display_order: int = 0
    notes: Optional[str] = None
    is_skipped: bool = False
    is_warmup: bool = False  # هل هو تمرين إحماء كامل (ليس نفس الـ Set)

    @field_validator('display_order')
    @classmethod
    def validate_order(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Display order cannot be negative.")
        return v

# --- 4. كيان Set (المجموعة - غير مرتبط بـ Gym فقط) ---
class Set(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid6.uuid7)
    performed_exercise_id: uuid.UUID
    set_order: int = 0
    weight: Decimal  # بالكيلوجرام كـ Decimal
    reps: int
    rpe: Optional[float] = None
    set_type: SetType = SetType.WORKING

    @field_validator('weight')
    @classmethod
    def validate_weight(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Weight cannot be negative.")
        return v

    @field_validator('reps')
    @classmethod
    def validate_reps(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Reps must be greater than 0.")
        return v

    @field_validator('rpe')
    @classmethod
    def validate_rpe(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 1.0 or v > 10.0):
            raise ValueError("RPE must be between 1 and 10.")
        return v

    model_config = ConfigDict(frozen=True)