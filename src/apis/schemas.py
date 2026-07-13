from pydantic import BaseModel, field_validator
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from src.domain.enums import SessionStatus, SetType

def serialize_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

class SessionDTO(BaseModel):
    id: str
    status: SessionStatus
    started_at: datetime
    ended_at: Optional[datetime] = None
    notes: Optional[str] = None
    volume_kg: Decimal = Decimal("0")
    sets_count: int = 0

    @field_validator('volume_kg', mode='before')
    @classmethod
    def serialize_volume(cls, v):
        if isinstance(v, Decimal):
            return serialize_decimal(v)
        return v

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
