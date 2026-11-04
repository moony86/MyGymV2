from pydantic import ConfigDict, BaseModel, Field, field_validator, field_serializer, model_validator
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from src.domain.enums import SessionStatus, SetType


class AddExerciseToSessionRequest(BaseModel):
    exercise_id: str


    @field_validator('exercise_id')
    @classmethod
    def valid_exercise_identifier(cls, value):
        import uuid
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Invalid exercise_id")

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
    brand: Optional[str] = None
    image_url: Optional[str] = None
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
    weight: Decimal = Field(ge=0, max_digits=6, decimal_places=2, allow_inf_nan=False)
    reps: int = Field(gt=0)
    set_order: Optional[int] = None
    set_type: SetType = SetType.WORKING
    rpe: Optional[float] = Field(default=None, ge=1, le=10, allow_inf_nan=False)
    rir: Optional[int] = Field(default=None, ge=0, le=10)
    notes: Optional[str] = None

    @field_validator('exercise_id')
    @classmethod
    def valid_exercise_identifier(cls, value):
        import uuid
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Invalid exercise_id")

class FinishWorkoutRequest(BaseModel):
    session_id: str

class UpdateSetRequest(BaseModel):
    weight: Optional[Decimal] = Field(default=None, ge=0, max_digits=6, decimal_places=2, allow_inf_nan=False)
    reps: Optional[int] = Field(default=None, gt=0)
    set_type: Optional[SetType] = None
    rpe: Optional[float] = Field(default=None, ge=1, le=10, allow_inf_nan=False)
    rir: Optional[int] = Field(default=None, ge=0, le=10)


class BodyMeasurementDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True,coerce_numbers_to_str=True)

    @field_validator('date',mode='before')
    @classmethod
    def normalize_measurement_date(cls,value):
        if isinstance(value,datetime):return value.date().isoformat()
        return value.isoformat() if hasattr(value,'isoformat') else value

    @field_validator('created_at',mode='before')
    @classmethod
    def normalize_created_at(cls,value):
        return _as_utc_iso(value) if isinstance(value,datetime) else value

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
        return _as_utc_iso(dt) if isinstance(dt, datetime) else dt if isinstance(dt,datetime) else dt


class AddBodyMeasurementRequest(BaseModel):
    date: str
    type: str
    goal: Optional[str] = None
    weight: Optional[Decimal] = Field(default=None,gt=0,max_digits=5,decimal_places=2,allow_inf_nan=False)
    waist: Optional[Decimal] = Field(default=None,gt=0,max_digits=5,decimal_places=2,allow_inf_nan=False)
    narrow_waist: Optional[Decimal] = Field(default=None,gt=0,max_digits=5,decimal_places=2,allow_inf_nan=False)
    chest: Optional[Decimal] = Field(default=None,gt=0,max_digits=5,decimal_places=2,allow_inf_nan=False)
    hips: Optional[Decimal] = Field(default=None,gt=0,max_digits=5,decimal_places=2,allow_inf_nan=False)
    left_arm: Optional[Decimal] = Field(default=None,gt=0,max_digits=5,decimal_places=2,allow_inf_nan=False)
    right_arm: Optional[Decimal] = Field(default=None,gt=0,max_digits=5,decimal_places=2,allow_inf_nan=False)
    left_thigh: Optional[Decimal] = Field(default=None,gt=0,max_digits=5,decimal_places=2,allow_inf_nan=False)
    right_thigh: Optional[Decimal] = Field(default=None,gt=0,max_digits=5,decimal_places=2,allow_inf_nan=False)
    neck: Optional[Decimal] = Field(default=None,gt=0,max_digits=5,decimal_places=2,allow_inf_nan=False)
    body_fat: Optional[Decimal] = Field(default=None,ge=0,le=100,max_digits=5,decimal_places=2,allow_inf_nan=False)
    notes: Optional[str] = None
    conditions: Optional[dict] = None
    front_photo: Optional[str] = None
    side_photo: Optional[str] = None
    back_photo: Optional[str] = None



    @field_validator('date')
    @classmethod
    def valid_date(cls,value):
        from datetime import date as Date, datetime
        from zoneinfo import ZoneInfo
        parsed=Date.fromisoformat(value)
        if parsed>datetime.now(ZoneInfo('Asia/Riyadh')).date():raise ValueError('Future measurements are not valid')
        return parsed.isoformat()

    @model_validator(mode='after')
    def has_measurement(self):
        if not any(getattr(self,name) is not None for name in ['weight','waist','narrow_waist','chest','hips','left_arm','right_arm','left_thigh','right_thigh','neck','body_fat']):raise ValueError('Enter at least one measurement')
        return self

# ============================================================
# Planner Schemas
# ============================================================
class PlanExerciseSchema(BaseModel):
    exercise_id: str
    target_sets: int
    target_reps_min: int
    target_reps_max: int
    display_order: int = 0
    notes: Optional[str] = None

class PlanScheduleSchema(BaseModel):
    day_of_week: int
    name: Optional[str] = None

class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    exercises: List[PlanExerciseSchema] = []
    schedules: List[PlanScheduleSchema] = []

class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    exercises: Optional[List[PlanExerciseSchema]] = None
    schedules: Optional[List[PlanScheduleSchema]] = None

class PlanResponse(BaseModel):
    id: str
    profile_id: str
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        return _as_utc_iso(dt)

class ProgressiveOverloadSuggestion(BaseModel):
    exercise_id: str
    suggested_weight: Decimal
    suggested_reps: int
    reason: str


# ============================================================
# Exercise Management Schemas (CRUD)
# ============================================================
class CreateExerciseRequest(BaseModel):
    name: str
    primary_muscle: Optional[str] = None
    secondary_muscles: Optional[str] = None
    equipment: Optional[str] = None
    equipment_tag: Optional[str] = None  # alias للتوافق مع الواجهة
    brand: Optional[str] = None
    image_url: Optional[str] = None
    aliases: Optional[List[str]] = None


class UpdateExerciseRequest(BaseModel):
    name: Optional[str] = None
    primary_muscle: Optional[str] = None
    secondary_muscles: Optional[str] = None
    equipment: Optional[str] = None
    equipment_tag: Optional[str] = None
    brand: Optional[str] = None
    image_url: Optional[str] = None
    aliases: Optional[List[str]] = None
    is_active: Optional[bool] = None
