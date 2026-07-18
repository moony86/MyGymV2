from pydantic import BaseModel, field_validator, field_serializer
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from src.domain.enums import SessionStatus, SetType

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
    weight: Decimal
    reps: int
    set_order: Optional[int] = None
    set_type: SetType = SetType.WORKING
    rpe: Optional[float] = None
    notes: Optional[str] = None

class FinishWorkoutRequest(BaseModel):
    session_id: str

class UpdateSetRequest(BaseModel):
    weight: Optional[Decimal] = None
    reps: Optional[int] = None
    set_type: Optional[SetType] = None
    rpe: Optional[float] = None
