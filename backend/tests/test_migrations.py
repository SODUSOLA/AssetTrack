from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from alembic import command
from app.db.base import Base
from tests.conftest import alembic_config

EXPECTED_TABLES = {
    "units",
    "users",
    "devices",
    "complaints",
    "complaint_comments",
    "device_events",
    "acknowledgements",
    "refresh_tokens",
}


def test_migration_round_trip(engine: Engine) -> None:
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    with engine.connect() as conn:
        assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
        assert (
            conn.execute(text("SELECT count(*) FROM pg_type WHERE typname = 'event_type'")).scalar()
            == 0
        )

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert EXPECTED_TABLES <= set(inspect(conn).get_table_names())


def test_models_match_migrated_schema(engine: Engine) -> None:
    """Drift check: ORM metadata and the hand-written migration describe the same schema."""
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == []
