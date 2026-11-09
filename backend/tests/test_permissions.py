"""SPEC 5.1 permission matrix, plus route-walking guards that also cover later milestones."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import API_PREFIX, app
from tests.api_helpers import People, bearer

ALL = {"admin", "engineer", "auditor", "unit_rep"}
UID = "00000000-0000-0000-0000-000000000001"

# (method, path, roles allowed). Allowed means "gets past the permission check": the response may
# still be 404/422 because the test sends an empty body or a made-up id.
MATRIX = [
    ("GET", "/auth/me", ALL),
    ("GET", "/users", {"admin"}),
    ("POST", "/users", {"admin"}),
    ("GET", f"/users/{UID}", {"admin"}),
    ("PATCH", f"/users/{UID}", {"admin"}),
    ("GET", "/units", ALL),
    ("POST", "/units", {"admin"}),
    ("PATCH", f"/units/{UID}", {"admin"}),
    ("POST", "/devices", {"admin", "engineer"}),
    ("GET", "/devices", ALL),
    ("GET", f"/devices/{UID}", ALL),
    ("PATCH", f"/devices/{UID}", {"admin", "engineer"}),
    ("GET", f"/devices/{UID}/timeline", ALL),
    ("GET", f"/units/{UID}/devices", ALL),
    ("POST", "/complaints", {"admin", "engineer", "unit_rep"}),
    ("GET", "/complaints", ALL),
    ("GET", f"/complaints/{UID}", ALL),
    ("PATCH", f"/complaints/{UID}", {"admin", "engineer"}),
    ("GET", f"/complaints/{UID}/comments", ALL),
    ("POST", f"/complaints/{UID}/comments", {"admin", "engineer", "unit_rep"}),
    ("POST", f"/complaints/{UID}/confirm", {"unit_rep"}),
    ("POST", f"/complaints/{UID}/reopen", {"admin", "engineer", "unit_rep"}),
    ("POST", f"/devices/{UID}/events", {"admin", "engineer"}),
    ("GET", "/events", ALL),
    ("GET", "/events/1", ALL),
    ("POST", "/events/1/acknowledge", {"unit_rep"}),
    ("GET", "/acknowledgements/pending", ALL),
    ("GET", "/reports/monthly-activity", ALL),
    ("GET", "/reports/open-tickets", ALL),
    ("GET", "/reports/turnaround", ALL),
    ("GET", "/reports/repeat-faults", ALL),
    ("GET", "/reports/awaiting-unit", ALL),
]


@pytest.mark.parametrize(("method", "path", "allowed"), MATRIX)
@pytest.mark.parametrize("role", sorted(ALL))
def test_permission_matrix(
    api: TestClient, people: People, method: str, path: str, allowed: set[str], role: str
) -> None:
    resp = api.request(method, API_PREFIX + path, headers=bearer(people.by_role()[role]), json={})
    if role in allowed:
        assert resp.status_code not in (401, 403), resp.text
    else:
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"


# ---------- route walking ----------

PUBLIC = {
    ("GET", f"{API_PREFIX}/health"),
    ("POST", f"{API_PREFIX}/auth/login"),
    ("POST", f"{API_PREFIX}/auth/refresh"),
    ("POST", f"{API_PREFIX}/auth/logout"),
}
# Writes every signed-in role may perform on their own account.
SELF_SERVICE_WRITES = {("POST", f"{API_PREFIX}/auth/change-password")}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


HTTP_METHODS = {"get", "put", "post", "delete", "patch"}


def api_routes() -> list[tuple[str, str]]:
    """(METHOD, path template) for every documented API route, read from the OpenAPI schema.

    Routes marked include_in_schema=False are not covered; keep those outside /api/v1.
    """
    found = []
    for path, operations in app.openapi()["paths"].items():
        if path.startswith(API_PREFIX):
            found.extend((method.upper(), path) for method in operations if method in HTTP_METHODS)
    return sorted(found)


def concrete(path: str) -> str:
    out = path
    while "{" in out:
        start, end = out.index("{"), out.index("}")
        out = out[:start] + str(uuid.uuid4()) + out[end + 1 :]
    return out


def test_route_walk_finds_the_known_routes() -> None:
    routes = set(api_routes())
    assert ("POST", f"{API_PREFIX}/auth/login") in routes
    assert ("PATCH", f"{API_PREFIX}/users/{{user_id}}") in routes
    assert len(routes) >= 15


@pytest.mark.parametrize(("method", "path"), [r for r in api_routes() if r not in PUBLIC])
def test_every_non_public_route_requires_authentication(
    api: TestClient, method: str, path: str
) -> None:
    resp = api.request(method, concrete(path), json={})
    assert resp.status_code == 401, f"{method} {path} is reachable without a token"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        r
        for r in api_routes()
        if r[0] in WRITE_METHODS and r not in PUBLIC and r not in SELF_SERVICE_WRITES
    ],
)
def test_auditor_gets_403_on_every_write_endpoint(
    api: TestClient, people: People, method: str, path: str
) -> None:
    resp = api.request(method, concrete(path), headers=bearer(people.auditor), json={})
    assert resp.status_code == 403, f"{method} {path} accepted an auditor"
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_public_routes_are_exactly_the_expected_ones(api: TestClient) -> None:
    """A new unauthenticated route must be added to PUBLIC deliberately."""
    open_routes = set()
    for method, path in api_routes():
        resp = api.request(method, concrete(path), json={})
        if resp.status_code != 401:
            open_routes.add((method, path))
    # /auth/refresh is public but authenticates by cookie, so with no cookie it also answers 401.
    assert open_routes | {("POST", f"{API_PREFIX}/auth/refresh")} == PUBLIC
