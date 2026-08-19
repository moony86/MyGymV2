from fastapi import APIRouter, HTTPException, status, Depends
from typing import Optional, List
from decimal import Decimal
from datetime import date
import uuid6

from src.apis.schemas import (
    TrainingProfileDTO,
    UpsertTrainingProfileRequest,
    UpdateWeightRequest,
    BodyMeasurementDTO,
    AddBodyMeasurementRequest,
    ProfileDTO,
    CreateProfileRequest,
)
from src.services.training_profile_service import TrainingProfileService
from src.services.body_measurement_service import BodyMeasurementService
from src.infrastructure.db.connection import SessionLocal
from src.infrastructure.db.models import ProfileTable
from src.apis.deps import get_current_profile_id
from src.domain.training_profile_entity import TrainingProfile

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/profiles", response_model=List[ProfileDTO])
def list_profiles():
    db = SessionLocal()
    try:
        return [ProfileDTO(id=row.id, name=row.name) for row in db.query(ProfileTable).order_by(ProfileTable.created_at).all()]
    finally:
        db.close()


@router.post("/profiles", response_model=ProfileDTO)
def create_profile(req: CreateProfileRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile name is required")
    db = SessionLocal()
    try:
        row = ProfileTable(id=str(uuid6.uuid7()), name=name)
        db.add(row)
        db.commit()
        return ProfileDTO(id=row.id, name=row.name)
    finally:
        db.close()


def profile_to_dto(profile: TrainingProfile, warnings=None) -> TrainingProfileDTO:
    return TrainingProfileDTO(
        id=str(profile.id),
        sex=profile.sex.value,
        birth_year=profile.birth_year,
        age=profile.age,
        height_cm=profile.height_cm,
        current_weight_kg=profile.current_weight_kg,
        experience_level=profile.experience_level.value,
        training_days_per_week=profile.training_days_per_week,
        session_duration_minutes=profile.session_duration_minutes,
        primary_goal=profile.primary_goal.value,
        updated_at=profile.updated_at,
        warnings=[w.to_dict() for w in (warnings or [])],
    )


@router.get("/profile", response_model=TrainingProfileDTO)
def get_profile(profile_id: str = Depends(get_current_profile_id)):
    db = SessionLocal()
    try:
        service = TrainingProfileService(db, profile_id)
        profile = service.get_profile()
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No training profile has been created yet.",
            )
        warnings = service.get_warnings(profile)
        return profile_to_dto(profile, warnings)
    finally:
        db.close()


@router.put("/profile", response_model=TrainingProfileDTO)
def upsert_profile(req: UpsertTrainingProfileRequest, profile_id: str = Depends(get_current_profile_id)):
    db = SessionLocal()
    try:
        service = TrainingProfileService(db, profile_id)
        profile = service.create_or_update_profile(
            sex=req.sex,
            birth_year=req.birth_year,
            height_cm=req.height_cm,
            current_weight_kg=req.current_weight_kg,
            experience_level=req.experience_level,
            training_days_per_week=req.training_days_per_week,
            session_duration_minutes=req.session_duration_minutes,
            primary_goal=req.primary_goal,
        )
        db.commit()
        warnings = service.get_warnings(profile)
        return profile_to_dto(profile, warnings)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()


@router.patch("/profile/weight", response_model=TrainingProfileDTO)
def update_weight(req: UpdateWeightRequest, profile_id: str = Depends(get_current_profile_id)):
    db = SessionLocal()
    try:
        service = TrainingProfileService(db, profile_id)
        profile = service.update_weight(req.current_weight_kg)
        db.commit()
        return profile_to_dto(profile)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()


# ========== Body Measurements ==========

@router.get("/profile/measurements", response_model=List[BodyMeasurementDTO])
def get_body_measurements(limit: int = 30, profile_id: str = Depends(get_current_profile_id)):
    db = SessionLocal()
    try:
        service = BodyMeasurementService(db)
        measurements = service.get_history(profile_id, limit=limit)
        return [BodyMeasurementDTO.model_validate(m) for m in measurements]
    finally:
        db.close()


@router.get("/profile/measurements/latest", response_model=Optional[BodyMeasurementDTO])
def get_latest_body_measurement(profile_id: str = Depends(get_current_profile_id)):
    db = SessionLocal()
    try:
        service = BodyMeasurementService(db)
        measurement = service.get_latest(profile_id)
        if measurement is None:
            return None
        return BodyMeasurementDTO.model_validate(measurement)
    finally:
        db.close()


@router.post("/profile/measurements", response_model=BodyMeasurementDTO)
def add_body_measurement(req: AddBodyMeasurementRequest, profile_id: str = Depends(get_current_profile_id)):
    db = SessionLocal()
    try:
        service = BodyMeasurementService(db)
        measurement = service.add_measurement(
            profile_id=profile_id,
            date=date.fromisoformat(req.date),
            mtype=req.type,
            goal=req.goal,
            weight=req.weight,
            waist=req.waist,
            narrow_waist=req.narrow_waist,
            chest=req.chest,
            hips=req.hips,
            left_arm=req.left_arm,
            right_arm=req.right_arm,
            left_thigh=req.left_thigh,
            right_thigh=req.right_thigh,
            neck=req.neck,
            body_fat=req.body_fat,
            notes=req.notes,
            conditions=req.conditions,
            front_photo=req.front_photo,
            side_photo=req.side_photo,
            back_photo=req.back_photo,
        )
        db.commit()
        return BodyMeasurementDTO.model_validate(measurement)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()


@router.delete("/profile/measurements/{measurement_id}")
def delete_body_measurement(measurement_id: str, profile_id: str = Depends(get_current_profile_id)):
    db = SessionLocal()
    try:
        service = BodyMeasurementService(db)
        deleted = service.delete_measurement(measurement_id, profile_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Measurement not found",
            )
        db.commit()
        return {"message": "Measurement deleted successfully"}
    finally:
        db.close()
