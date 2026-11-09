import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings


@pytest.mark.parametrize("path", ["/health", "/api/v1/health"])
def test_health_ok(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


@pytest.mark.usefixtures("unreachable_db")
def test_health_503_in_standard_error_format(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.json() == {
        "error": {"code": "DB_UNAVAILABLE", "message": "Database is not reachable", "details": {}}
    }


def test_unknown_route_uses_error_format(client: TestClient) -> None:
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "HTTP_404"


def test_production_rejects_default_secret_key() -> None:
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(env="production", secret_key="change-me")
    with pytest.raises(ValueError, match="at least 32"):
        Settings(env="production", secret_key="too-short")
    assert Settings(env="production", secret_key="x" * 40).env == "production"
