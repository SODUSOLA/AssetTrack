import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    burn_password_check,
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models.auth import RefreshToken
from app.models.core import User

logger = logging.getLogger("app.auth")

_INVALID_CREDENTIALS = AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password")


@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    expires_in: int
    refresh_token: str


def _now() -> datetime:
    return datetime.now(UTC)


def _invalid_credentials() -> AppError:
    return AppError(
        _INVALID_CREDENTIALS.status_code, _INVALID_CREDENTIALS.code, _INVALID_CREDENTIALS.message
    )


def authenticate(db: Session, email: str, password: str) -> User:
    """Same error and similar cost for unknown email, wrong password and inactive account."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        burn_password_check(password)
        raise _invalid_credentials()
    if not verify_password(user.password_hash, password):
        raise _invalid_credentials()
    if not user.is_active:
        logger.info("login.rejected_inactive user=%s", user.id)
        raise _invalid_credentials()
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return user


def issue_tokens(db: Session, user: User) -> TokenBundle:
    access_token, expires_in = create_access_token(user)
    refresh_plain = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_plain),
            expires_at=_now() + timedelta(days=get_settings().refresh_token_days),
        )
    )
    db.commit()
    return TokenBundle(access_token, expires_in, refresh_plain)


def revoke_all_refresh_tokens(
    db: Session, user_id: uuid.UUID, *, except_token_hash: str | None = None
) -> None:
    """Revoke every live refresh token of a user (caller commits)."""
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    if except_token_hash is not None:
        stmt = stmt.where(RefreshToken.token_hash != except_token_hash)
    db.execute(stmt)


def rotate_refresh_token(db: Session, refresh_plain: str) -> tuple[User, TokenBundle]:
    row = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(refresh_plain))
        .with_for_update()
    )
    if row is None:
        raise AppError(401, "REFRESH_TOKEN_INVALID", "Invalid refresh token")
    if row.revoked_at is not None:
        # A rotated or revoked token is being replayed: assume it leaked, end every session.
        logger.warning("refresh.reuse_detected user=%s", row.user_id)
        revoke_all_refresh_tokens(db, row.user_id)
        db.commit()
        raise AppError(401, "REFRESH_TOKEN_INVALID", "Invalid refresh token")
    if row.expires_at <= _now():
        raise AppError(401, "REFRESH_TOKEN_EXPIRED", "Refresh token has expired")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        row.revoked_at = _now()
        db.commit()
        raise AppError(401, "REFRESH_TOKEN_INVALID", "Invalid refresh token")
    row.revoked_at = _now()
    return user, issue_tokens(db, user)  # issue_tokens commits the revocation too


def revoke_refresh_token(db: Session, refresh_plain: str) -> None:
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(refresh_plain))
    )
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        db.commit()


def change_password(
    db: Session,
    user: User,
    old_password: str,
    new_password: str,
    *,
    keep_refresh_token: str | None = None,
) -> None:
    if not verify_password(user.password_hash, old_password):
        raise AppError(400, "INVALID_OLD_PASSWORD", "The current password is incorrect")
    if old_password == new_password:
        raise AppError(400, "PASSWORD_UNCHANGED", "The new password must differ from the old one")
    user.password_hash = hash_password(new_password)
    keep_hash = hash_refresh_token(keep_refresh_token) if keep_refresh_token else None
    revoke_all_refresh_tokens(db, user.id, except_token_hash=keep_hash)
    db.commit()
    logger.info("password.changed user=%s", user.id)
