import pytest
import uuid
import uuid6
import tempfile
import os
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use a file-based temp database to avoid SQLite in-memory sharing issues
tmpdir = tempfile.mkdtemp()
TEST_DB_PATH = os.path.join(tmpdir, "test.db")

# Monkeypatch database connection for tests BEFORE importing app
from src.infrastructure.db import connection as conn_module
test_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
conn_module.engine = test_engine
conn_module.SessionLocal = sessionmaker(bind=test_engine, expire_on_commit=False)

from src.infrastructure.db.models import Base, ExerciseTable
from fastapi.testclient import TestClient
from src.apis.main import app

# Create tables in test database
Base.metadata.create_all(test_engine)

client = TestClient(app)

@pytest.fixture
def db_session():
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture(autouse=True)
def clean_db(db_session):
    from src.infrastructure.db.models import SessionTable, PerformedExerciseTable, SetTable, ExerciseTable
    db_session.query(SetTable).delete()
    db_session.query(PerformedExerciseTable).delete()
    db_session.query(SessionTable).delete()
    db_session.query(ExerciseTable).delete()
    db_session.commit()
    yield

@pytest.fixture
def sample_exercise(db_session):
    ex = db_session.query(ExerciseTable).filter_by(name="Bench Press").first()
    if not ex:
        ex = ExerciseTable(
            id=str(uuid6.uuid7()),
            name="Bench Press",
            primary_muscle="chest",
            equipment="barbell",
            is_active=True
        )
        db_session.add(ex)
        db_session.commit()
    return ex

def test_start_workout(db_session):
    response = client.post("/api/workouts/start", json={})
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["status"] == "ACTIVE"


def test_profiles_keep_active_sessions_separate():
    first = client.post("/api/profiles", json={"name": "أحمد"}).json()
    second = client.post("/api/profiles", json={"name": "سارة"}).json()

    first_headers = {"X-Profile-Id": first["id"]}
    second_headers = {"X-Profile-Id": second["id"]}
    first_start = client.post("/api/workouts/start", headers=first_headers, json={})
    second_start = client.post("/api/workouts/start", headers=second_headers, json={})

    assert first_start.status_code == 200
    assert second_start.status_code == 200
    assert client.get("/api/workouts/active", headers=first_headers).json()["session"]["id"] == first_start.json()["id"]
    assert client.get("/api/workouts/active", headers=second_headers).json()["session"]["id"] == second_start.json()["id"]

def test_get_active_workout_empty():
    response = client.get("/api/workouts/active")
    assert response.status_code == 200
    data = response.json()
    assert data["session"] is None

def test_get_exercises(db_session, sample_exercise):
    response = client.get("/api/exercises")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert data[0]["name"] == "Bench Press"

def test_add_set_to_workout(db_session, sample_exercise):
    start_resp = client.post("/api/workouts/start", json={})
    session_id = start_resp.json()["id"]
    
    response = client.post(f"/api/workouts/{session_id}/sets", json={
        "exercise_id": str(sample_exercise.id),
        "weight": 70.0,
        "reps": 8,
        "set_type": "working"
    })
    assert response.status_code == 200
    data = response.json()
    assert Decimal(data["weight"]) == Decimal("70.00")
    assert data["reps"] == 8

def test_retrying_same_set_operation_does_not_duplicate(db_session, sample_exercise):
    from src.infrastructure.db.models import SetTable

    start_resp = client.post("/api/workouts/start", json={})
    session_id = start_resp.json()["id"]
    payload = {
        "exercise_id": str(sample_exercise.id),
        "weight": 70.0,
        "reps": 8,
        "client_operation_id": "offline-operation-1",
    }

    first = client.post(f"/api/workouts/{session_id}/sets", json=payload)
    second = client.post(f"/api/workouts/{session_id}/sets", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert db_session.query(SetTable).count() == 1

def test_get_workout_details(db_session, sample_exercise):
    start_resp = client.post("/api/workouts/start", json={})
    session_id = start_resp.json()["id"]
    
    client.post(f"/api/workouts/{session_id}/sets", json={
        "exercise_id": str(sample_exercise.id),
        "weight": 70.0,
        "reps": 8
    })
    
    response = client.get(f"/api/workouts/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["session"]["id"] == session_id
    assert len(data["sets"]) == 1

def test_finish_workout(db_session, sample_exercise):
    start_resp = client.post("/api/workouts/start", json={})
    session_id = start_resp.json()["id"]
    
    client.post(f"/api/workouts/{session_id}/sets", json={
        "exercise_id": str(sample_exercise.id),
        "weight": 70.0,
        "reps": 8
    })
    
    response = client.post(f"/api/workouts/{session_id}/finish")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "COMPLETED"

def test_get_last_set(db_session, sample_exercise):
    start_resp = client.post("/api/workouts/start", json={})
    session_id = start_resp.json()["id"]
    
    client.post(f"/api/workouts/{session_id}/sets", json={
        "exercise_id": str(sample_exercise.id),
        "weight": 70.0,
        "reps": 8
    })
    
    response = client.get(f"/api/workouts/{session_id}/last-set?exercise_id={sample_exercise.id}")
    assert response.status_code == 200
    data = response.json()
    assert Decimal(data["weight"]) == Decimal("70.00")
