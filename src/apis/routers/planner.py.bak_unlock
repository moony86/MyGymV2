import os
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.apis.deps import get_db
from src.infrastructure.db.models import (
    ExerciseTable,
    TrainingProfileTable,
)
from src.services.evaluator_service import EvaluatorService
from src.services.generator_service import GeneratorService
from src.services.planner_service import PlannerService

router = APIRouter(prefix="/api/planner", tags=["planner"])


EXPERIMENTAL_PLANNER_ENABLED = os.getenv(
    "MYGYM_ENABLE_EXPERIMENTAL_PLANNER",
    "false",
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
    order_index: int = Field(default=0, ge=0)
    target_sets: Optional[int] = Field(default=None, ge=1)
    target_reps: Optional[int] = Field(default=None, ge=1)
    target_weight_mode: str = "LAST_SESSION"
    fixed_weight: Optional[float] = Field(default=None, ge=0)
    fixed_reps: Optional[int] = Field(default=None, ge=1)
    rest_seconds: Optional[int] = Field(default=None, ge=0)


class PlanCreate(BaseModel):
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


def _get_service(db) -> PlannerService:
    # Current MyGymV2 uses the single default profile.
    return PlannerService(db)


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

    return PlanResponse(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        enabled=bool(plan.enabled),
        created_at=plan.created_at.isoformat(),
        exercises=[
            PlanExerciseResponse(
                id=pe.id,
                exercise_id=pe.exercise_id,
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
):
    profile = (
        db.query(TrainingProfileTable)
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=400,
            detail="أكمل البروفايل أولاً",
        )

    plans = GeneratorService(
        db
    ).generate_plan_for_profile(
        profile,
        template_id=template_id,
    )

    return {
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
):
    profile = (
        db.query(TrainingProfileTable)
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=400,
            detail="أكمل البروفايل أولاً",
        )

    return EvaluatorService(
        db
    ).evaluate_program(
        program_group_id,
        profile,
    )


@router.get("/evaluate-plan/{plan_id}")
def evaluate_single_plan(
    plan_id: str,
    db=Depends(get_db),
):
    """تقييم خطة واحدة — يعمل على أي خطة موجودة بدون feature flag."""
    profile = db.query(TrainingProfileTable).first()
    if not profile:
        raise HTTPException(status_code=400, detail="أكمل البروفايل أولاً")

    from src.infrastructure.db.models import WorkoutPlanTable
    target_plan = db.query(WorkoutPlanTable).filter(
        WorkoutPlanTable.id == plan_id
    ).first()

    if not target_plan:
        raise HTTPException(status_code=404, detail="الخطة غير موجودة")

    # إذا عنده program_group_id، استخدم المجموعة كاملة
    if target_plan.program_group_id:
        return EvaluatorService(db).evaluate_program(
            target_plan.program_group_id, profile
        )

    # خطة مفردة — نبني تقرير مباشرة
    from collections import defaultdict
    from src.infrastructure.db.models import ExerciseTable, PlanExerciseTable
    from src.apis.deps import get_knowledge_provider
    from src.services.evaluator_service import GOAL_TO_TRAINING_RULES

    provider = get_knowledge_provider()
    plan_exercises = db.query(PlanExerciseTable).filter(
        PlanExerciseTable.plan_id == plan_id
    ).all()

    muscle_volume = defaultdict(float)
    unresolved = []
    SECONDARY_WEIGHT = 0.5

    for pe in plan_exercises:
        exercise_row = db.query(ExerciseTable).filter(
            ExerciseTable.id == pe.exercise_id
        ).first()
        if not exercise_row or not exercise_row.knowledge_variant_id:
            unresolved.append(exercise_row.name if exercise_row else pe.exercise_id)
            continue
        try:
            variant = provider.variant(exercise_row.knowledge_variant_id)
            exercise = provider.exercise(variant.exercise)
        except Exception:
            unresolved.append(exercise_row.name)
            continue

        sets = pe.target_sets or 0
        for muscle_id in (exercise.primary_muscles or []):
            muscle_volume[muscle_id] += sets * 1.0
        for muscle_id in (exercise.secondary_muscles or []):
            muscle_volume[muscle_id] += sets * SECONDARY_WEIGHT

    group_volume = defaultdict(float)
    for muscle_id, volume in muscle_volume.items():
        muscle = provider.muscle(muscle_id)
        if muscle and getattr(muscle, "group", None):
            group_volume[muscle.group] += volume

    goal_key = GOAL_TO_TRAINING_RULES.get(profile.primary_goal, "hypertrophy")
    volume_rules = provider.training_rules["weekly_volume"][goal_key]
    coverage_rules = provider.training_rules["muscle_coverage"]

    def classify(vol, rules):
        if vol < rules["minimum_sets_per_muscle"]:
            return "below_minimum"
        if vol > rules["maximum_sets_per_muscle"]:
            return "above_maximum"
        return "ok"

    major_report = []
    for group_id in coverage_rules["major_muscles"]:
        vol = round(group_volume.get(group_id, 0.0), 1)
        major_report.append({
            "id": group_id,
            "weekly_sets": vol,
            "recommended_range": volume_rules["recommended_sets"],
            "status": classify(vol, volume_rules),
        })

    optional_report = []
    for muscle_id in coverage_rules["optional_muscles"]:
        vol = round(muscle_volume.get(muscle_id, 0.0), 1)
        optional_report.append({
            "id": muscle_id,
            "weekly_sets": vol,
            "recommended_range": volume_rules["recommended_sets"],
            "status": classify(vol, volume_rules),
        })

    overall = "PASS"
    if any(r["status"] == "below_minimum" for r in major_report):
        overall = "FAIL"
    elif any(r["status"] in ("below_minimum", "above_maximum")
             for r in major_report + optional_report):
        overall = "WARNING"

    return {
        "program_group_id": None,
        "plan_id": plan_id,
        "plan_name": target_plan.name,
        "days_count": 1,
        "goal": profile.primary_goal,
        "overall_status": overall,
        "major_muscles": major_report,
        "optional_muscles": optional_report,
        "unresolved_exercises": unresolved,
    }

