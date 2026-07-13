from sqlalchemy import select, func, and_
from src.infrastructure.db.models import SetTable, PerformedExerciseTable, SessionTable, ExerciseTable

def get_exercise_history(db, exercise_id, limit=20, offset=0):
    stmt = (
        select(SetTable, PerformedExerciseTable, SessionTable)
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(PerformedExerciseTable.exercise_id == str(exercise_id))
        .order_by(SessionTable.started_at.desc(), SetTable.set_order)
        .limit(limit)
        .offset(offset)
    )
    return db.execute(stmt).scalars().all()

def get_session_volume(db, session_id):
    stmt = (
        select(func.sum(SetTable.weight * SetTable.reps))
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .where(PerformedExerciseTable.session_id == str(session_id))
    )
    return db.execute(stmt).scalar_one_or_none()

def get_weekly_volume(db, user_id, week_start):
    stmt = (
        select(func.sum(SetTable.weight * SetTable.reps))
        .join(PerformedExerciseTable, SetTable.performed_exercise_id == PerformedExerciseTable.id)
        .join(SessionTable, PerformedExerciseTable.session_id == SessionTable.id)
        .where(
            and_(
                SessionTable.started_at >= week_start,
                SessionTable.user_id == user_id
            )
        )
    )
    return db.execute(stmt).scalar_one_or_none()
