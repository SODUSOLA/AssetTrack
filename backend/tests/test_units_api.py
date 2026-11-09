import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api_helpers import People, bearer

UNITS = "/api/v1/units"


@pytest.mark.parametrize("role", ["admin", "engineer", "auditor", "unit_rep"])
def test_every_signed_in_role_can_list_units(api: TestClient, people: People, role: str) -> None:
    resp = api.get(UNITS, headers=bearer(people.by_role()[role]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert [u["code"] for u in body["items"]] == ["A", "B"]
    assert set(body["items"][0]) == {"id", "name", "code", "is_active", "created_at"}


def test_listing_units_requires_authentication(api: TestClient) -> None:
    assert api.get(UNITS).status_code == 401


def test_admin_creates_and_updates_units(api: TestClient, people: People) -> None:
    admin = bearer(people.admin)
    created = api.post(UNITS, headers=admin, json={"name": " Records ", "code": "REC"})
    assert created.status_code == 201
    unit = created.json()
    assert unit["name"] == "Records" and unit["is_active"] is True

    patched = api.patch(f"{UNITS}/{unit['id']}", headers=admin, json={"is_active": False})
    assert patched.json()["is_active"] is False and patched.json()["code"] == "REC"

    active_only = api.get(UNITS, headers=admin, params={"is_active": True}).json()
    assert "REC" not in [u["code"] for u in active_only["items"]]


@pytest.mark.parametrize(
    "body", [{"name": "Unit A", "code": "NEW"}, {"name": "New name", "code": "A"}]
)
def test_duplicate_unit_name_or_code_is_409(api: TestClient, people: People, body: dict) -> None:
    resp = api.post(UNITS, headers=bearer(people.admin), json=body)
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "UNIT_EXISTS")


def test_renaming_a_unit_onto_an_existing_one_is_409(api: TestClient, people: People) -> None:
    resp = api.patch(
        f"{UNITS}/{people.unit_b.id}", headers=bearer(people.admin), json={"name": "Unit A"}
    )
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "UNIT_EXISTS")


def test_patching_unknown_unit_is_404(api: TestClient, people: People) -> None:
    resp = api.patch(f"{UNITS}/{uuid.uuid4()}", headers=bearer(people.admin), json={"code": "Z"})
    assert (resp.status_code, resp.json()["error"]["code"]) == (404, "UNIT_NOT_FOUND")


def test_unit_validation(api: TestClient, people: People) -> None:
    resp = api.post(UNITS, headers=bearer(people.admin), json={"name": " ", "code": "X"})
    assert resp.status_code == 422


@pytest.mark.parametrize("role", ["admin", "engineer", "auditor", "unit_rep"])
def test_repairs_are_in_house_so_there_are_no_vendor_endpoints(
    api: TestClient, people: People, role: str
) -> None:
    headers = bearer(people.by_role()[role])
    assert api.get("/api/v1/vendors", headers=headers).status_code == 404
    assert api.post("/api/v1/vendors", headers=headers, json={"name": "X"}).status_code == 404
    paths = api.get("/api/v1/openapi.json").json()["paths"]
    assert not [p for p in paths if "vendor" in p]
