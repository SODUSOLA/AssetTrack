from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.rate_limit import LOGIN_LIMIT, limiter
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse
from app.schemas.users import UserOut
from app.services import auth as auth_service
from app.services.auth import TokenBundle

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
# The refresh cookie is only ever sent to the auth endpoints.
REFRESH_COOKIE_PATH = "/api/v1/auth"

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
    )


def _respond(response: Response, bundle: TokenBundle) -> TokenResponse:
    _set_refresh_cookie(response, bundle.refresh_token)
    return TokenResponse(access_token=bundle.access_token, expires_in=bundle.expires_in)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in",
    description="Exchange email and password for a 30-minute access token (JSON) and a 7-day "
    "refresh token (httpOnly cookie). Limited to 5 attempts per minute per IP.",
)
@limiter.limit(LOGIN_LIMIT)
def login(request: Request, response: Response, body: LoginRequest, db: DbSession) -> TokenResponse:
    user = auth_service.authenticate(db, body.email, body.password)
    return _respond(response, auth_service.issue_tokens(db, user))


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate the refresh token",
    description="Reads the refresh cookie, revokes it and issues a new access token and cookie. "
    "Presenting an already-used refresh token revokes every session of that user.",
)
def refresh(
    response: Response, db: DbSession, refresh_token: RefreshCookie = None
) -> TokenResponse:
    if not refresh_token:
        raise AppError(401, "REFRESH_TOKEN_INVALID", "Missing refresh token")
    _, bundle = auth_service.rotate_refresh_token(db, refresh_token)
    return _respond(response, bundle)


@router.post(
    "/logout",
    status_code=204,
    summary="Sign out",
    description="Revokes the refresh token (if any) and clears the cookie.",
)
def logout(response: Response, db: DbSession, refresh_token: RefreshCookie = None) -> None:
    if refresh_token:
        auth_service.revoke_refresh_token(db, refresh_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserOut, summary="Current user")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post(
    "/change-password",
    status_code=204,
    summary="Change own password",
    description="Requires the old password. Ends every other session of the user; the current "
    "session (refresh cookie) stays valid.",
)
def change_password(
    body: ChangePasswordRequest,
    user: CurrentUser,
    db: DbSession,
    refresh_token: RefreshCookie = None,
) -> None:
    auth_service.change_password(
        db, user, body.old_password, body.new_password, keep_refresh_token=refresh_token
    )
