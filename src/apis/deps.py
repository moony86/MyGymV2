from typing import Generator
from sqlalchemy.orm import Session as DbSession
from src.infrastructure.db.connection import SessionLocal
from src.services.session_service import SessionService

def get_db() -> Generator[DbSession, None, None]:
    db = SessionLocal()
    try:
        connection = db.connection()
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.commit()
        except Exception:
            pass
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()

def get_session_service(db) -> SessionService:
    return SessionService(db)
