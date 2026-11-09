"""Real concurrency and least-privilege checks (SPEC 8.5, 12.1 test 5, 4.2 hardening).

These tests commit real data through separate connections and use threads, so they cannot run
inside the rolled-back transaction the other tests use. Audit rows cannot be deleted, so each test
resets the whole test schema when it is done.
"""

import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import Device, DeviceEvent, User
from app.models.enums import AckStatus, DeviceStatus, EventType, UserRole
from app.schemas.events import EventCreate
from app.services import events as event_service
from tests.conftest import TEST_DATABASE_URL, reset_schema
from tests.event_helpers import API, acknowledge, ok, post_event
from tests.factories import make_device, make_event, make_unit, make_user

S = DeviceStatus
EVENT = TypeAdapter(EventCreate)


@pytest.fixture
def committed(engine: Engine) -> Iterator[Engine]:
    """Use `engine` for real, committed work; the schema is rebuilt afterwards."""
    yield engine
    engine.dispose()
    reset_schema(engine)


def seed(engine: Engine, status: S = S.assigned, **extra: Any) -> dict[str, Any]:
    """One unit with two reps, an engineer and a device in `status`. Ids only."""
    with Session(engine) as s:
        unit = make_unit(s)
        engineer = make_user(s, UserRole.engineer)
        reps = [make_user(s, UserRole.unit_rep, unit) for _ in range(2)]
        device = make_device(s, engineer, unit_id=unit.id, status=status, **extra)
        s.commit()
        return {
            "unit": unit.id, "engineer": engineer.id, "reps": [r.id for r in reps],
            "device": device.id,
        }  # fmt: skip


def run_parallel(engine: Engine, calls: list[Callable[[Session], Any]]) -> list[tuple[str, Any]]:
    """Run each call in its own thread and session, released together by a barrier."""
    barrier = threading.Barrier(len(calls))
    results: list[tuple[str, Any]] = [("unfinished", None)] * len(calls)

    def worker(i: int) -> None:
        with Session(engine) as s:
            barrier.wait(timeout=20)
            try:
                results[i] = ("ok", calls[i](s))
            except AppError as exc:
                results[i] = ("error", exc.code)
            except Exception as exc:  # noqa: BLE001 - reported by the assertion
                results[i] = ("crash", repr(exc))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(calls))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def log_event(user_id, device_id, **body) -> Callable[[Session], Any]:
    def call(s: Session) -> Any:
        actor = s.get(User, user_id)
        return event_service.record_event(s, actor, device_id, EVENT.validate_python(body))

    return call


def chain(engine: Engine, device_id) -> list[DeviceEvent]:
    with Session(engine) as s:
        return list(
            s.query(DeviceEvent).filter_by(device_id=device_id).order_by(DeviceEvent.id).all()
        )


# ---------- SPEC 12.1 test 5 ----------


def test_simultaneous_identical_events_yield_exactly_one_success(committed: Engine) -> None:
    world = seed(committed, S.received_for_repair)
    call = log_event(world["engineer"], world["device"], event_type="diagnosed", diagnosis="Dead")
    results = run_parallel(committed, [call] * 8)

    assert [r[0] for r in results].count("ok") == 1, results
    assert [r for r in results if r[0] != "ok"] == [("error", "INVALID_TRANSITION")] * 7
    events = chain(committed, world["device"])
    assert [e.event_type for e in events] == [EventType.diagnosed]
    with Session(committed) as s:
        assert s.get(Device, world["device"]).status is S.diagnosed


def test_racing_different_events_always_leave_a_consistent_history(committed: Engine) -> None:
    """From `diagnosed` three events compete; whichever order wins, the log must stay a chain."""
    for _ in range(4):
        world = seed(committed, S.diagnosed)
        d, e = world["device"], world["engineer"]
        calls = [
            log_event(e, d, event_type="repair_started"),
            log_event(e, d, event_type="repair_completed", notes="Fixed"),
            log_event(e, d, event_type="decommissioned", notes="Beyond repair"),
            log_event(e, d, event_type="repair_started"),
            log_event(e, d, event_type="note_added", notes="fyi"),
        ]
        results = run_parallel(committed, calls)
        assert not [r for r in results if r[0] in ("crash", "unfinished")], results
        assert all(r[1] == "INVALID_TRANSITION" for r in results if r[0] == "error"), results

        events = chain(committed, d)
        assert len(events) == [r[0] for r in results].count("ok") and events
        previous = S.diagnosed
        for event in events:
            assert event.from_status in (previous, None) or event.event_type is EventType.note_added
            previous = event.to_status
        with Session(committed) as s:
            assert s.get(Device, d).status is previous  # device == where the log ended
        stamps = [e.occurred_at for e in events]
        assert stamps == sorted(stamps)  # time order == lock order


