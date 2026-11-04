import os
from decimal import Decimal
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

from src.apis.deps import get_db
from src.domain.profile_context import get_current_profile_id
from src.infrastructure.db.models import (
    ExerciseTable,
    TrainingProfileTable,
)
from src.services.evaluator_service import EvaluatorService, ProgramNotFoundError
from src.services.generator_service import GeneratorService, NoSuitableTemplateError
from src.services.planner_service import PlannerService
from src.services.plan_options import get_options, save_options

router = APIRouter(prefix="/api/planner", tags=["planner"])


EXPERIMENTAL_PLANNER_ENABLED = os.getenv(
    "MYGYM_ENABLE_EXPERIMENTAL_PLANNER",
    "true",
).lower() in {"1", "true", "yes"}


def require_experimental_planner():
    if not EXPERIMENTAL_PLANNER_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class PlanExerciseCreate(BaseModel):
    exercise_id: str
    alternative_exercise_id: Optional[str] = None
    order_index: int = Field(default=0, ge=0)
    target_sets: Optional[int] = Field(default=None, ge=1)
    target_reps: Optional[int] = Field(default=None, ge=1)
    target_weight_mode: str = "LAST_SESSION"
    fixed_weight: Optional[float] = Field(default=None, ge=0)
    fixed_reps: Optional[int] = Field(default=None, ge=1)
    rest_seconds: Optional[int] = Field(default=None, ge=0)


class SchedulePayload(BaseModel):
    schedule_type: Literal['manual','weekly','interval']
    days_of_week: List[int] = Field(default_factory=list)
    workout_days: Optional[int] = Field(default=1,ge=1,le=7)
    rest_days: Optional[int] = Field(default=0,ge=0,le=7)

    @field_validator('days_of_week')
    @classmethod
    def validate_days(cls, value):
        if any(day<0 or day>6 for day in value):raise ValueError('Weekdays must be 0 to 6, Monday first')
        return sorted(set(value))

    @model_validator(mode='after')
    def validate_schedule(self):
        if self.schedule_type=='weekly' and not self.days_of_week:raise ValueError('Select at least one weekday')
        if self.schedule_type=='interval' and (self.workout_days is None or self.rest_days is None):raise ValueError('Work and rest days are required')
        return self

class PlanCreate(BaseModel):
    schedules: Optional[List[SchedulePayload]] = None
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    exercises: List[PlanExerciseCreate] = Field(
        default_factory=list
    )


class ScheduleCreate(BaseModel):
    schedule_type: str = "manual"
    interval_days: Optional[int] = Field(
        default=None,
        ge=1,
    )
    days_mask: Optional[int] = Field(
        default=None,
        ge=0,
        le=127,
    )


class PlanExerciseResponse(BaseModel):
    alternative_exercise_id: Optional[str] = None
    alternative_exercise_name: Optional[str] = None
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
    generation: Optional[dict] = None
    schedules: List[dict] = Field(default_factory=list)
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


def _get_service(db) -> PlannerService:
    # Bind every plan operation to the authenticated request context.
    return PlannerService(db, profile_id=get_current_profile_id())


def _plan_response(
    service: PlannerService,
    plan_id: str,
) -> PlanResponse:
    data = service.get_plan_with_details(plan_id)

    plan = data.get("plan")
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    exercises = data.get("exercises", [])
    names = data.get("exercise_names", {})
    options = get_options(service.db,plan)
    alternatives = options.get('alternatives',{})
    alternative_names = {row.id:row.name for row in service.db.query(ExerciseTable).filter(ExerciseTable.id.in_(list(alternatives.values()))).all()}

    return PlanResponse(
        schedules=options.get("schedules",[]),
        generation=options.get("generation"),
        id=plan.id,
        name=plan.name,
        description=plan.description,
        enabled=bool(plan.enabled),
        created_at=plan.created_at.isoformat(),
        exercises=[
            PlanExerciseResponse(
                id=pe.id,
                exercise_id=pe.exercise_id,
                alternative_exercise_id=alternatives.get(pe.exercise_id),
                alternative_exercise_name=alternative_names.get(alternatives.get(pe.exercise_id)),
                exercise_name=names.get(
                    pe.exercise_id,
                    "Unknown",
                ),
                order_index=pe.order_index,
                target_sets=pe.target_sets,
                target_reps=pe.target_reps,
                target_weight_mode=pe.target_weight_mode,
                fixed_weight=(
                    float(pe.fixed_weight)
                    if pe.fixed_weight is not None
                    else None
                ),
                fixed_reps=pe.fixed_reps,
                rest_seconds=pe.rest_seconds,
            )
            for pe in exercises
        ],
    )


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

