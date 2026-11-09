"""The built web app is served from /app on the same origin as the API."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.spa import CSP, NONCE_PLACEHOLDER, content_security_policy
from app.main import create_app


@pytest.fixture
def built(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        f'<!doctype html><title>shell</title><meta name="csp-nonce" content="{NONCE_PLACEHOLDER}">'
    )
    (tmp_path / "assets" / "app.1a2b3c.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    return tmp_path


@pytest.fixture
def client(built: Path) -> TestClient:
    return TestClient(create_app(static_dir=built), follow_redirects=False)


def test_the_shell_is_served_at_app(client: TestClient) -> None:
    for path in ("/app", "/app/"):
        resp = client.get(path, follow_redirects=True)
        assert resp.status_code == 200 and "<title>shell</title>" in resp.text


@pytest.mark.parametrize("path", ["/app/devices", "/app/devices/0d5c-4a", "/app/complaints/x/y"])
def test_deep_links_get_the_shell_so_reloads_work(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200 and "<title>shell</title>" in resp.text


def test_missing_assets_are_404_not_the_shell(client: TestClient) -> None:
    for path in ("/app/assets/missing.js", "/app/nothing.css", "/app/logo.png"):
        assert client.get(path).status_code == 404


def test_caching_rules(client: TestClient) -> None:
    hashed = client.get("/app/assets/app.1a2b3c.js")
    assert hashed.headers["cache-control"] == "public, max-age=31536000, immutable"
    for path in ("/app/", "/app/devices", "/app/favicon.svg"):
        assert client.get(path, follow_redirects=True).headers["cache-control"] == "no-cache"


def _nonce_of(response) -> str:
    """The nonce a page was given, read from its own markup."""
    marker = 'name="csp-nonce" content="'
    start = response.text.index(marker) + len(marker)
    return response.text[start : response.text.index('"', start)]


def test_every_page_gets_its_own_nonce_in_the_markup_and_the_policy(client: TestClient) -> None:
    first, second = client.get("/app/devices"), client.get("/app/devices")
    nonces = {_nonce_of(first), _nonce_of(second)}
    assert len(nonces) == 2 and NONCE_PLACEHOLDER not in first.text
    for response in (first, second):
        nonce = _nonce_of(response)
        assert len(nonce) >= 20
        assert response.headers["content-security-policy"] == content_security_policy(nonce)
        assert f"style-src 'self' 'nonce-{nonce}'" in response.headers["content-security-policy"]


def test_only_styles_may_carry_a_nonce_and_scripts_never_can(client: TestClient) -> None:
    csp = client.get("/app/").headers["content-security-policy"]
    script = next(rule for rule in csp.split("; ") if rule.startswith("script-src"))
    assert script == "script-src 'self'"
    assert csp.count("nonce-") == 1


def test_assets_get_the_policy_without_any_nonce(client: TestClient) -> None:
    assert client.get("/app/assets/app.1a2b3c.js").headers["content-security-policy"] == CSP
    assert "nonce" not in CSP


def test_the_app_has_a_strict_content_security_policy(client: TestClient) -> None:
    csp = client.get("/app/devices").headers["content-security-policy"]
    for rule in (
        "default-src 'self'",
        "script-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
    ):
        assert rule in csp
    for forbidden in ("unsafe-inline", "unsafe-eval", "http:", "https:"):
        assert forbidden not in csp


def test_every_response_gets_basic_security_headers(client: TestClient) -> None:
    for path in ("/app/", "/api/v1/nope", "/api/v1/openapi.json"):
        headers = client.get(path, follow_redirects=True).headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["x-frame-options"] == "DENY"


def test_the_policy_is_not_applied_to_the_api_or_its_docs(client: TestClient) -> None:
    assert "content-security-policy" not in client.get("/api/v1/openapi.json").headers
    assert "content-security-policy" not in client.get("/docs").headers  # Swagger needs its CDN


def test_unknown_api_routes_stay_json_404s(client: TestClient) -> None:
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "HTTP_404"


def test_root_redirects_to_the_app(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code in (302, 307) and resp.headers["location"] == "/app/"


def test_without_a_build_root_points_at_the_docs_and_app_is_absent(tmp_path: Path) -> None:
    client = TestClient(create_app(static_dir=tmp_path), follow_redirects=False)
    assert client.get("/").headers["location"] == "/docs"
    assert client.get("/app/").status_code == 404
