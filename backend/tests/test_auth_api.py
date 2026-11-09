from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    MAX_PASSWORD_LENGTH,
    create_access_token,
    hash_password,
    new_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models.auth import RefreshToken
from app.models.enums import UserRole
from app.services.auth import issue_tokens
from tests.api_helpers import PASSWORD, People, bearer

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
CHANGE_PASSWORD = "/api/v1/auth/change-password"
COOKIE_DOMAIN = "testserver.local"  # what http.cookiejar assigns to a dotless host
COOKIE_PATH = "/api/v1/auth"


def login(api: TestClient, email: str, password: str = PASSWORD):
    return api.post(LOGIN, json={"email": email, "password": password})


def set_cookie(api: TestClient, value: str) -> None:
    api.cookies.clear()  # exactly one refresh cookie in the jar
    api.cookies.set("refresh_token", value, domain=COOKIE_DOMAIN, path=COOKIE_PATH)


# ---------- password hashing ----------


def test_passwords_use_argon2id_and_verify() -> None:
    hashed = hash_password("a-long-enough-password")
    assert hashed.startswith("$argon2id$")
    assert hashed != hash_password("a-long-enough-password")  # per-hash salt
    assert verify_password(hashed, "a-long-enough-password")
    assert not verify_password(hashed, "something-else-entirely")
    assert not verify_password("not-a-hash", "whatever")
    assert not password_needs_rehash(hashed)


# ---------- login ----------


def test_login_returns_access_token_and_httponly_cookie(api: TestClient, people: People) -> None:
    resp = login(api, people.rep_a.email)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_minutes * 60

    claims = jwt.decode(body["access_token"], get_settings().secret_key, algorithms=["HS256"])
    assert claims["sub"] == str(people.rep_a.id)
    assert claims["role"] == "unit_rep"
    assert claims["unit_id"] == str(people.unit_a.id)

    cookie = resp.headers["set-cookie"].lower()
    assert "refresh_token=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert f"path={COOKIE_PATH}" in cookie
    assert "max-age=" in cookie


def test_login_email_is_case_insensitive(api: TestClient, people: People) -> None:
    assert login(api, "ADMIN@T.TEST").status_code == 200


def test_login_failures_are_indistinguishable(api: TestClient, people: People, db: Session) -> None:
    people.auditor.is_active = False
    db.commit()
    wrong_password = login(api, people.admin.email, "wrong-password-here")
    unknown_email = login(api, "nobody@t.test")
    inactive = login(api, people.auditor.email)
    for resp in (wrong_password, unknown_email, inactive):
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert wrong_password.json() == unknown_email.json() == inactive.json()
    assert "set-cookie" not in inactive.headers


def test_login_is_rate_limited_to_five_per_minute(api: TestClient, people: People) -> None:
    for _ in range(5):
        assert login(api, people.admin.email, "wrong-password-here").status_code == 401
    blocked = login(api, people.admin.email)  # correct password, still blocked
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert blocked.headers["retry-after"]


def test_login_validates_input(api: TestClient) -> None:
    assert api.post(LOGIN, json={"email": "not-an-email", "password": "x"}).status_code == 422
    too_long = "x" * (MAX_PASSWORD_LENGTH + 1)
    assert api.post(LOGIN, json={"email": "a@t.test", "password": too_long}).status_code == 422


# ---------- access tokens / me ----------