@router.get(
    "/plans",
    response_model=List[PlanResponse],
)
def get_all_plans(db=Depends(get_db)):
    service = _get_service(db)
    plans = service.get_all_plans()

    return [
        _plan_response(service, plan.id)
        for plan in plans
    ]


@router.post(
    "/plans",
    response_model=PlanResponse,
)
def create_plan(
    req: PlanCreate,
    db=Depends(get_db),
):
    service = _get_service(db)

    try:
        plan = service.create_plan(
            req.name,
            req.description,
        )

        for ex in req.exercises:
            service.add_exercise_to_plan(
                plan_id=plan.id,
                exercise_id=ex.exercise_id,
                order_index=ex.order_index,
                target_sets=ex.target_sets,
                target_reps=ex.target_reps,
                target_weight_mode=(
                    ex.target_weight_mode
                ),
                fixed_weight=(
                    Decimal(str(ex.fixed_weight))
                    if ex.fixed_weight is not None
                    else None
                ),
                fixed_reps=ex.fixed_reps,
                rest_seconds=ex.rest_seconds,
            )

        save_options(db,plan,req.exercises,req.schedules)
        db.commit()

        return _plan_response(
            service,
            plan.id,
        )

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/plans/{plan_id}",
    response_model=PlanResponse,
)
def get_plan(
    plan_id: str,
    db=Depends(get_db),
):
    service = _get_service(db)
    return _plan_response(
        service,
        plan_id,
    )


