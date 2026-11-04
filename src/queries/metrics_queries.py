from sqlalchemy import select, func, and_
from src.infrastructure.db.models import (
    SetTable, PerformedExerciseTable, SessionTable, ExerciseTable
)


def get_muscle_volume_by_week(db, profile_id, week_start, week_end):
    stmt = (
        select(
            ExerciseTable.primary_muscle,
            func.sum(SetTable.weight * SetTable.reps).label("volume"),
        )
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(ExerciseTable, PerformedExerciseTable.exercise_id == ExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.started_at >= week_start,
                SessionTable.started_at < week_end,
            )
        )
        .group_by(ExerciseTable.primary_muscle)
    )
    return db.execute(stmt).all()


def get_muscle_sets_by_week(db, profile_id, week_start, week_end):
    stmt = (
        select(
            ExerciseTable.primary_muscle,
            func.count(SetTable.id).label("sets"),
        )
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(ExerciseTable, PerformedExerciseTable.exercise_id == ExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.started_at >= week_start,
                SessionTable.started_at < week_end,
                SetTable.set_type != "warmup",
                PerformedExerciseTable.is_skipped.is_(False),
                PerformedExerciseTable.is_warmup.is_(False),
                ExerciseTable.primary_muscle.is_not(None),
            )
        )
        .group_by(ExerciseTable.primary_muscle)
        .order_by(ExerciseTable.primary_muscle)
    )
    return db.execute(stmt).all()


def get_streak_count(db, profile_id):
    stmt = (
        select(func.count(SessionTable.id))
        .where(
            and_(
                SessionTable.profile_id == profile_id,
                SessionTable.status == "COMPLETED",
            )
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def get_top_exercises(db, profile_id, limit=5):
    stmt = (
        select(
            ExerciseTable.name,
            func.count(SetTable.id).label("set_count"),
        )
        .join(PerformedExerciseTable, ExerciseTable.id == PerformedExerciseTable.exercise_id)
        .join(SetTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(SessionTable.profile_id == profile_id)
        .group_by(ExerciseTable.id)
        .order_by(func.count(SetTable.id).desc())
        .limit(limit)
    )
    return db.execute(stmt).all()