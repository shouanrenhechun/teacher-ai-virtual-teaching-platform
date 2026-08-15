from collections.abc import Generator

from sqlalchemy.orm import Session

from ..database.session import get_db


def db_session() -> Generator[Session, None, None]:
    yield from get_db()