@router.put(
    "/plans/{plan_id}",
    response_model=PlanResponse,
)
def update_plan(
    plan_id: str,
    req: PlanCreate,
    db=Depends(get_db),
):
    service = _get_service(db)

    try:
        exercises_payload = [
            {
                "exercise_id": ex.exercise_id,
                "order_index": ex.order_index,
                "target_sets": ex.target_sets,
                "target_reps": ex.target_reps,
                "target_weight_mode": (
                    ex.target_weight_mode
                ),
                "fixed_weight": (
                    Decimal(str(ex.fixed_weight))
                    if ex.fixed_weight is not None
                    else None
                ),
                "fixed_reps": ex.fixed_reps,
                "rest_seconds": ex.rest_seconds,
            }
            for ex in req.exercises
        ]

        updated = service.update_plan(
            plan_id=plan_id,
            name=req.name,
            description=req.description,
            exercises=exercises_payload,
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found",
            )

        save_options(db,updated,req.exercises,req.schedules)
        db.commit()

        return _plan_response(
            service,
            plan_id,
        )

    except HTTPException:
        db.rollback()
        raise

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.put(
    "/plans/{plan_id}/toggle",
    response_model=dict,
)
def toggle_plan(
    plan_id: str,
    enabled: bool = True,
    db=Depends(get_db),
):
    service = _get_service(db)

    result = service.enable_plan(
        plan_id,
        enabled,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    db.commit()

    return {
        "message": (
            "Plan enabled successfully"
            if enabled
            else "Plan disabled successfully"
        )
    }


@router.delete(
    "/plans/{plan_id}",
    response_model=dict,
)
def delete_plan(
    plan_id: str,
    db=Depends(get_db),
):
    service = _get_service(db)

    deleted = service.delete_plan(plan_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    db.commit()

    return {"message": "Plan deleted successfully"}


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

@router.get(
    "/today",
    response_model=Optional[PlanResponse],
)
def get_today_plan(
    db=Depends(get_db),
):
    service = _get_service(db)

    plan_data = service.get_today_plan()

    if not plan_data:
        return None

    return _plan_response(
        service,
        plan_data["plan"].id,
    )


@router.post(
    "/plans/{plan_id}/schedule",
    response_model=dict,
)
def add_schedule(
    plan_id: str,
    req: ScheduleCreate,
    db=Depends(get_db),
):
    service = _get_service(db)

    try:
        schedule = service.add_schedule(
            plan_id=plan_id,
            schedule_type=req.schedule_type,
            interval_days=req.interval_days,
            days_mask=req.days_mask,
        )

        db.commit()

        return {
            "message": "Schedule added successfully",
            "schedule_id": schedule.id,
        }

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# Planned sessions
# ---------------------------------------------------------------------------

@router.post(
    "/plans/{plan_id}/start",
    response_model=StartPlanResponse,
)
def start_planned_session(
    plan_id: str,
    notes: Optional[str] = None,
    db=Depends(get_db),
):
    service = _get_service(db)

    try:
        result = service.start_planned_session(
            plan_id,
            notes,
        )

        db.commit()

        return StartPlanResponse(
            session_id=result["session_id"],
            planned_exercises=[
                PlannedExercise(
                    plan_exercise_id=ex[
                        "plan_exercise_id"
                    ],
                    exercise_id=ex["exercise_id"],
                    name=ex["name"],
                    order=ex["order"],
                    target_sets=ex["target_sets"],
                    target_reps=ex["target_reps"],
                    suggested_weight=(
                        float(ex["suggested_weight"])
                        if ex["suggested_weight"]
                        is not None
                        else None
                    ),
                    suggested_reps=ex[
                        "suggested_reps"
                    ],
                    rest_seconds=ex[
                        "rest_seconds"
                    ],
                    is_completed=ex[
                        "is_completed"
                    ],
                )
                for ex in result[
                    "planned_exercises"
                ]
            ],
        )

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/sessions/{session_id}/progress",
    response_model=StartPlanResponse,
)
def get_session_plan_progress(
    session_id: str,
    db=Depends(get_db),
):
    service = _get_service(db)

    try:
        result = service.get_session_plan_progress(
            session_id
        )

        return StartPlanResponse(
            session_id=result["session_id"],
            planned_exercises=[
                PlannedExercise(
                    plan_exercise_id=ex[
                        "plan_exercise_id"
                    ],
                    exercise_id=ex["exercise_id"],
                    name=ex["name"],
                    order=ex["order"],
                    target_sets=ex["target_sets"],
                    target_reps=ex["target_reps"],
                    suggested_weight=(
                        float(ex["suggested_weight"])
                        if ex["suggested_weight"]
                        is not None
                        else None
                    ),
                    suggested_reps=ex[
                        "suggested_reps"
                    ],
                    rest_seconds=ex[
                        "rest_seconds"
                    ],
                    is_completed=ex[
                        "is_completed"
                    ],
                )
                for ex in result[
                    "planned_exercises"
                ]
            ],
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# Alternatives
# ---------------------------------------------------------------------------

@router.get(
    "/exercises/{exercise_id}/alternatives",
    response_model=List[AlternativeResponse],
)
def get_alternatives(
    exercise_id: str,
    db=Depends(get_db),
):
    service = _get_service(db)

    alts = service.get_alternatives(
        exercise_id
    )

    result = []

    for alt in alts:
        alt_ex = (
            db.query(ExerciseTable)
            .filter(
                ExerciseTable.id
                == alt.alternative_exercise_id
            )
            .first()
        )

        result.append(
            AlternativeResponse(
                id=alt.id,
                exercise_id=alt.exercise_id,
                alternative_exercise_id=(
                    alt.alternative_exercise_id
                ),
                alternative_name=(
                    alt_ex.name
                    if alt_ex
                    else "Unknown"
                ),
            )
        )

    return result


@router.post(
    "/alternatives",
    response_model=AlternativeResponse,
)
def add_alternative(
    exercise_id: str,
    alternative_exercise_id: str,
    db=Depends(get_db),
):
    service = _get_service(db)

    try:
        alt = service.add_alternative(
            exercise_id,
            alternative_exercise_id,
        )

        db.commit()

        alt_ex = (
            db.query(ExerciseTable)
            .filter(
                ExerciseTable.id
                == alt.alternative_exercise_id
            )
            .first()
        )

        return AlternativeResponse(
            id=alt.id,
            exercise_id=alt.exercise_id,
            alternative_exercise_id=(
                alt.alternative_exercise_id
            ),
            alternative_name=(
                alt_ex.name
                if alt_ex
                else "Unknown"
            ),
        )

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.delete(
    "/alternatives/{alternative_id}",
    response_model=dict,
)
def delete_alternative(
    alternative_id: str,
    db=Depends(get_db),
):
    service = _get_service(db)

    deleted = service.remove_alternative(
        alternative_id
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alternative not found",
        )

    db.commit()

    return {"message": "Alternative deleted successfully"}


# ---------------------------------------------------------------------------
# Experimental planner endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/generate",
    dependencies=[
        Depends(require_experimental_planner)
    ],
)
def generate_plan(
    template_id: Optional[str] = None,
    db=Depends(get_db),
    profile_id: str = Depends(get_current_profile_id),
):
    profile = (
        db.query(TrainingProfileTable)
        .filter(TrainingProfileTable.id == profile_id)
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=400,
            detail="أكمل البروفايل أولاً",
        )

    from src.services.coaching import preferences
    if preferences(db,profile_id) is None:raise HTTPException(status_code=409,detail={'code':'preferences_required','message':'Complete coaching setup before generating a new program'})
    service=GeneratorService(db)
    try:
        plans=service.generate_plan_for_profile(profile,template_id=template_id)
    except (ValueError, NoSuitableTemplateError) as error:
        db.rollback()
        raise HTTPException(status_code=400,detail=str(error))


    return {
        "generation": service.report,
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "day_index": p.day_index,
            }
            for p in plans
        ]
    }


