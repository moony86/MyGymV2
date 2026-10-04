"""
Analytics Router
================
API endpoints للتحليل:
- /api/analytics/overview
- /api/analytics/muscle-balance
- /api/analytics/plateaus
- /api/analytics/effort
- /api/analytics/trends
- /api/analytics/exercises (قائمة للاختيار)
- /api/analytics/exercise/{id} (Deep Dive)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DbSession

from src.apis.deps import get_db, get_current_profile_id
from src.queries.analytics_queries import (
    get_available_exercises,
    get_effort_analysis,
    get_exercise_prs,
    get_exercise_sessions,
    get_exercise_trend,
    get_muscle_balance,
    get_plateaus,
    get_weekly_trends,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/exercises")
def list_exercises(
    db: DbSession = Depends(get_db),
    profile_id: str = Depends(get_current_profile_id),
):
    """قائمة التمارين المتاحة للتحليل (للقائمة المنسدلة)."""
    return get_available_exercises(db, profile_id)


@router.get("/exercise/{exercise_id}")
def exercise_deep_dive(
    exercise_id: str,
    days: int = Query(30, ge=7, le=365),
    limit: int = Query(30, ge=5, le=100),
    db: DbSession = Depends(get_db),
    profile_id: str = Depends(get_current_profile_id),
):
    """Exercise Deep Dive: e1RM trend + PRs + مقارنة فترات."""
    return {
        "exercise_id": exercise_id,
        "sessions": get_exercise_sessions(db, profile_id, exercise_id, limit=limit),
        "prs": get_exercise_prs(db, profile_id, exercise_id),
        "trend": get_exercise_trend(db, profile_id, exercise_id, days=days),
    }


@router.get("/muscle-balance")
def muscle_balance(
    weeks: int = Query(4, ge=1, le=52),
    db: DbSession = Depends(get_db),
    profile_id: str = Depends(get_current_profile_id),
):
    """Muscle Balance: Sets/أسبوع لكل عضلة + تصنيف."""
    return get_muscle_balance(db, profile_id, weeks=weeks)


@router.get("/plateaus")
def plateaus(
    weeks: int = Query(3, ge=1, le=12),
    min_sessions: int = Query(3, ge=2, le=10),
    db: DbSession = Depends(get_db),
    profile_id: str = Depends(get_current_profile_id),
):
    """كشف الجمود: تمارين ما تحسّنت."""
    return get_plateaus(db, profile_id, weeks=weeks, min_sessions=min_sessions)


@router.get("/effort")
def effort(
    weeks: int = Query(8, ge=1, le=52),
    db: DbSession = Depends(get_db),
    profile_id: str = Depends(get_current_profile_id),
):
    """تحليل الشدة: RIR/RPE Distribution + تحذيرات."""
    return get_effort_analysis(db, profile_id, weeks=weeks)


@router.get("/trends")
def trends(
    weeks: int = Query(12, ge=1, le=52),
    db: DbSession = Depends(get_db),
    profile_id: str = Depends(get_current_profile_id),
):
    """Trends أسبوعية: حجم + sets + جلسات."""
    return {"trends": get_weekly_trends(db, profile_id, weeks=weeks)}


@router.get("/overview")
def overview(
    weeks: int = Query(8, ge=1, le=52),
    db: DbSession = Depends(get_db),
    profile_id: str = Depends(get_current_profile_id),
):
    """نظرة شاملة: كل المؤشرات في طلب واحد."""
    return {
        "muscle_balance": get_muscle_balance(db, profile_id, weeks=weeks),
        "effort": get_effort_analysis(db, profile_id, weeks=weeks),
        "plateaus": get_plateaus(db, profile_id, weeks=3, min_sessions=2),
        "trends": get_weekly_trends(db, profile_id, weeks=weeks),
    }
