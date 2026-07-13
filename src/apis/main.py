from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import uuid6

from src.apis.routers.sessions import router as sessions_router
from src.apis.routers.exercises import router as exercises_router
from src.infrastructure.db.models import Base, ExerciseTable
from src.infrastructure.db.connection import engine, SessionLocal

DEFAULT_EXERCISES = [
    # Chest
    ("Chest Press (Machine)", "chest", "machine"),
    ("Incline Chest Press (Machine)", "chest", "machine"),
    ("Bench Press (Barbell)", "chest", "barbell"),
    ("Pec Deck Fly", "chest", "machine"),
    ("Cable Fly", "chest", "cable"),

    # Back
    ("Lat Pulldown", "back", "cable"),
    ("Seated Cable Row", "back", "cable"),
    ("Chest Supported Row", "back", "machine"),
    ("Pull Up", "back", "bodyweight"),
    ("Barbell Row", "back", "barbell"),

    # Shoulders
    ("Shoulder Press (Machine)", "shoulders", "machine"),
    ("Overhead Press (Barbell)", "shoulders", "barbell"),
    ("Lateral Raise", "shoulders", "dumbbell"),
    ("Rear Delt Fly", "shoulders", "machine"),

    # Legs
    ("Leg Press", "legs", "machine"),
    ("Hack Squat", "legs", "machine"),
    ("Squat", "legs", "barbell"),
    ("Leg Extension", "legs", "machine"),
    ("Leg Curl", "hamstrings", "machine"),
    ("Romanian Deadlift", "hamstrings", "barbell"),
    ("Calf Raise", "calves", "machine"),

    # Arms
    ("Biceps Curl", "biceps", "dumbbell"),
    ("Hammer Curl", "biceps", "dumbbell"),
    ("Preacher Curl (Machine)", "biceps", "machine"),
    ("Triceps Pushdown", "triceps", "cable"),
    ("Triceps Extension (Machine)", "triceps", "machine"),
    ("Skull Crusher", "triceps", "barbell"),
]
Base.metadata.create_all(engine)

def seed_default_exercises():
    from sqlalchemy.orm import Session as DbSession
    from uuid6 import uuid7
    db = SessionLocal()
    try:
        existing_names = {
        row.name
            for row in db.query(ExerciseTable.name).all()
        }
        added = 0
        
        for name, primary_muscle, equipment in DEFAULT_EXERCISES:
            if name in existing_names:
                continue

            db.add(
                ExerciseTable(
                    id=str(uuid7()),
                    name=name,
                    primary_muscle=primary_muscle,
                    equipment=equipment,
                    is_active=True,
                )
            )
            
            added +=1
            
        db.commit()
        
        if added:
            print(f"Added {added} new exercises.")
        else:
            print("Exercise library is already up to date.")
    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
    finally:
        db.close()


if os.getenv("PYTEST_CURRENT_TEST") is None:
    seed_default_exercises()

app = FastAPI(
    title="MyGym Pro Core",
    description="Minimal workout tracking API for dogfooding",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)
app.include_router(exercises_router)

static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "templates", "index.html"))

@app.get("/workout")
async def workout_page():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "templates", "workout.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
