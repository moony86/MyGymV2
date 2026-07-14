from fastapi import APIRouter, HTTPException, status
from typing import List, Optional
from decimal import Decimal
from pydantic import BaseModel

from src.infrastructure.db.connection import SessionLocal
from src.services.planner_service import PlannerService

router = APIRouter(prefix="/api/planner", tags=["planner"])

# ========== Pydantic Schemas ==========

class PlanExerciseCreate(BaseModel):
    exercise_id: str
    order_index: int
    target_sets: Optional[int] = None
    target_reps: Optional[int] = None
    target_weight_mode: str = "LAST_SESSION"
    fixed_weight: Optional[float] = None
    fixed_reps: Optional[int] = None
    rest_seconds: Optional[int] = None


class PlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    exercises: List[PlanExerciseCreate]


class ScheduleCreate(BaseModel):
    schedule_type: str = "manual"  # 'weekly', 'interval', 'manual'
    interval_days: Optional[int] = None
    days_mask: Optional[int] = None


class PlanExerciseResponse(BaseModel):
    id: str
    exercise_id: str
    exercise_name: str
    order_index: int
    target_sets: Optional[int]
    target_reps: Optional[int]
    target_weight_mode: str
    fixed_weight: Optional[float]
    fixed_reps: Optional[int]
    rest_seconds: Optional[int]


class PlanResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    enabled: bool
    created_at: str
    exercises: List[PlanExerciseResponse]


class PlannedExercise(BaseModel):
    plan_exercise_id: str
    exercise_id: str
    name: str
    order: int
    target_sets: Optional[int]
    target_reps: Optional[int]
    suggested_weight: Optional[float]
    suggested_reps: Optional[int]
    rest_seconds: Optional[int]
    is_completed: bool


class StartPlanResponse(BaseModel):
    session_id: str
    planned_exercises: List[PlannedExercise]


class AlternativeResponse(BaseModel):
    id: str
    exercise_id: str
    alternative_exercise_id: str
    alternative_name: str


# ========== نقاط النهاية ==========

@router.get("/plans", response_model=List[PlanResponse])
def get_all_plans():
    db = SessionLocal()
    try:
        service = PlannerService(db)
        plans = service.get_all_plans()
        result = []
        for plan in plans:
            data = service.get_plan_with_details(plan.id)
            exercises = data.get("exercises", [])
            names = data.get("exercise_names", {})
            result.append(PlanResponse(
                id=plan.id,
                name=plan.name,
                description=plan.description,
                enabled=plan.enabled,
                created_at=plan.created_at.isoformat(),
                exercises=[
                    PlanExerciseResponse(
                        id=pe.id,
                        exercise_id=pe.exercise_id,
                        exercise_name=names.get(pe.exercise_id, "Unknown"),
                        order_index=pe.order_index,
                        target_sets=pe.target_sets,
                        target_reps=pe.target_reps,
                        target_weight_mode=pe.target_weight_mode,
                        fixed_weight=float(pe.fixed_weight) if pe.fixed_weight is not None else None,
                        fixed_reps=pe.fixed_reps,
                        rest_seconds=pe.rest_seconds,
                    )
                    for pe in exercises
                ]
            ))
        return result
    finally:
        db.close()


