"""remove vendors: repairs are done in-house

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02

Decision of the agency (SPEC v1.2): no repair is ever sent to an outside vendor, so the system has
no vendor concept. This drops the `vendors` table, `device_events.vendor_id` and its rule, the
`sent_to_vendor` event type and the `with_vendor` device status.

The permanent record is not touched. `device_events` is append-only, so this migration refuses to
run if any event or device already uses a vendor (it names what it found and changes nothing).
Changing a column's type rewrites the table without firing the row guards, so no row is edited,
deleted or truncated in the eyes of the guards, and they stay in place; the checks that read
`event_type` are dropped and re-added unchanged around the change, because PostgreSQL cannot
compare the old and the new type.

`downgrade()` recreates the empty structure. It cannot bring back vendor data, and there is none
to bring back: the upgrade refuses to run when there is any.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# `%%` because the driver treats a single `%` as a parameter marker; PostgreSQL sees `%`.
REFUSE = """
DO $$
DECLARE
  sent integer;
  held integer;
BEGIN
  SELECT count(*) INTO sent FROM device_events
    WHERE event_type = 'sent_to_vendor' OR vendor_id IS NOT NULL
       OR to_status = 'with_vendor' OR from_status = 'with_vendor';
  SELECT count(*) INTO held FROM devices WHERE status = 'with_vendor';
  IF sent > 0 OR held > 0 THEN
    RAISE EXCEPTION
      'Cannot remove vendors: %% event(s) and %% device(s) still refer to a vendor. '
      'The record is append-only, so nothing was changed. Decide how to handle that history first.',
      sent, held;
  END IF;
END $$
"""

# Constraints that read `event_type`; recreated exactly as 0001 defined them.
EVENT_CHECKS = {
    "diagnosed_needs_diagnosis": "CHECK (event_type <> 'diagnosed' OR diagnosis IS NOT NULL)",
    "return_needs_collector": (
        "CHECK (event_type <> 'returned_to_unit' OR counterparty_name IS NOT NULL)"
    ),
    "intake_needs_depositor": (
        "CHECK (event_type <> 'received_for_repair' OR counterparty_name IS NOT NULL)"
    ),
}

STATUS_NEW = (
    "'in_stock', 'assigned', 'received_for_repair', 'diagnosed', 'in_repair', "
    "'awaiting_parts', 'repaired', 'decommissioned'"
)
STATUS_OLD = (
    "'in_stock', 'assigned', 'received_for_repair', 'diagnosed', 'in_repair', "
    "'awaiting_parts', 'with_vendor', 'repaired', 'decommissioned'"
)
EVENT_NEW = (
    "'device_registered', 'assigned_to_unit', 'received_for_repair', 'diagnosed', "
    "'repair_started', 'parts_requested', 'repair_completed', 'returned_to_unit', "
    "'decommissioned', 'note_added'"
)
EVENT_OLD = (
    "'device_registered', 'assigned_to_unit', 'received_for_repair', 'diagnosed', "
    "'repair_started', 'parts_requested', 'sent_to_vendor', 'repair_completed', "
    "'returned_to_unit', 'decommissioned', 'note_added'"
)


def _retype_enums(status_values: str, event_values: str) -> list[str]:
    """Replace the two enum types with the given values, converting every column that uses them."""
    drop_checks = ", ".join(f"DROP CONSTRAINT {name}" for name in EVENT_CHECKS)
    add_checks = ", ".join(f"ADD CONSTRAINT {name} {rule}" for name, rule in EVENT_CHECKS.items())
    return [
        "ALTER TYPE device_status RENAME TO device_status_old",
        f"CREATE TYPE device_status AS ENUM ({status_values})",
        "ALTER TABLE devices ALTER COLUMN status DROP DEFAULT",
        "ALTER TABLE devices ALTER COLUMN status TYPE device_status "
        "USING status::text::device_status",
        "ALTER TABLE devices ALTER COLUMN status SET DEFAULT 'in_stock'",
        "ALTER TABLE device_events ALTER COLUMN from_status TYPE device_status "
        "USING from_status::text::device_status",
        "ALTER TABLE device_events ALTER COLUMN to_status TYPE device_status "
        "USING to_status::text::device_status",
        "DROP TYPE device_status_old",
        f"ALTER TABLE device_events {drop_checks}",
        "ALTER TYPE event_type RENAME TO event_type_old",
        f"CREATE TYPE event_type AS ENUM ({event_values})",
        "ALTER TABLE device_events ALTER COLUMN event_type TYPE event_type "
        "USING event_type::text::event_type",
        "DROP TYPE event_type_old",
        f"ALTER TABLE device_events {add_checks}",
    ]


UP = [
    REFUSE,
    "ALTER TABLE device_events DROP CONSTRAINT vendor_event_needs_vendor",
    "ALTER TABLE device_events DROP COLUMN vendor_id",
    "DROP TABLE vendors",
    *_retype_enums(STATUS_NEW, EVENT_NEW),
]

DOWN = [
    """CREATE TABLE vendors (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      name TEXT NOT NULL UNIQUE,
      phone TEXT,
      address TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    *_retype_enums(STATUS_OLD, EVENT_OLD),
    "ALTER TABLE device_events ADD COLUMN vendor_id UUID REFERENCES vendors(id)",
    "ALTER TABLE device_events ADD CONSTRAINT vendor_event_needs_vendor "
    "CHECK (event_type <> 'sent_to_vendor' OR vendor_id IS NOT NULL)",
]


def upgrade() -> None:
    bind = op.get_bind()
    for statement in UP:
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    bind = op.get_bind()
    for statement in DOWN:
        bind.exec_driver_sql(statement)
