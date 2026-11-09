import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.core import User
from app.models.enums import UserRole

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
) -> User:
    """Resolve the bearer token to a live user.

    Role, unit and active flag always come from the database, never from the token claims, so a
    demoted or deactivated user loses access immediately.
    """
    if credentials is None:
        raise AppError(401, "NOT_AUTHENTICATED", "Authentication required")
    claims = decode_access_token(credentials.credentials)
    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise AppError(401, "INVALID_TOKEN", "Invalid access token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[..., User]:
    allowed = frozenset(roles)

    def dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise AppError(403, "FORBIDDEN", "You do not have permission to perform this action")
        return user

    return dependency
