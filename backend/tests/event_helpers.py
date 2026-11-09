"""Shared helpers for event and acknowledgement tests."""

from fastapi.testclient import TestClient

from tests.api_helpers import bearer

API = "/api/v1"


def device_id(device) -> str:
    return str(getattr(device, "id", device))


def post_event(api: TestClient, user, device, event_type: str, **body):
    return api.post(
        f"{API}/devices/{device_id(device)}/events",
        headers=bearer(user),
        json={"event_type": event_type, **body},
    )


def ok(resp, status: int = 201) -> dict:
    assert resp.status_code == status, resp.text
    return resp.json()


def acknowledge(api: TestClient, user, event_id: int, status: str = "confirmed", **body):
    return api.post(
        f"{API}/events/{event_id}/acknowledge",
        headers=bearer(user),
        json={"status": status, **body},
    )
