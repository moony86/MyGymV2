from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as DbSession
import os
import logging
from contextlib import contextmanager

# إعداد تسجيل الدخول الأساسي
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# مسار قاعدة البيانات (افتراضي: gym_tracker.db في الجذر)
DB_PATH = os.getenv("DB_PATH", "./gym_tracker.db")

# إنشاء المحرك مع دعم المفاتيح الأجنبية وفرضها
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False}
)

# نصوص PRAGMA الأوليةي
from sqlalchemy import event
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        logger.info("تم إعداد PRAGMA لقاعدة البيانات")
    except Exception as e:
        logger.warning(f"لم يتمكن من إعداد PRAGMA: {e}")
    finally:
        cursor.close()

# Create Session with optimized settings
def get_session_local():
    return sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False
    )

SessionLocal = get_session_local()

@contextmanager
def get_db() -> DbSession:
    """متجر سياق آمن لإدارة جلسات قاعدة البيانات."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"خطأ في قاعدة البيانات: {e}", exc_info=True)
        raise
    finally:
        db.close()