import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.auth import RefreshToken
from app.services.auth import issue_tokens
from tests.api_helpers import PASSWORD, People, bearer
from tests.factories import make_unit, make_user

USERS = "/api/v1/users"
NEW_PASSWORD = "a-very-new-password"


def new_user_body(**overrides) -> dict:
    return {
        "full_name": "  Ada Obi ",
        "email": "ada@lasrra.test",
        "password": "initial-password-1",
        "role": "engineer",
    } | overrides


def test_admin_creates_user_who_can_log_in(api: TestClient, people: People) -> None:
    resp = api.post(USERS, headers=bearer(people.admin), json=new_user_body())
    assert resp.status_code == 201
    body = resp.json()
    assert body["full_name"] == "Ada Obi"  # trimmed
    assert body["role"] == "engineer" and body["unit_id"] is None and body["is_active"] is True
    assert "password" not in body and "password_hash" not in body

    login = api.post(
        "/api/v1/auth/login", json={"email": "ada@lasrra.test", "password": "initial-password-1"}
    )
    assert login.status_code == 200


def test_create_unit_rep_requires_an_active_unit(
    api: TestClient, people: People, db: Session
) -> None:
    admin = bearer(people.admin)
    missing = api.post(USERS, headers=admin, json=new_user_body(role="unit_rep"))
    assert (missing.status_code, missing.json()["error"]["code"]) == (422, "UNIT_REQUIRED")

    unknown = new_user_body(role="unit_rep", unit_id=str(uuid.uuid4()))
    assert api.post(USERS, headers=admin, json=unknown).json()["error"]["code"] == "UNIT_NOT_FOUND"

    people.unit_b.is_active = False
    db.commit()
    inactive = new_user_body(role="unit_rep", unit_id=str(people.unit_b.id))
    assert api.post(USERS, headers=admin, json=inactive).json()["error"]["code"] == "UNIT_NOT_FOUND"

    ok = new_user_body(role="unit_rep", unit_id=str(people.unit_a.id))
    created = api.post(USERS, headers=admin, json=ok)
    assert created.status_code == 201
    assert created.json()["unit_id"] == str(people.unit_a.id)


def test_unit_is_rejected_for_non_unit_rep_roles(api: TestClient, people: People) -> None:
    body = new_user_body(role="auditor", unit_id=str(people.unit_a.id))
    resp = api.post(USERS, headers=bearer(people.admin), json=body)
    assert (resp.status_code, resp.json()["error"]["code"]) == (422, "UNIT_NOT_ALLOWED")


def test_duplicate_email_is_rejected_case_insensitively(api: TestClient, people: People) -> None:
    resp = api.post(
        USERS, headers=bearer(people.admin), json=new_user_body(email=people.engineer.email.upper())
    )
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "EMAIL_TAKEN")


def test_user_input_validation(api: TestClient, people: People) -> None:
    admin = bearer(people.admin)
    for bad in (
        {"password": "short"},
        {"password": "x" * 129},
        {"email": "not-an-email"},
        {"full_name": "   "},
        {"role": "superuser"},
    ):
        resp = api.post(USERS, headers=admin, json=new_user_body(**bad))
        assert resp.status_code == 422, bad
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_users_is_paginated_and_filterable(api: TestClient, people: People) -> None:
    admin = bearer(people.admin)
    page = api.get(USERS, headers=admin, params={"page": 1, "page_size": 2}).json()
    assert set(page) == {"items", "total", "page", "page_size"}
    assert (page["total"], page["page"], page["page_size"], len(page["items"])) == (5, 1, 2, 2)

    beyond = api.get(USERS, headers=admin, params={"page": 99}).json()
    assert beyond["items"] == [] and beyond["total"] == 5

    reps = api.get(USERS, headers=admin, params={"role": "unit_rep"}).json()
    assert reps["total"] == 2
    assert {u["role"] for u in reps["items"]} == {"unit_rep"}

    assert api.get(USERS, headers=admin, params={"page_size": 101}).status_code == 422
    assert api.get(USERS, headers=admin, params={"page": 0}).status_code == 422


def test_get_user_and_not_found(api: TestClient, people: People) -> None:
    admin = bearer(people.admin)
    assert (
        api.get(f"{USERS}/{people.rep_a.id}", headers=admin).json()["email"] == people.rep_a.email
    )
    resp = api.get(f"{USERS}/{uuid.uuid4()}", headers=admin)
    assert (resp.status_code, resp.json()["error"]["code"]) == (404, "USER_NOT_FOUND")
    assert api.get(f"{USERS}/not-a-uuid", headers=admin).status_code == 422


def test_there_is_no_user_delete_endpoint(api: TestClient, people: People) -> None:
    resp = api.delete(f"{USERS}/{people.engineer.id}", headers=bearer(people.admin))
    assert resp.status_code == 405