def test_simultaneous_acknowledgements_yield_exactly_one(committed: Engine) -> None:
    world = seed(committed)
    with Session(committed) as s:
        device = s.get(Device, world["device"])
        engineer = s.get(User, world["engineer"])
        event = make_event(
            s, device, engineer, event_type=EventType.assigned_to_unit,
            counterparty_name="Ada", to_status=S.assigned, unit_id=world["unit"],
        )  # fmt: skip
        s.commit()
        event_id = event.id

    def ack(rep_id, status):
        def call(s: Session) -> Any:
            rep = s.get(User, rep_id)
            comment = "no" if status is AckStatus.disputed else None
            return event_service.acknowledge(s, rep, event_id, status, comment)

        return call

    calls = [ack(world["reps"][0], AckStatus.confirmed), ack(world["reps"][1], AckStatus.disputed)]
    calls += [ack(world["reps"][0], AckStatus.confirmed)] * 2
    results = run_parallel(committed, calls)
    assert [r[0] for r in results].count("ok") == 1, results
    assert [r for r in results if r[0] != "ok"] == [("error", "ALREADY_ACKNOWLEDGED")] * 3
    with Session(committed) as s:
        count = s.execute(
            text("SELECT count(*) FROM acknowledgements WHERE event_id = :e"), {"e": event_id}
        ).scalar()
    assert count == 1


# ---------- the application role from SPEC 4.2: INSERT and SELECT only on audit tables ----------

APP_ROLE, APP_PASSWORD = "audit_app", "audit_app"


def grant_least_privilege(engine: Engine) -> Engine:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""DO $$ BEGIN
                  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}';
                  END IF; END $$"""
            )
        )
        for statement in (
            f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
            f"GRANT SELECT, INSERT, UPDATE ON units, users, devices, complaints, "
            f"refresh_tokens TO {APP_ROLE}",
            f"GRANT SELECT, INSERT ON device_events, acknowledgements, complaint_comments "
            f"TO {APP_ROLE}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}",
        ):
            conn.execute(text(statement))
    url = make_url(TEST_DATABASE_URL).set(username=APP_ROLE, password=APP_PASSWORD)
    return create_engine(url)


def test_the_whole_lifecycle_works_with_insert_and_select_only_on_audit_tables(
    committed: Engine,
) -> None:
    world = seed(committed, S.in_stock, serial_number="SN-LP-1")
    with Session(committed, expire_on_commit=False) as s:
        engineer, rep = s.get(User, world["engineer"]), s.get(User, world["reps"][0])
        admin = make_user(s, UserRole.admin)
        s.commit()
    restricted = grant_least_privilege(committed)

    def restricted_db() -> Iterator[Session]:
        with Session(restricted) as s:
            yield s

    app.dependency_overrides[get_db] = restricted_db
    headers = {
        u: {"Authorization": f"Bearer {create_access_token(user)[0]}"}
        for u, user in {"eng": engineer, "rep": rep, "admin": admin}.items()
    }
    try:
        with TestClient(app) as api:
            device_id = str(world["device"])
            assign = ok(
                post_event(
                    api, engineer, device_id, "assigned_to_unit",
                    unit_id=str(world["unit"]), counterparty_name="Ada",
                )
            )  # fmt: skip
            ok(acknowledge(api, rep, assign["id"]))
            ticket = ok(api.post(f"{API}/complaints", headers=headers["rep"], json={
                "title": "No power", "description": "Dead", "device_id": device_id}))  # fmt: skip
            patch = api.patch(f"{API}/devices/{device_id}", headers=headers["eng"],
                              json={"model": "Latitude"})  # fmt: skip
            assert patch.status_code == 200, patch.text
            intake = ok(post_event(api, engineer, device_id, "received_for_repair",
                                   complaint_id=ticket["id"], counterparty_name="Ada"))  # fmt: skip
            ok(acknowledge(api, rep, intake["id"]))
            ok(post_event(api, engineer, device_id, "diagnosed", diagnosis="Battery"))
            ok(post_event(api, engineer, device_id, "repair_started"))
            ok(post_event(api, engineer, device_id, "repair_completed", notes="Fixed"))
            back = ok(
                post_event(api, engineer, device_id, "returned_to_unit", counterparty_name="Ada")
            )
            comment = api.post(f"{API}/complaints/{ticket['id']}/comments", headers=headers["rep"],
                               json={"body": "Thanks"})  # fmt: skip
            assert comment.status_code == 201, comment.text
            ok(acknowledge(api, rep, back["id"]))
            final = api.get(f"{API}/complaints/{ticket['id']}", headers=headers["admin"]).json()
            assert final["status"] == "closed"
            assert [e["event_type"] for e in final["events"]][0] == "received_for_repair"
            ok(post_event(api, engineer, device_id, "decommissioned", notes="Retired"))
            assert (
                api.get(f"{API}/devices/{device_id}", headers=headers["admin"]).json()["status"]
                == "decommissioned"
            )

        # And the role really is as restricted as the spec says.
        with restricted.connect() as conn:
            for statement in (
                "UPDATE device_events SET notes = 'tampered'",
                "DELETE FROM acknowledgements",
                "UPDATE complaint_comments SET body = 'tampered'",
                "SELECT id FROM device_events FOR UPDATE",
            ):
                with pytest.raises(DBAPIError) as exc:
                    conn.execute(text(statement))
                assert exc.value.orig.sqlstate == "42501", statement  # insufficient_privilege
                conn.rollback()
    finally:
        app.dependency_overrides.clear()
        restricted.dispose()
