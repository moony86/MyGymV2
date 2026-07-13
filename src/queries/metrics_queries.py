from sqlalchemy import select, func, and_, case
from src.infrastructure.db.models import (
    SetTable, PerformedExerciseTable, SessionTable, ExerciseTable
)

def get_muscle_volume_by_week(db, user_id, week_start):
    stmt = (
        select(
            ExerciseTable.primary_muscle,
            func.sum(SetTable.weight * SetTable.reps).label("volume")
        )
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(ExerciseTable, PerformedExerciseTable.exercise_id == ExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.started_at >= week_start,
                SessionTable.user_id == user_id
            )
        )
        .group_by(ExerciseTable.primary_muscle)
    )
    return db.execute(stmt).all()

def get_streak_count(db, user_id):
    stmt = (
        select(func.count(SessionTable.id))
        .where(
            and_(
                SessionTable.user_id == user_id,
                SessionTable.status == "COMPLETED"
            )
        )
    )
    return db.execute(stmt).scalar_one_or_none()

def get_top_exercises(db, user_id, limit=5):
    stmt = (
        select(
            ExerciseTable.name,
            func.count(SetTable.id).label("set_count")
        )
        .join(PerformedExerciseTable, ExerciseTable.id == PerformedExerciseTable.exercise_id)
        .join(SetTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(SessionTable.user_id == user_id)
        .group_by(ExerciseTable.id)
        .order_by(func.count(SetTable.id).desc())
        .limit(limit)
    )
    return db.execute(stmt).all()
