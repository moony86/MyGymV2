from typing import Generator, Optional
from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session as DbSession
from src.infrastructure.db.connection import SessionLocal
from src.services.session_service import SessionService
from pathlib import Path
from src.knowledge.loader import KnowledgeLoader
from src.knowledge.provider import KnowledgeProvider
from src.knowledge.validator import KnowledgeValidator
from src.knowledge.queries import KnowledgeQueries
from src.infrastructure.db.models import DEFAULT_PROFILE_ID, ProfileTable

# deps.py موجود بـ src/apis/deps.py
# .parent      -> src/apis
# .parent.parent -> src
# .parent.parent.parent -> جذر المشروع (حيث يعيش مجلد knowledge/ فعليًا)
KNOWLEDGE_DIR = Path(__file__).parent.parent.parent / "knowledge"

# تحميل البيانات وتدقيقها عند استيراد الملف (مرة واحدة)
loader = KnowledgeLoader(KNOWLEDGE_DIR)
store = loader.load()

# تشغيل الفحص (Validator)
validator = KnowledgeValidator(store)
validator.validate()  # سيفشل التطبيق عن العمل لو البيانات غير متسقة

# إنشاء المزودين
_provider = KnowledgeProvider(store)
_queries = KnowledgeQueries(_provider)


def get_knowledge_provider() -> KnowledgeProvider:
    return _provider


def get_knowledge_queries() -> KnowledgeQueries:
    return _queries


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


def get_current_profile_id(
    profile_id: Optional[str] = Header(default=None, alias="X-Profile-Id"),
) -> str:
    return profile_id or DEFAULT_PROFILE_ID


def validate_profile_id(db: DbSession, profile_id: str) -> str:
    exists = db.query(ProfileTable.id).filter(ProfileTable.id == profile_id).first()
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile_id


def get_session_service(db, profile_id: str = DEFAULT_PROFILE_ID) -> SessionService:
    return SessionService(db, profile_id=profile_id)
