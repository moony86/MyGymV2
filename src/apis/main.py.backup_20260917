from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import uuid6

from src.apis.routers.sessions import router as sessions_router
from src.apis.routers.exercises import router as exercises_router
from src.apis.routers.profile import router as profile_router
from src.infrastructure.db.models import Base, ExerciseTable
from src.infrastructure.db.connection import engine, SessionLocal

from src.apis.routers.planner import router as planner_router
from alembic.config import Config
from alembic import command
from src.apis.deps import get_knowledge_provider
from src.domain.profile_context import set_current_profile_id, reset_current_profile_id, DEFAULT_PROFILE_ID



def run_migrations():
    """تشغيل الترحيلات تلقائياً عند بدء التشغيل"""
    alembic_cfg = Config("alembic.ini")
    try:
        command.upgrade(alembic_cfg, "head")
        print("Database migrations applied successfully.")
    except Exception as e:
        raise RuntimeError(f"Database migrations failed: {e}") from e



if os.getenv("PYTEST_CURRENT_TEST") is None:
    run_migrations()


app = FastAPI(
    title="MyGym Pro Core",
    description="Minimal workout tracking API for dogfooding",
    version="0.1.0"
)


@app.middleware("http")
async def profile_context_middleware(request, call_next):
    token = set_current_profile_id(
        request.headers.get("X-Profile-Id", DEFAULT_PROFILE_ID)
    )
    try:
        return await call_next(request)
    finally:
        reset_current_profile_id(token)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)
app.include_router(exercises_router)
app.include_router(planner_router)
app.include_router(profile_router)

static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "templates", "index.html"))


@app.get("/workout")
async def workout_page():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "templates", "workout.html"))


@app.get("/plans")
async def plans_page():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "templates", "plans.html"))


@app.get("/profile-setup")
async def profile_setup_page():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "templates", "profile-setup.html"))


@app.get("/body-history")
async def body_history_page():
    return FileResponse(os.path.join(os.path.dirname(__file__), "..", "..", "templates", "body_history.html"))


@app.get("/debug-knowledge")
async def debug_knowledge():
    provider = get_knowledge_provider()
    return {
        "total_exercises": len(provider.exercises()),
        "total_muscles": len(provider.muscles()),
        "total_templates": len(provider.templates()),
        "status": "Healthy & Validated"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
