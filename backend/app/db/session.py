from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def atomic(db: Session) -> Iterator[Session]:
    """One unit of work: commit when the block finishes, roll everything back if it raises."""
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
