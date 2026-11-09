"""Migration 0006 removes the vendor concept without touching the permanent record."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from tests.conftest import alembic_config, reset_schema

UNIT = "11111111-1111-4111-8111-111111111111"
USER = "22222222-2222-4222-8222-222222222222"
DEVICE = "33333333-3333-4333-8333-333333333333"
VENDOR = "44444444-4444-4444-8444-444444444444"


@pytest.fixture
def at_0005(engine: Engine) -> Iterator[Engine]:
    """The schema as it was before vendors were removed, put back to head afterwards."""
    command.downgrade(alembic_config(), "0005")
    yield engine
    reset_schema(engine)


def seed(engine: Engine, *, vendor_history: bool = False, device_status: str = "assigned") -> None:
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO units(id, name, code) VALUES ('{UNIT}', 'U', 'U')"))
        conn.execute(
            text(
                f"INSERT INTO users(id, full_name, email, password_hash, role) "
                f"VALUES ('{USER}', 'A', 'a@x.test', 'h', 'admin')"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO devices(id, device_type, status, created_by, unit_id) "
                f"VALUES ('{DEVICE}', 'laptop', '{device_status}', '{USER}', '{UNIT}')"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO device_events(device_id, event_type, from_status, to_status, "
                f"actor_id, unit_id, counterparty_name) VALUES ('{DEVICE}', 'assigned_to_unit', "
                f"'in_stock', 'assigned', '{USER}', '{UNIT}', 'Ada')"
            )
        )
        conn.execute(text(f"INSERT INTO vendors(id, name) VALUES ('{VENDOR}', 'FixIt')"))
        if vendor_history:
            conn.execute(
                text(
                    f"INSERT INTO device_events(device_id, event_type, from_status, to_status, "
                    f"actor_id, vendor_id) VALUES ('{DEVICE}', 'sent_to_vendor', 'diagnosed', "
                    f"'with_vendor', '{USER}', '{VENDOR}')"
                )
            )


def scalar(engine: Engine, sql: str):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def enum_values(engine: Engine, name: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT unnest(enum_range(NULL::{name}))::text")).all()
    return {r[0] for r in rows}


def test_the_record_and_its_guards_survive_the_upgrade(at_0005: Engine) -> None:
    seed(at_0005)
    command.upgrade(alembic_config(), "0006")

    assert scalar(at_0005, "SELECT to_regclass('vendors')") is None
    assert scalar(at_0005, "SELECT count(*) FROM device_events") == 1
    assert scalar(at_0005, f"SELECT status::text FROM devices WHERE id = '{DEVICE}'") == "assigned"
    assert "sent_to_vendor" not in enum_values(at_0005, "event_type")
    assert "with_vendor" not in enum_values(at_0005, "device_status")
    assert enum_values(at_0005, "device_status") >= {"in_stock", "in_repair", "repaired"}
    assert not scalar(
        at_0005,
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name = 'device_events' AND column_name = 'vendor_id'",
    )

    # Still append-only: no edit, no delete, no truncate, exactly as before.
    for statement in (
        "UPDATE device_events SET notes = 'x'",
        "DELETE FROM device_events",
        "TRUNCATE device_events CASCADE",
    ):
        with pytest.raises(DBAPIError) as caught, at_0005.begin() as conn:
            conn.execute(text(statement))
        assert getattr(caught.value.orig, "sqlstate", None) == "23001", statement

    # The rules on what an event must contain are still there.
    with pytest.raises(DBAPIError, match="diagnosed_needs_diagnosis"), at_0005.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO device_events(device_id, event_type, to_status, actor_id) "
                f"VALUES ('{DEVICE}', 'diagnosed', 'diagnosed', '{USER}')"
            )
        )
    # New devices still start in stock.
    with at_0005.begin() as conn:
        status = conn.execute(
            text(
                f"INSERT INTO devices(device_type, created_by) "
                f"VALUES ('x', '{USER}') RETURNING status"
            )
        ).scalar()
    assert str(status) == "in_stock"


@pytest.mark.parametrize(
    ("kwargs", "what"),
    [
        ({"vendor_history": True}, "a device was sent to a vendor"),
        ({"device_status": "with_vendor"}, "a device is with a vendor"),
    ],
)
def test_it_refuses_to_run_when_vendor_history_exists(
    at_0005: Engine, kwargs: dict, what: str
) -> None:
    seed(at_0005, **kwargs)
    with pytest.raises(Exception, match="vendor"):
        command.upgrade(alembic_config(), "0006")
    # Nothing changed: still at 0005, the record intact, the table still there.
    assert scalar(at_0005, "SELECT version_num FROM alembic_version") == "0005"
    assert scalar(at_0005, "SELECT to_regclass('vendors')") is not None
    assert scalar(at_0005, "SELECT count(*) FROM device_events") >= 1
    assert "sent_to_vendor" in enum_values(at_0005, "event_type"), what


def test_the_downgrade_recreates_the_empty_structure(engine: Engine) -> None:
    try:
        command.downgrade(alembic_config(), "0005")
        assert scalar(engine, "SELECT to_regclass('vendors')") is not None
        assert scalar(engine, "SELECT count(*) FROM vendors") == 0
        assert {"sent_to_vendor"} <= enum_values(engine, "event_type")
        assert {"with_vendor"} <= enum_values(engine, "device_status")
        command.upgrade(alembic_config(), "head")  # and it can go forward again
        assert scalar(engine, "SELECT to_regclass('vendors')") is None
    finally:
        reset_schema(engine)
