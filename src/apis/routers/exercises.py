from fastapi import APIRouter, HTTPException, status
from typing import List

from src.apis.schemas import (
    ExerciseDTO,
    CreateExerciseRequest,
    UpdateExerciseRequest,
    MessageResponse,
)
from src.infrastructure.db.connection import SessionLocal
from src.infrastructure.db.models import ExerciseTable
import uuid6

router = APIRouter(prefix="/api", tags=["exercises"])


def _to_dto(ex) -> ExerciseDTO:
    return ExerciseDTO(
        id=str(ex.id),
        name=ex.name,
        primary_muscle=ex.primary_muscle,
        equipment=ex.equipment,
        aliases=ex.aliases or [],
    )


@router.get("/exercises", response_model=List[ExerciseDTO])
def get_exercises(include_inactive: bool = False):
    """جلب قائمة التمارين. الافتراضي: التمارين النشطة فقط."""
    db = SessionLocal()
    try:
        stmt = db.query(ExerciseTable)
        if not include_inactive:
            stmt = stmt.filter(ExerciseTable.is_active == True)
        orm_exercises = stmt.order_by(ExerciseTable.name).all()
        return [_to_dto(ex) for ex in orm_exercises]
    finally:
        db.close()


@router.post("/exercises", response_model=ExerciseDTO, status_code=status.HTTP_201_CREATED)
def create_exercise(req: CreateExerciseRequest):
    """إضافة تمرين جديد."""
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="اسم التمرين مطلوب")

    db = SessionLocal()
    try:
        name = req.name.strip()

        # منع التكرار
        existing = db.query(ExerciseTable).filter(ExerciseTable.name == name).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"التمرين \'{name}\' موجود مسبقاً",
            )

        equipment = req.equipment or req.equipment_tag

        new_ex = ExerciseTable(
            id=str(uuid6.uuid7()),
            name=name,
            primary_muscle=req.primary_muscle,
            secondary_muscles=req.secondary_muscles,
            equipment=equipment,
            aliases=req.aliases or [],
            is_active=True,
        )
        db.add(new_ex)
        db.commit()
        db.refresh(new_ex)
        return _to_dto(new_ex)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"خطأ في الإضافة: {str(e)}")
    finally:
        db.close()


@router.put("/exercises/{exercise_id}", response_model=ExerciseDTO)
@router.patch("/exercises/{exercise_id}", response_model=ExerciseDTO)
def update_exercise(exercise_id: str, req: UpdateExerciseRequest):
    """تعديل تمرين موجود. يدعم PUT و PATCH."""
    db = SessionLocal()
    try:
        ex = db.query(ExerciseTable).filter(ExerciseTable.id == exercise_id).first()
        if not ex:
            raise HTTPException(status_code=404, detail="التمرين غير موجود")

        if req.name is not None:
            new_name = req.name.strip()
            if not new_name:
                raise HTTPException(status_code=400, detail="الاسم لا يمكن أن يكون فارغاً")
            dup = db.query(ExerciseTable).filter(
                ExerciseTable.name == new_name,
                ExerciseTable.id != exercise_id,
            ).first()
            if dup:
                raise HTTPException(status_code=409, detail=f"الاسم \'{new_name}\' مستخدم مسبقاً")
            ex.name = new_name

        if req.primary_muscle is not None:
            ex.primary_muscle = req.primary_muscle
        if req.secondary_muscles is not None:
            ex.secondary_muscles = req.secondary_muscles

        equipment = req.equipment or req.equipment_tag
        if equipment is not None:
            ex.equipment = equipment

        if req.aliases is not None:
            ex.aliases = req.aliases
        if req.is_active is not None:
            ex.is_active = req.is_active

        db.commit()
        db.refresh(ex)
        return _to_dto(ex)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"خطأ في التعديل: {str(e)}")
    finally:
        db.close()


@router.delete("/exercises/{exercise_id}", response_model=MessageResponse)
def delete_exercise(exercise_id: str, hard: bool = False):
    """حذف تمرين. الافتراضي soft delete (is_active=False).
    استخدم ?hard=true للحذف النهائي (تحذير: يفشل لو التمرين مستخدم في جلسات)."""
    db = SessionLocal()
    try:
        ex = db.query(ExerciseTable).filter(ExerciseTable.id == exercise_id).first()
        if not ex:
            raise HTTPException(status_code=404, detail="التمرين غير موجود")

        name = ex.name
        if hard:
            try:
                db.delete(ex)
                db.commit()
                return MessageResponse(message=f"تم حذف \'{name}\' نهائياً")
            except Exception as e:
                db.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="لا يمكن الحذف النهائي — التمرين مستخدم في جلسات سابقة. استخدم الحذف الناعم.",
                )
        else:
            ex.is_active = False
            db.commit()
            return MessageResponse(message=f"تم تعطيل \'{name}\'")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"خطأ في الحذف: {str(e)}")
    finally:
        db.close()
