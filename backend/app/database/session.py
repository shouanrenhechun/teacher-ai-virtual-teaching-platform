from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[2]
DATABASE_DIR = BACKEND_DIR / "data"
DATABASE_PATH = DATABASE_DIR / "app.db"
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

    Base.metadata.create_all(bind=engine)

    from .seed import seed_initial_data

    with SessionLocal() as db:
        seed_initial_data(db)


def get_db():
    """Yield a database session for FastAPI request handlers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
