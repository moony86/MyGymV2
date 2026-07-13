from fastapi import APIRouter, HTTPException
from typing import List

from src.apis.schemas import ExerciseDTO
from src.services.session_service import SessionService
from src.infrastructure.db.connection import SessionLocal

router = APIRouter(prefix="/api", tags=["exercises"])

@router.get("/exercises", response_model=List[ExerciseDTO])
def get_exercises():
    db = SessionLocal()
    try:
        service = SessionService(db)
        orm_exercises = service.get_all_exercises()
        return [
            ExerciseDTO(
                id=str(ex.id),
                name=ex.name,
                primary_muscle=ex.primary_muscle,
                equipment=ex.equipment,
                aliases=ex.aliases or []
            )
            for ex in orm_exercises
        ]
    finally:
        db.close()
