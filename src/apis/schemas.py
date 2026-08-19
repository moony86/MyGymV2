from pydantic import BaseModel, field_validator, field_serializer
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from src.domain.enums import SessionStatus, SetType


class AddExerciseToSessionRequest(BaseModel):
    exercise_id: str


class PerformedExerciseDTO(BaseModel):
    id: str
    exercise_id: str
    exercise_name: str
    display_order: int
    is_planned: bool  # هل هذا التمرين ضمن خطة هذه الجلسة أصلًا؟
    has_sets: bool     # هل سُجّلت له أي مجموعة فعليًا؟

class TrainingProfileDTO(BaseModel):
    id: str
    sex: str
    birth_year: int
    age: int  # مشتق وقت الإرسال فقط، لا يُخزَّن أبدًا
    height_cm: Decimal
    current_weight_kg: Decimal
    experience_level: str
    training_days_per_week: int
    session_duration_minutes: int
    primary_goal: str
    updated_at: datetime
    warnings: List[dict] = []

    @field_validator('height_cm', 'current_weight_kg', mode='before')
    @classmethod
    def serialize_decimal_fields(cls, v):
        if isinstance(v, Decimal):
            return str(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        return v


class ProfileDTO(BaseModel):
    id: str
    name: str


class CreateProfileRequest(BaseModel):
    name: str


class UpsertTrainingProfileRequest(BaseModel):
    sex: str
    birth_year: int
    height_cm: Decimal
    current_weight_kg: Decimal
    experience_level: str
    training_days_per_week: int
    session_duration_minutes: int
    primary_goal: str


class UpdateWeightRequest(BaseModel):
    current_weight_kg: Decimal

def serialize_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _as_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """
    SQLite يفقد الـ tzinfo عند التخزين، لكن القيمة الرقمية المخزّنة هي UTC
    فعليًا (كل كتابة تمر عبر utc_now()). لذلك أي datetime بدون tzinfo قادم
    من قاعدة البيانات نعتبره UTC صراحة، ونرسله دائمًا بلاحقة 'Z' حتى لا
    يفسّره المتصفح كتوقيت محلي (هذا كان سبب فرق الـ 3 ساعات في العداد).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


class SessionDTO(BaseModel):
    id: str
    status: SessionStatus
    started_at: datetime
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None
    plan_id: Optional[str] = None

    volume_kg: Decimal = Decimal("0")
    sets_count: int = 0
    duration_minutes: Optional[int] = None

    @field_validator('volume_kg', mode='before')
    @classmethod
    def serialize_volume(cls, v):
        if isinstance(v, Decimal):
            return serialize_decimal(v)
        return v

    @field_serializer('started_at', 'ended_at')
    def serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        return _as_utc_iso(dt)

class SetDTO(BaseModel):
    id: str
    performed_exercise_id: str
    exercise_name: str
    set_order: int
    weight: Decimal
    reps: int
    rpe: Optional[float] = None
    rir: Optional[int] = None
    set_type: SetType
    volume_kg: Decimal

    @field_validator('weight', 'volume_kg', mode='before')
    @classmethod
    def serialize_weight(cls, v):
        if isinstance(v, Decimal):
            return serialize_decimal(v)
        return v

class ExerciseDTO(BaseModel):
    id: str
    name: str
    primary_muscle: Optional[str] = None
    equipment: Optional[str] = None
    aliases: Optional[List[str]] = None

class ActiveSessionDTO(BaseModel):
    session: Optional[SessionDTO] = None
    sets: List[SetDTO] = []
    last_set: Optional[SetDTO] = None
    total_volume: Decimal = Decimal("0")

class MessageResponse(BaseModel):
    message: str

class StartWorkoutRequest(BaseModel):
    notes: Optional[str] = None

class AddSetRequest(BaseModel):
    exercise_id: str
    client_operation_id: Optional[str] = None
    weight: Decimal
    reps: int
    set_order: Optional[int] = None
    set_type: SetType = SetType.WORKING
    rpe: Optional[float] = None
    rir: Optional[int] = None
    notes: Optional[str] = None

class FinishWorkoutRequest(BaseModel):
    session_id: str

class UpdateSetRequest(BaseModel):
    weight: Optional[Decimal] = None
    reps: Optional[int] = None
    set_type: Optional[SetType] = None
    rpe: Optional[float] = None
    rir: Optional[int] = None


class BodyMeasurementDTO(BaseModel):
    id: str
    profile_id: str
    date: str
    type: str
    goal: Optional[str]
    weight: Optional[str]
    waist: Optional[str]
    narrow_waist: Optional[str]
    chest: Optional[str]
    hips: Optional[str]
    left_arm: Optional[str]
    right_arm: Optional[str]
    left_thigh: Optional[str]
    right_thigh: Optional[str]
    neck: Optional[str]
    body_fat: Optional[str]
    notes: Optional[str]
    conditions: Optional[dict]
    front_photo: Optional[str]
    side_photo: Optional[str]
    back_photo: Optional[str]
    created_at: str

    @field_validator(
        "weight", "waist", "narrow_waist", "chest", "hips",
        "left_arm", "right_arm", "left_thigh", "right_thigh",
        "neck", "body_fat",
        mode="before",
    )
    @classmethod
    def serialize_decimal(cls, v):
        if v is None:
            return None
        if isinstance(v, Decimal):
            return serialize_decimal(v)
        return str(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @field_serializer("date", "created_at")
    def serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        return _as_utc_iso(dt)


class AddBodyMeasurementRequest(BaseModel):
    date: str
    type: str
    goal: Optional[str] = None
    weight: Optional[Decimal] = None
    waist: Optional[Decimal] = None
    narrow_waist: Optional[Decimal] = None
    chest: Optional[Decimal] = None
    hips: Optional[Decimal] = None
    left_arm: Optional[Decimal] = None
    right_arm: Optional[Decimal] = None
    left_thigh: Optional[Decimal] = None
    right_thigh: Optional[Decimal] = None
    neck: Optional[Decimal] = None
    body_fat: Optional[Decimal] = None
    notes: Optional[str] = None
    conditions: Optional[dict] = None
    front_photo: Optional[str] = None
    side_photo: Optional[str] = None
    back_photo: Optional[str] = None