def test_me_returns_user_without_password_hash(api: TestClient, people: People) -> None:
    resp = api.get(ME, headers=bearer(people.rep_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == people.rep_a.email
    assert body["unit_id"] == str(people.unit_a.id)
    assert "password_hash" not in body and "password" not in body


def test_missing_or_garbage_token_is_401(api: TestClient) -> None:
    missing = api.get(ME)
    assert (missing.status_code, missing.json()["error"]["code"]) == (401, "NOT_AUTHENTICATED")
    garbage = api.get(ME, headers={"Authorization": "Bearer not.a.token"})
    assert (garbage.status_code, garbage.json()["error"]["code"]) == (401, "INVALID_TOKEN")


def _token(people: People, **overrides) -> dict[str, str]:
    now = datetime.now(UTC)
    claims = {
        "sub": str(people.admin.id),
        "role": "admin",
        "unit_id": None,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    } | overrides
    secret = overrides.pop("_secret", None) or get_settings().secret_key
    claims.pop("_secret", None)
    return {"Authorization": f"Bearer {jwt.encode(claims, secret, algorithm='HS256')}"}


def test_expired_token_is_rejected(api: TestClient, people: People) -> None:
    headers = _token(people, exp=datetime.now(UTC) - timedelta(seconds=5))
    resp = api.get(ME, headers=headers)
    assert (resp.status_code, resp.json()["error"]["code"]) == (401, "TOKEN_EXPIRED")


def test_token_signed_with_another_key_is_rejected(api: TestClient, people: People) -> None:
    now = datetime.now(UTC)
    forged = jwt.encode(
        {"sub": str(people.admin.id), "typ": "access", "exp": now + timedelta(minutes=5)},
        "some-other-secret-key-of-sufficient-length",
        algorithm="HS256",
    )
    resp = api.get(ME, headers={"Authorization": f"Bearer {forged}"})
    assert (resp.status_code, resp.json()["error"]["code"]) == (401, "INVALID_TOKEN")


def test_token_of_wrong_type_or_subject_is_rejected(api: TestClient, people: People) -> None:
    assert api.get(ME, headers=_token(people, typ="refresh")).status_code == 401
    assert api.get(ME, headers=_token(people, sub="not-a-uuid")).status_code == 401
    unknown_user = _token(people, sub="00000000-0000-0000-0000-000000000000")
    assert api.get(ME, headers=unknown_user).status_code == 401


def test_deactivated_user_loses_access_immediately(
    api: TestClient, people: People, db: Session
) -> None:
    headers = bearer(people.engineer)
    assert api.get(ME, headers=headers).status_code == 200
    people.engineer.is_active = False
    db.commit()
    assert api.get(ME, headers=headers).status_code == 401


def test_role_comes_from_database_not_token_claims(
    api: TestClient, people: People, db: Session
) -> None:
    headers = bearer(people.engineer)  # token says engineer
    register = {"device_type": "laptop"}
    assert api.post("/api/v1/devices", headers=headers, json=register).status_code == 201
    unit_id = people.unit_a.id
    people.engineer.unit_id = unit_id
    people.engineer.role = UserRole.unit_rep
    db.commit()
    assert api.post("/api/v1/devices", headers=headers, json=register).status_code == 403


# ---------- refresh / logout ----------


def test_refresh_rotates_the_token(api: TestClient, people: People) -> None:
    first = login(api, people.admin.email)
    old_cookie = first.cookies["refresh_token"]

    second = api.post(REFRESH)
    assert second.status_code == 200
    assert second.json()["access_token"]
    new_cookie = second.cookies["refresh_token"]
    assert new_cookie != old_cookie
    new_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}
    assert api.get(ME, headers=new_headers).status_code == 200


def test_replaying_a_rotated_token_revokes_every_session(api: TestClient, people: People) -> None:
    old_cookie = login(api, people.admin.email).cookies["refresh_token"]
    new_cookie = api.post(REFRESH).cookies["refresh_token"]

    set_cookie(api, new_cookie)
    assert api.post(REFRESH).status_code == 200  # sanity: the cookie really is sent and valid
    newest_cookie = api.cookies.get("refresh_token", domain=COOKIE_DOMAIN, path=COOKIE_PATH)

    set_cookie(api, old_cookie)  # attacker replays the already-used token
    replay = api.post(REFRESH)
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "REFRESH_TOKEN_INVALID"

    set_cookie(api, newest_cookie)  # the legitimate holder is logged out too
    assert api.post(REFRESH).status_code == 401


def test_refresh_without_cookie_is_401(api: TestClient) -> None:
    resp = api.post(REFRESH)
    assert (resp.status_code, resp.json()["error"]["code"]) == (401, "REFRESH_TOKEN_INVALID")


def test_unknown_refresh_token_is_401(api: TestClient, people: People, db: Session) -> None:
    valid = issue_tokens(db, people.admin).refresh_token
    set_cookie(api, valid)
    assert api.post(REFRESH).status_code == 200  # the helper does deliver the cookie
    set_cookie(api, new_refresh_token())
    assert api.post(REFRESH).status_code == 401


def test_expired_refresh_token_is_401(api: TestClient, people: People, db: Session) -> None:
    login(api, people.admin.email)
    db.execute(update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    resp = api.post(REFRESH)
    assert (resp.status_code, resp.json()["error"]["code"]) == (401, "REFRESH_TOKEN_EXPIRED")


def test_refresh_for_deactivated_user_is_401(api: TestClient, people: People, db: Session) -> None:
    login(api, people.admin.email)
    people.admin.is_active = False
    db.commit()
    assert api.post(REFRESH).status_code == 401


def test_refresh_tokens_are_stored_hashed(api: TestClient, people: People, db: Session) -> None:
    cookie = login(api, people.admin.email).cookies["refresh_token"]
    stored = db.scalars(select(RefreshToken.token_hash)).all()
    assert len(stored) == 1
    assert cookie not in stored


def test_logout_revokes_and_clears_cookie(api: TestClient, people: People) -> None:
    cookie = login(api, people.admin.email).cookies["refresh_token"]
    resp = api.post(LOGOUT)
    assert resp.status_code == 204
    assert "max-age=0" in resp.headers["set-cookie"].lower()

    set_cookie(api, cookie)
    resp = api.post(REFRESH)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "REFRESH_TOKEN_INVALID"


def test_logout_without_session_is_still_204(api: TestClient) -> None:
    assert api.post(LOGOUT).status_code == 204


# ---------- change password ----------


def test_change_password_flow(api: TestClient, people: People, db: Session) -> None:
    current_cookie = login(api, people.rep_a.email).cookies["refresh_token"]
    other_session = issue_tokens(db, people.rep_a).refresh_token

    resp = api.post(
        CHANGE_PASSWORD,
        headers=bearer(people.rep_a),
        json={"old_password": PASSWORD, "new_password": "a-brand-new-password"},
    )
    assert resp.status_code == 204

    set_cookie(api, current_cookie)
    assert api.post(REFRESH).status_code == 200  # this session survives
    set_cookie(api, other_session)
    assert api.post(REFRESH).status_code == 401  # other sessions ended

    api.cookies.clear()
    assert login(api, people.rep_a.email).status_code == 401  # old password gone
    assert login(api, people.rep_a.email, "a-brand-new-password").status_code == 200


@pytest.mark.parametrize(
    ("old", "new", "status", "code"),
    [
        ("wrong-old-password", "a-brand-new-password", 400, "INVALID_OLD_PASSWORD"),
        (PASSWORD, PASSWORD, 400, "PASSWORD_UNCHANGED"),
        (PASSWORD, "short", 422, "VALIDATION_ERROR"),
        (PASSWORD, "x" * (MAX_PASSWORD_LENGTH + 1), 422, "VALIDATION_ERROR"),
    ],
)
def test_change_password_rejections(
    api: TestClient, people: People, old: str, new: str, status: int, code: str
) -> None:
    resp = api.post(
        CHANGE_PASSWORD,
        headers=bearer(people.engineer),
        json={"old_password": old, "new_password": new},
    )
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code


def test_change_password_requires_authentication(api: TestClient) -> None:
    resp = api.post(CHANGE_PASSWORD, json={"old_password": "x", "new_password": "y" * 12})
    assert resp.status_code == 401


def test_access_token_helper_matches_user(people: People) -> None:
    token, expires_in = create_access_token(people.rep_b)
    claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    assert claims["unit_id"] == str(people.unit_b.id)
    assert expires_in == 1800
