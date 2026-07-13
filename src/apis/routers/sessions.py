from fastapi import APIRouter, HTTPException, status
from typing import List, Any
from decimal import Decimal
import uuid

from src.apis.schemas import (
    StartWorkoutRequest, AddSetRequest, FinishWorkoutRequest, UpdateSetRequest,
    SessionDTO, SetDTO, ActiveSessionDTO, MessageResponse, ExerciseDTO
)
from src.services.session_service import SessionService
from src.services.units_service import WeightFormatter
from src.domain.entities import Set, Session
from src.domain.enums import SessionStatus, SetType
from src.infrastructure.db.models import ExerciseTable, SetTable, PerformedExerciseTable
from src.infrastructure.db.connection import SessionLocal

router = APIRouter(prefix="/api", tags=["workouts"])

def session_to_dto(session: Session, sets: List[Set], exercise_names: dict = None) -> SessionDTO:
    volume = sum((s.weight * s.reps for s in sets), Decimal("0"))
    duration_minutes = None
    if session.ended_at and session.started_at:
        delta = session.ended_at - session.started_at
        duration_minutes = int(delta.total_seconds() // 60)

    return SessionDTO(
        id=str(session.id),
        status=session.status,
        started_at=session.started_at,
        ended_at=session.ended_at,
        notes=session.notes,
        volume_kg=volume,
        sets_count=len(sets),
        duration_minutes=duration_minutes
    )

def set_to_dto(orm_set, exercise_name: str = "") -> SetDTO:
    return SetDTO(
        id=str(orm_set.id),
        performed_exercise_id=str(orm_set.performed_exercise_id),
        exercise_name=exercise_name,
        set_order=orm_set.set_order,
        weight=orm_set.weight,
        reps=orm_set.reps,
        rpe=orm_set.rpe,
        set_type=SetType(orm_set.set_type),
        volume_kg=orm_set.weight * orm_set.reps
    )


@router.post("/workouts/start", response_model=SessionDTO)
def start_workout(req: StartWorkoutRequest):
    db = SessionLocal()
    try:
        service = SessionService(db)
        session = service.create_session(req.notes)
        db.commit()
        return session_to_dto(session, [])
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()

@router.get("/workouts/active", response_model=ActiveSessionDTO)
def get_active_workout():
    db = SessionLocal()
    try:
        service = SessionService(db)
        session = service.get_active_session()
        if not session:
            return ActiveSessionDTO(session=None, sets=[], last_set=None, total_volume=Decimal("0"))
        
        orm_sets = service.get_session_sets(session.id)
        
        exercise_names = {}
        for orm_set in orm_sets:
            pe = db.query(PerformedExerciseTable).filter(PerformedExerciseTable.id == orm_set.performed_exercise_id).first()
            if pe:
                ex = db.query(ExerciseTable).filter(ExerciseTable.id == pe.exercise_id).first()
                if ex:
                    exercise_names[str(orm_set.performed_exercise_id)] = ex.name
        
        sets_dto = [set_to_dto(s, exercise_names.get(str(s.performed_exercise_id), "")) for s in orm_sets]
        total_volume = sum((s.volume_kg for s in sets_dto), Decimal("0"))
        
        last_set_dto = None
        if orm_sets:
            last_set = orm_sets[-1]
            last_set_dto = set_to_dto(last_set, exercise_names.get(str(last_set.performed_exercise_id), ""))
        
        return ActiveSessionDTO(
            session=session_to_dto(session, orm_sets),
            sets=sets_dto,
            last_set=last_set_dto,
            total_volume=total_volume
        )
    finally:
        db.close()

@router.get("/workouts/history", response_model=list[SessionDTO])
def get_workout_history():
    db = SessionLocal()
    try:
        service = SessionService(db)

        sessions = service.get_completed_sessions()

        result = []

        for session in sessions:
            sets = service.get_session_sets(session.id)
            result.append(session_to_dto(session, sets))

        return result

    finally:
        db.close()

@router.get("/workouts/{session_id}", response_model=ActiveSessionDTO)
def get_workout(session_id: str):
    db = SessionLocal()
    try:
        service = SessionService(db)
        session, orm_sets = service.get_session_with_details(uuid.UUID(session_id))
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        
        exercise_names = {}
        for orm_set in orm_sets:
            pe = db.query(PerformedExerciseTable).filter(PerformedExerciseTable.id == orm_set.performed_exercise_id).first()
            if pe:
                ex = db.query(ExerciseTable).filter(ExerciseTable.id == pe.exercise_id).first()
                if ex:
                    exercise_names[str(orm_set.performed_exercise_id)] = ex.name
        
        sets_dto = [set_to_dto(s, exercise_names.get(str(s.performed_exercise_id), "")) for s in orm_sets]
        total_volume = sum((s.volume_kg for s in sets_dto), Decimal("0"))
        
        last_set_dto = None
        if orm_sets:
            last_set = orm_sets[-1]
            last_set_dto = set_to_dto(last_set, exercise_names.get(str(last_set.performed_exercise_id), ""))
        
        return ActiveSessionDTO(
            session=session_to_dto(session, orm_sets),
            sets=sets_dto,
            last_set=last_set_dto,
            total_volume=total_volume
        )
    finally:
        db.close()

@router.post("/workouts/{session_id}/sets", response_model=SetDTO)
def add_set(session_id: str, req: AddSetRequest):
    db = SessionLocal()
    try:
        service = SessionService(db)
        orm_set = service.add_set(
            session_id=uuid.UUID(session_id),
            exercise_id=uuid.UUID(req.exercise_id),
            weight=req.weight,
            reps=req.reps,
            set_order=req.set_order,
            set_type=req.set_type,
            rpe=req.rpe,
            notes=req.notes
        )
        db.commit()
        
        pe = db.query(PerformedExerciseTable).filter(PerformedExerciseTable.id == str(orm_set.performed_exercise_id)).first()
        exercise_name = ""
        if pe:
            ex = db.query(ExerciseTable).filter(ExerciseTable.id == pe.exercise_id).first()
            if ex:
                exercise_name = ex.name
        
        return set_to_dto(orm_set, exercise_name)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()

@router.patch("/sets/{set_id}", response_model=SetDTO)
def update_set(set_id: str, req: UpdateSetRequest):
    db = SessionLocal()
    try:
        service = SessionService(db)
        orm_set = service.update_set(
            set_id=uuid.UUID(set_id),
            weight=req.weight,
            reps=req.reps,
            set_type=req.set_type,
            rpe=req.rpe
        )
        db.commit()
        
        pe = db.query(PerformedExerciseTable).filter(PerformedExerciseTable.id == str(orm_set.performed_exercise_id)).first()
        exercise_name = ""
        if pe:
            ex = db.query(ExerciseTable).filter(ExerciseTable.id == pe.exercise_id).first()
            if ex:
                exercise_name = ex.name
        
        return set_to_dto(orm_set, exercise_name)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()

@router.delete("/sets/{set_id}", response_model=MessageResponse)
def delete_set(set_id: str):
    db = SessionLocal()
    try:
        service = SessionService(db)
        service.delete_set(uuid.UUID(set_id))
        db.commit()
        return MessageResponse(message="Set deleted successfully")
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()

@router.post("/workouts/{session_id}/finish", response_model=SessionDTO)
def finish_workout(session_id: str):
    db = SessionLocal()
    try:
        service = SessionService(db)
        session = service.finish_session(uuid.UUID(session_id))
        db.commit()
        return session_to_dto(session, [])
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()

@router.post("/workouts/{session_id}/abandon", response_model=SessionDTO)
def abandon_workout(session_id: str):
    db = SessionLocal()
    try:
        service = SessionService(db)
        session = service.abandon_session(uuid.UUID(session_id))
        db.commit()
        return session_to_dto(session, [])
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()

@router.get("/workouts/{session_id}/last-set", response_model=SetDTO)
def get_last_set(session_id: str, exercise_id: str):
    db = SessionLocal()
    try:
        service = SessionService(db)
        orm_set = service.get_last_set(uuid.UUID(session_id), uuid.UUID(exercise_id))
        if not orm_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No sets found for this exercise")
        
        pe = db.query(PerformedExerciseTable).filter(PerformedExerciseTable.id == str(orm_set.performed_exercise_id)).first()
        exercise_name = ""
        if pe:
            ex = db.query(ExerciseTable).filter(ExerciseTable.id == pe.exercise_id).first()
            if ex:
                exercise_name = ex.name
        
        return set_to_dto(orm_set, exercise_name)
    finally:
        db.close()

@router.delete("/workouts/{session_id}", response_model=MessageResponse)
def delete_workout(session_id: str):
    db = SessionLocal()
    try:
        service = SessionService(db)
        service.delete_session(uuid.UUID(session_id))
        db.commit()
        return MessageResponse(message="تم حذف الجلسة بنجاح")
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()
