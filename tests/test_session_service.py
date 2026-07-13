import pytest
import uuid
import uuid6
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.infrastructure.db.models import Base, ExerciseTable
from src.services.session_service import SessionService
from src.domain.enums import SetType, SessionStatus

# قاعدة بيانات اختبار في الذاكرة
@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture
def sample_exercise(db_session):
    ex = ExerciseTable(
        id=str(uuid6.uuid7()),
        name="Bench Press",
        is_active=True
    )
    db_session.add(ex)
    db_session.commit()
    return ex

def test_create_session(db_session):
    service = SessionService(db_session)
    session = service.create_session()
    assert session.status == SessionStatus.ACTIVE
    assert session.ended_at is None
    assert session.id is not None

def test_reject_multiple_active_sessions(db_session):
    service = SessionService(db_session)
    service.create_session()
    with pytest.raises(ValueError, match="ACTIVE session already exists"):
        service.create_session()

def test_add_set_to_session(db_session, sample_exercise):
    service = SessionService(db_session)
    session = service.create_session()

    new_set = service.add_set(
        session_id=session.id,
        exercise_id=uuid.UUID(sample_exercise.id),
        weight=Decimal("70.0"),
        reps=8,
        set_type=SetType.WORKING
    )
    assert new_set.weight == Decimal("70.0")
    assert new_set.reps == 8

    new_set2 = service.add_set(
        session_id=session.id,
        exercise_id=uuid.UUID(sample_exercise.id),
        weight=Decimal("75.0"),
        reps=6
    )
    assert new_set2.set_order == 1

def test_reject_negative_weight(db_session, sample_exercise):
    service = SessionService(db_session)
    session = service.create_session()
    with pytest.raises(ValueError, match="Weight cannot be negative"):
        service.add_set(session.id, uuid.UUID(sample_exercise.id), Decimal("-1.0"), 5)

def test_reject_zero_reps(db_session, sample_exercise):
    service = SessionService(db_session)
    session = service.create_session()
    with pytest.raises(ValueError, match="Reps must be > 0"):
        service.add_set(session.id, uuid.UUID(sample_exercise.id), Decimal("70.0"), 0)

def test_finish_session(db_session, sample_exercise):
    service = SessionService(db_session)
    session = service.create_session()
    service.add_set(session.id, uuid.UUID(sample_exercise.id), Decimal("70.0"), 8)

    completed = service.finish_session(session.id)
    assert completed.status == SessionStatus.COMPLETED
    assert completed.ended_at is not None

def test_reject_finish_empty_session(db_session):
    service = SessionService(db_session)
    session = service.create_session()
    with pytest.raises(ValueError, match="Cannot finish an empty session"):
        service.finish_session(session.id)

def test_reject_add_set_to_completed_session(db_session, sample_exercise):
    service = SessionService(db_session)
    session = service.create_session()
    service.add_set(session.id, uuid.UUID(sample_exercise.id), Decimal("70.0"), 8)
    service.finish_session(session.id)

    with pytest.raises(ValueError, match="Cannot add sets to a COMPLETED session"):
        service.add_set(session.id, uuid.UUID(sample_exercise.id), Decimal("80.0"), 5)

def test_abandon_session(db_session):
    service = SessionService(db_session)
    session = service.create_session()
    abandoned = service.abandon_session(session.id)
    assert abandoned.status == SessionStatus.ABANDONED

# --- Crash Recovery Tests ---
def test_crash_recovery_empty_session(db_session):
    service = SessionService(db_session)
    service.create_session()

    recovered = service.recover_active_sessions()
    assert len(recovered) == 1
    assert recovered[0].status == SessionStatus.ACTIVE

def test_crash_recovery_session_with_set(db_session, sample_exercise):
    service = SessionService(db_session)
    session = service.create_session()
    service.add_set(session.id, uuid.UUID(sample_exercise.id), Decimal("70.0"), 8)

    recovered = service.recover_active_sessions()
    assert len(recovered) == 1
    assert recovered[0].status == SessionStatus.ACTIVE

    sets = service.get_session_sets(session.id)
    assert len(sets) == 1