@router.post("/plans", response_model=PlanResponse)
def create_plan(req: PlanCreate):
    db = SessionLocal()
    try:
        service = PlannerService(db)
        plan = service.create_plan(req.name, req.description)

        for ex in req.exercises:
            service.add_exercise_to_plan(
                plan_id=plan.id,
                exercise_id=ex.exercise_id,
                order_index=ex.order_index,
                target_sets=ex.target_sets,
                target_reps=ex.target_reps,
                target_weight_mode=ex.target_weight_mode,
                fixed_weight=Decimal(str(ex.fixed_weight)) if ex.fixed_weight is not None else None,
                fixed_reps=ex.fixed_reps,
                rest_seconds=ex.rest_seconds,
            )

        db.commit()

        data = service.get_plan_with_details(plan.id)
        exercises = data.get("exercises", [])
        names = data.get("exercise_names", {})

        return PlanResponse(
            id=plan.id,
            name=plan.name,
            description=plan.description,
            enabled=plan.enabled,
            created_at=plan.created_at.isoformat(),
            exercises=[
                PlanExerciseResponse(
                    id=pe.id,
                    exercise_id=pe.exercise_id,
                    exercise_name=names.get(pe.exercise_id, "Unknown"),
                    order_index=pe.order_index,
                    target_sets=pe.target_sets,
                    target_reps=pe.target_reps,
                    target_weight_mode=pe.target_weight_mode,
                    fixed_weight=float(pe.fixed_weight) if pe.fixed_weight is not None else None,
                    fixed_reps=pe.fixed_reps,
                    rest_seconds=pe.rest_seconds,
                )
                for pe in exercises
            ]
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()


@router.get("/plans/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: str):
    db = SessionLocal()
    try:
        service = PlannerService(db)
        plan = service.get_plan_by_id(plan_id)
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

        data = service.get_plan_with_details(plan_id)
        exercises = data.get("exercises", [])
        names = data.get("exercise_names", {})

        return PlanResponse(
            id=plan.id,
            name=plan.name,
            description=plan.description,
            enabled=plan.enabled,
            created_at=plan.created_at.isoformat(),
            exercises=[
                PlanExerciseResponse(
                    id=pe.id,
                    exercise_id=pe.exercise_id,
                    exercise_name=names.get(pe.exercise_id, "Unknown"),
                    order_index=pe.order_index,
                    target_sets=pe.target_sets,
                    target_reps=pe.target_reps,
                    target_weight_mode=pe.target_weight_mode,
                    fixed_weight=float(pe.fixed_weight) if pe.fixed_weight is not None else None,
                    fixed_reps=pe.fixed_reps,
                    rest_seconds=pe.rest_seconds,
                )
                for pe in exercises
            ]
        )
    finally:
        db.close()


@router.put("/plans/{plan_id}/toggle", response_model=dict)
def toggle_plan(plan_id: str, enabled: bool = True):
    db = SessionLocal()
    try:
        service = PlannerService(db)
        result = service.enable_plan(plan_id, enabled)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
        db.commit()
        return {"message": f"Plan {'enabled' if enabled else 'disabled'} successfully"}
    finally:
        db.close()


@router.delete("/plans/{plan_id}", response_model=dict)
def delete_plan(plan_id: str):
    db = SessionLocal()
    try:
        service = PlannerService(db)
        deleted = service.delete_plan(plan_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
        db.commit()
        return {"message": "Plan deleted successfully"}
    finally:
        db.close()


# ========== الجدولة ==========

@router.get("/today", response_model=Optional[PlanResponse])
def get_today_plan():
    db = SessionLocal()
    try:
        service = PlannerService(db)
        plan_data = service.get_today_plan()
        if not plan_data:
            return None
        plan = plan_data["plan"]
        exercises = plan_data.get("exercises", [])
        names = plan_data.get("exercise_names", {})
        return PlanResponse(
            id=plan.id,
            name=plan.name,
            description=plan.description,
            enabled=plan.enabled,
            created_at=plan.created_at.isoformat(),
            exercises=[
                PlanExerciseResponse(
                    id=pe.id,
                    exercise_id=pe.exercise_id,
                    exercise_name=names.get(pe.exercise_id, "Unknown"),
                    order_index=pe.order_index,
                    target_sets=pe.target_sets,
                    target_reps=pe.target_reps,
                    target_weight_mode=pe.target_weight_mode,
                    fixed_weight=float(pe.fixed_weight) if pe.fixed_weight is not None else None,
                    fixed_reps=pe.fixed_reps,
                    rest_seconds=pe.rest_seconds,
                )
                for pe in exercises
            ]
        )
    finally:
        db.close()


@router.post("/plans/{plan_id}/schedule", response_model=dict)
def add_schedule(plan_id: str, req: ScheduleCreate):
    db = SessionLocal()
    try:
        service = PlannerService(db)
        schedule = service.add_schedule(
            plan_id=plan_id,
            schedule_type=req.schedule_type,
            interval_days=req.interval_days,
            days_mask=req.days_mask,
        )
        db.commit()
        return {"message": "Schedule added successfully", "schedule_id": schedule.id}
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()


# ========== تنفيذ الخطة ==========

@router.post("/plans/{plan_id}/start", response_model=StartPlanResponse)
def start_planned_session(plan_id: str, notes: Optional[str] = None):
    db = SessionLocal()
    try:
        service = PlannerService(db)
        result = service.start_planned_session(plan_id, notes)
        return StartPlanResponse(
            session_id=result["session_id"],
            planned_exercises=[
                PlannedExercise(
                    plan_exercise_id=ex["plan_exercise_id"],
                    exercise_id=ex["exercise_id"],
                    name=ex["name"],
                    order=ex["order"],
                    target_sets=ex["target_sets"],
                    target_reps=ex["target_reps"],
                    suggested_weight=float(ex["suggested_weight"]) if ex["suggested_weight"] is not None else None,
                    suggested_reps=ex["suggested_reps"],
                    rest_seconds=ex["rest_seconds"],
                    is_completed=ex["is_completed"],
                )
                for ex in result["planned_exercises"]
            ]
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()


# ========== البدائل ==========

@router.get("/exercises/{exercise_id}/alternatives", response_model=List[AlternativeResponse])
def get_alternatives(exercise_id: str):
    db = SessionLocal()
    try:
        service = PlannerService(db)
        alts = service.get_alternatives(exercise_id)
        result = []
        for alt in alts:
            alt_ex = db.query(ExerciseTable).filter(ExerciseTable.id == alt.alternative_exercise_id).first()
            result.append(AlternativeResponse(
                id=alt.id,
                exercise_id=alt.exercise_id,
                alternative_exercise_id=alt.alternative_exercise_id,
                alternative_name=alt_ex.name if alt_ex else "Unknown",
            ))
        return result
    finally:
        db.close()


@router.post("/alternatives", response_model=AlternativeResponse)
def add_alternative(exercise_id: str, alternative_exercise_id: str):
    db = SessionLocal()
    try:
        service = PlannerService(db)
        alt = service.add_alternative(exercise_id, alternative_exercise_id)
        db.commit()
        alt_ex = db.query(ExerciseTable).filter(ExerciseTable.id == alt.alternative_exercise_id).first()
        return AlternativeResponse(
            id=alt.id,
            exercise_id=alt.exercise_id,
            alternative_exercise_id=alt.alternative_exercise_id,
            alternative_name=alt_ex.name if alt_ex else "Unknown",
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        db.close()


@router.delete("/alternatives/{alternative_id}", response_model=dict)
def delete_alternative(alternative_id: str):
    db = SessionLocal()
    try:
        service = PlannerService(db)
        deleted = service.remove_alternative(alternative_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alternative not found")
        db.commit()
        return {"message": "Alternative deleted successfully"}
    finally:
        db.close()