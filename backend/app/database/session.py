from pathlib import Path
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[2]
DATABASE_DIR = BACKEND_DIR / "data"
DATABASE_PATH = Path(os.environ.get('TEACHING_DATABASE_PATH', str(DATABASE_DIR / "app.db")))
DATABASE_DIR = DATABASE_PATH.parent
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


class Base(DeclarativeBase):
    """Base class for future SQLAlchemy models."""


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create database tables and insert the small MVP seed set if needed."""
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    # Import models before create_all so SQLAlchemy knows every table.
    from .. import models  # noqa: F401
    from .migrations import migrate
    migrate(engine)

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql('PRAGMA user_version=2')

    from .seed import seed_initial_data
    from ..services.session_service import backfill_session_snapshots

    with SessionLocal() as db:
        seed_initial_data(db)
        backfill_session_snapshots(db)


def get_db():
    """Yield a database session for FastAPI request handlers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
