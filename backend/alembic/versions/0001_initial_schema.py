"""initial schema, audit tables and immutability guards

Revision ID: 0001
Revises:
Create Date: 2026-10-23

Hand-written from SPEC.md section 4.2. Additions beyond the spec DDL:
  * guard exceptions use ERRCODE restrict_violation (SQLSTATE 23001), so the service layer
    can catch them by code instead of matching message text;
  * BEFORE TRUNCATE guards on the append-only tables and on costs (row triggers do not fire
    on TRUNCATE).

Statements are sent with exec_driver_sql and contain no percent signs or colon parameters.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UP = [
    # ===== EXTENSIONS =====
    "CREATE EXTENSION IF NOT EXISTS citext",
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    # ===== ENUMS =====
    "CREATE TYPE user_role AS ENUM ('admin', 'engineer', 'unit_rep', 'auditor')",
    """CREATE TYPE device_status AS ENUM (
      'in_stock', 'assigned', 'received_for_repair', 'diagnosed',
      'in_repair', 'awaiting_parts', 'with_vendor', 'repaired', 'decommissioned'
    )""",
    """CREATE TYPE event_type AS ENUM (
      'device_registered', 'assigned_to_unit', 'received_for_repair', 'diagnosed',
      'repair_started', 'parts_requested', 'sent_to_vendor', 'repair_completed',
      'returned_to_unit', 'decommissioned', 'note_added'
    )""",
    "CREATE TYPE complaint_status AS ENUM "
    "('open', 'in_progress', 'resolved', 'closed', 'reopened')",
    "CREATE TYPE complaint_category AS ENUM ('hardware', 'software', 'network', 'other')",
    "CREATE TYPE priority_level AS ENUM ('low', 'medium', 'high', 'critical')",
    "CREATE TYPE cost_kind AS ENUM ('purchase', 'repair', 'parts', 'other')",
    "CREATE TYPE ack_status AS ENUM ('confirmed', 'disputed')",
    # ===== SEQUENCES =====
    "CREATE SEQUENCE asset_tag_seq START 1",
    "CREATE SEQUENCE ticket_no_seq START 1",
    # ===== CORE TABLES =====
    """CREATE TABLE units (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      name TEXT NOT NULL UNIQUE,
      code TEXT NOT NULL UNIQUE,
      is_active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE users (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      full_name TEXT NOT NULL,
      email CITEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      role user_role NOT NULL,
      unit_id UUID REFERENCES units(id),
      is_active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT unit_rep_requires_unit CHECK (role <> 'unit_rep' OR unit_id IS NOT NULL)
    )""",
    """CREATE TABLE vendors (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      name TEXT NOT NULL UNIQUE,
      phone TEXT,
      address TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE devices (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      asset_tag TEXT NOT NULL UNIQUE
        DEFAULT ('LAS-ENG-' || lpad(nextval('asset_tag_seq')::text, 6, '0')),
      serial_number TEXT UNIQUE,
      device_type TEXT NOT NULL,
      make TEXT,
      model TEXT,
      unit_id UUID REFERENCES units(id),
      status device_status NOT NULL DEFAULT 'in_stock',
      acquired_on DATE,
      created_by UUID NOT NULL REFERENCES users(id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX idx_devices_unit ON devices(unit_id)",
    "CREATE INDEX idx_devices_status ON devices(status)",
    """CREATE TABLE complaints (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      ticket_no TEXT NOT NULL UNIQUE
        DEFAULT ('TKT-' || to_char(now(), 'YYYY') || '-'
                 || lpad(nextval('ticket_no_seq')::text, 5, '0')),
      unit_id UUID NOT NULL REFERENCES units(id),
      raised_by UUID NOT NULL REFERENCES users(id),
      device_id UUID REFERENCES devices(id),
      category complaint_category NOT NULL DEFAULT 'hardware',
      title TEXT NOT NULL,
      description TEXT NOT NULL,
      priority priority_level NOT NULL DEFAULT 'medium',
      status complaint_status NOT NULL DEFAULT 'open',
      assigned_to UUID REFERENCES users(id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      resolved_at TIMESTAMPTZ,
      closed_at TIMESTAMPTZ
    )""",
    "CREATE INDEX idx_complaints_unit_status ON complaints(unit_id, status)",
    """CREATE TABLE complaint_comments (
      id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      complaint_id UUID NOT NULL REFERENCES complaints(id),
      author_id UUID NOT NULL REFERENCES users(id),
      body TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",
    # ===== AUDIT CORE =====
    """CREATE TABLE device_events (
      id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      device_id UUID NOT NULL REFERENCES devices(id),
      complaint_id UUID REFERENCES complaints(id),
      unit_id UUID REFERENCES units(id),
      event_type event_type NOT NULL,
      from_status device_status,
      to_status device_status NOT NULL,
      actor_id UUID NOT NULL REFERENCES users(id),
      counterparty_name TEXT,
      counterparty_user_id UUID REFERENCES users(id),
      vendor_id UUID REFERENCES vendors(id),
      diagnosis TEXT,
      notes TEXT,
      corrects_event_id BIGINT REFERENCES device_events(id),
      occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT diagnosed_needs_diagnosis
        CHECK (event_type <> 'diagnosed' OR diagnosis IS NOT NULL),
      CONSTRAINT vendor_event_needs_vendor
        CHECK (event_type <> 'sent_to_vendor' OR vendor_id IS NOT NULL),
      CONSTRAINT return_needs_collector
        CHECK (event_type <> 'returned_to_unit' OR counterparty_name IS NOT NULL),
      CONSTRAINT intake_needs_depositor
        CHECK (event_type <> 'received_for_repair' OR counterparty_name IS NOT NULL)
    )""",
    "CREATE INDEX idx_events_device_time ON device_events(device_id, occurred_at)",
    "CREATE INDEX idx_events_complaint ON device_events(complaint_id)",
    "CREATE INDEX idx_events_unit_time ON device_events(unit_id, occurred_at)",
    """CREATE TABLE acknowledgements (
      id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      event_id BIGINT NOT NULL UNIQUE REFERENCES device_events(id),
      acknowledged_by UUID NOT NULL REFERENCES users(id),
      status ack_status NOT NULL,
      comment TEXT,
      acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT dispute_needs_comment CHECK (status <> 'disputed' OR comment IS NOT NULL)
    )""",
    """CREATE TABLE costs (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      device_id UUID REFERENCES devices(id),
      complaint_id UUID REFERENCES complaints(id),
      event_id BIGINT REFERENCES device_events(id),
      unit_id UUID REFERENCES units(id),
      kind cost_kind NOT NULL,
      description TEXT NOT NULL,
      amount NUMERIC(14,2) NOT NULL CONSTRAINT costs_amount_check CHECK (amount >= 0),
      currency CHAR(3) NOT NULL DEFAULT 'NGN',
      vendor_id UUID REFERENCES vendors(id),
      invoice_ref TEXT,
      incurred_on DATE NOT NULL,
      recorded_by UUID NOT NULL REFERENCES users(id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      voided_at TIMESTAMPTZ,
      voided_by UUID REFERENCES users(id),
      void_reason TEXT,
      CONSTRAINT void_fields_together CHECK (
        (voided_at IS NULL AND voided_by IS NULL AND void_reason IS NULL) OR
        (voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL)
      )
    )""",
    "CREATE INDEX idx_costs_period ON costs(incurred_on) WHERE voided_at IS NULL",
    "CREATE INDEX idx_costs_unit ON costs(unit_id)",
    "CREATE INDEX idx_costs_device ON costs(device_id)",
    # ===== IMMUTABILITY GUARDS =====
    """CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION USING
        ERRCODE = 'restrict_violation',
        MESSAGE = TG_OP || ' on ' || TG_TABLE_NAME || ' is not allowed (append-only table)';
    END; $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER device_events_immutable BEFORE UPDATE OR DELETE ON device_events
      FOR EACH ROW EXECUTE FUNCTION forbid_mutation()""",
    """CREATE TRIGGER acknowledgements_immutable BEFORE UPDATE OR DELETE ON acknowledgements
      FOR EACH ROW EXECUTE FUNCTION forbid_mutation()""",
    """CREATE TRIGGER complaint_comments_immutable BEFORE UPDATE OR DELETE ON complaint_comments
      FOR EACH ROW EXECUTE FUNCTION forbid_mutation()""",
    # Row triggers do not fire on TRUNCATE, so guard it separately.
    """CREATE TRIGGER device_events_no_truncate BEFORE TRUNCATE ON device_events
      FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()""",
    """CREATE TRIGGER acknowledgements_no_truncate BEFORE TRUNCATE ON acknowledgements
      FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()""",
    """CREATE TRIGGER complaint_comments_no_truncate BEFORE TRUNCATE ON complaint_comments
      FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation()""",
    # costs: only the one-time void fields may change
    """CREATE OR REPLACE FUNCTION costs_guard() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
          MESSAGE = 'costs rows cannot be deleted; void them instead';
      END IF;
      IF OLD.voided_at IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
          MESSAGE = 'a voided cost cannot be changed';
      END IF;
      IF (to_jsonb(NEW) - 'voided_at' - 'voided_by' - 'void_reason')
         IS DISTINCT FROM
         (to_jsonb(OLD) - 'voided_at' - 'voided_by' - 'void_reason') THEN
        RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
          MESSAGE = 'cost fields cannot be edited; void and re-enter instead';
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER costs_guard_trg BEFORE UPDATE OR DELETE ON costs
      FOR EACH ROW EXECUTE FUNCTION costs_guard()""",
    """CREATE FUNCTION costs_forbid_truncate() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION USING ERRCODE = 'restrict_violation',
        MESSAGE = 'costs cannot be truncated; void rows instead';
    END; $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER costs_no_truncate BEFORE TRUNCATE ON costs
      FOR EACH STATEMENT EXECUTE FUNCTION costs_forbid_truncate()""",
]

DOWN = [
    "DROP TABLE costs",
    "DROP TABLE acknowledgements",
    "DROP TABLE device_events",
    "DROP TABLE complaint_comments",
    "DROP TABLE complaints",
    "DROP TABLE devices",
    "DROP TABLE vendors",
    "DROP TABLE users",
    "DROP TABLE units",
    "DROP FUNCTION costs_forbid_truncate()",
    "DROP FUNCTION costs_guard()",
    "DROP FUNCTION forbid_mutation()",
    "DROP SEQUENCE ticket_no_seq",
    "DROP SEQUENCE asset_tag_seq",
    "DROP TYPE ack_status",
    "DROP TYPE cost_kind",
    "DROP TYPE priority_level",
    "DROP TYPE complaint_category",
    "DROP TYPE complaint_status",
    "DROP TYPE event_type",
    "DROP TYPE device_status",
    "DROP TYPE user_role",
]


def upgrade() -> None:
    bind = op.get_bind()
    for statement in UP:
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    bind = op.get_bind()
    for statement in DOWN:
        bind.exec_driver_sql(statement)
