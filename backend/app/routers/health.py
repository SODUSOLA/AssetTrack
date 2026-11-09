from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Liveness and database check",
    description="Returns 200 when the API is up and PostgreSQL answers `SELECT 1`; "
    "503 in the standard error format otherwise.",
)
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise AppError(503, "DB_UNAVAILABLE", "Database is not reachable") from exc
    return {"status": "ok", "database": "ok"}