def test_patch_changes_name_role_and_unit(api: TestClient, people: People) -> None:
    admin = bearer(people.admin)
    url = f"{USERS}/{people.rep_a.id}"

    moved = api.patch(url, headers=admin, json={"unit_id": str(people.unit_b.id)})
    assert moved.json()["unit_id"] == str(people.unit_b.id)

    renamed = api.patch(url, headers=admin, json={"full_name": "New Name"}).json()
    assert renamed["full_name"] == "New Name" and renamed["unit_id"] == str(people.unit_b.id)

    # Leaving the unit_rep role clears the unit automatically.
    promoted = api.patch(url, headers=admin, json={"role": "engineer"}).json()
    assert promoted["role"] == "engineer" and promoted["unit_id"] is None

    # ...and becoming a unit_rep again needs one.
    back = api.patch(url, headers=admin, json={"role": "unit_rep"})
    assert back.json()["error"]["code"] == "UNIT_REQUIRED"
    ok = api.patch(url, headers=admin, json={"role": "unit_rep", "unit_id": str(people.unit_a.id)})
    assert ok.status_code == 200


def test_patch_rejects_unit_for_non_unit_rep_and_clearing_a_reps_unit(
    api: TestClient, people: People
) -> None:
    admin = bearer(people.admin)
    bad = api.patch(
        f"{USERS}/{people.engineer.id}", headers=admin, json={"unit_id": str(people.unit_a.id)}
    )
    assert bad.json()["error"]["code"] == "UNIT_NOT_ALLOWED"
    clear = api.patch(f"{USERS}/{people.rep_a.id}", headers=admin, json={"unit_id": None})
    assert clear.json()["error"]["code"] == "UNIT_REQUIRED"


def test_deactivating_a_user_ends_all_their_sessions(
    api: TestClient, people: People, db: Session
) -> None:
    issue_tokens(db, people.engineer)
    headers = bearer(people.engineer)
    assert api.get("/api/v1/auth/me", headers=headers).status_code == 200

    resp = api.patch(
        f"{USERS}/{people.engineer.id}", headers=bearer(people.admin), json={"is_active": False}
    )
    assert resp.json()["is_active"] is False
    assert api.get("/api/v1/auth/me", headers=headers).status_code == 401
    live = db.query(RefreshToken).filter(RefreshToken.revoked_at.is_(None)).count()
    assert live == 0


def test_admin_password_reset(api: TestClient, people: People, db: Session) -> None:
    issue_tokens(db, people.rep_a)
    resp = api.patch(
        f"{USERS}/{people.rep_a.id}", headers=bearer(people.admin), json={"password": NEW_PASSWORD}
    )
    assert resp.status_code == 200
    assert "password" not in resp.json()

    assert db.query(RefreshToken).filter(RefreshToken.revoked_at.is_(None)).count() == 0
    old = api.post("/api/v1/auth/login", json={"email": people.rep_a.email, "password": PASSWORD})
    assert old.status_code == 401
    new = api.post(
        "/api/v1/auth/login", json={"email": people.rep_a.email, "password": NEW_PASSWORD}
    )
    assert new.status_code == 200


def test_short_reset_password_is_rejected(api: TestClient, people: People) -> None:
    resp = api.patch(
        f"{USERS}/{people.rep_a.id}", headers=bearer(people.admin), json={"password": "short"}
    )
    assert resp.status_code == 422


def test_the_last_active_admin_cannot_be_demoted_or_deactivated(
    api: TestClient, people: People, db: Session
) -> None:
    admin = bearer(people.admin)
    url = f"{USERS}/{people.admin.id}"
    for body in ({"is_active": False}, {"role": "engineer"}):
        resp = api.patch(url, headers=admin, json=body)
        assert (resp.status_code, resp.json()["error"]["code"]) == (409, "LAST_ADMIN"), body

    # A second admin makes the first one removable, and then protects the second.
    second = make_user(db, people.admin.role, email="second-admin@t.test")
    db.commit()
    assert api.patch(url, headers=admin, json={"role": "engineer"}).status_code == 200
    last = api.patch(f"{USERS}/{second.id}", headers=bearer(second), json={"is_active": False})
    assert last.json()["error"]["code"] == "LAST_ADMIN"


def test_inactive_admin_does_not_count_as_a_remaining_admin(
    api: TestClient, people: People, db: Session
) -> None:
    dormant = make_user(db, people.admin.role, email="dormant@t.test", is_active=False)
    db.commit()
    assert dormant.is_active is False
    resp = api.patch(
        f"{USERS}/{people.admin.id}", headers=bearer(people.admin), json={"is_active": False}
    )
    assert resp.json()["error"]["code"] == "LAST_ADMIN"


def test_unit_created_in_same_test_is_assignable(
    api: TestClient, people: People, db: Session
) -> None:
    unit = make_unit(db, name="Unit C", code="C")
    db.commit()
    body = new_user_body(role="unit_rep", unit_id=str(unit.id), email="c@t.test")
    assert api.post(USERS, headers=bearer(people.admin), json=body).status_code == 201