@router.get(
    "/evaluate/{program_group_id}",
    dependencies=[
        Depends(require_experimental_planner)
    ],
)
def evaluate_program(
    program_group_id: str,
    db=Depends(get_db),
    profile_id: str = Depends(get_current_profile_id),
):
    profile = (
        db.query(TrainingProfileTable)
        .filter(TrainingProfileTable.id == profile_id)
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=400,
            detail="أكمل البروفايل أولاً",
        )

    try:
        return EvaluatorService(db).evaluate_program(program_group_id, profile)
    except ProgramNotFoundError:
        raise HTTPException(status_code=404, detail="Program not found")


@router.get("/evaluate-plan/{plan_id}")
def evaluate_single_plan(
    plan_id: str,
    db=Depends(get_db),
    profile_id: str = Depends(get_current_profile_id),
):
    """تقييم خطة واحدة — يعمل على أي خطة موجودة بدون feature flag."""
    profile = db.query(TrainingProfileTable).filter(
        TrainingProfileTable.id == profile_id
    ).first()
    if not profile:
        raise HTTPException(status_code=400, detail="أكمل البروفايل أولاً")

    from src.infrastructure.db.models import WorkoutPlanTable
    target_plan = db.query(WorkoutPlanTable).filter(
        WorkoutPlanTable.id == plan_id,
        WorkoutPlanTable.profile_id == profile_id
    ).first()

    if not target_plan:
        raise HTTPException(status_code=404, detail="الخطة غير موجودة")

    # إذا عنده program_group_id، استخدم المجموعة كاملة
    if target_plan.program_group_id:
        return EvaluatorService(db).evaluate_program(
            target_plan.program_group_id, profile
        )

    return EvaluatorService(db).evaluate_plans([target_plan],profile)
