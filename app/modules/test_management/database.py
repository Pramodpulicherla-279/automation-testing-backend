"""
test_management/database.py
─────────────────────────────
SQLAlchemy engine + session for the Test Management MySQL backend.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.modules.test_management.config import config
from app.modules.test_management.db_models import Base  # noqa: F401 -- re-exported for Alembic

engine = create_engine(
    config.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=config.db_echo,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
