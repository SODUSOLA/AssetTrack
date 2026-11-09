"""remove pricing: drop costs, cost_kind and their guards

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28

Decision of the admin (SPEC v1.1): the system records no monetary values anywhere. No endpoint
ever wrote to `costs`, so the table is empty everywhere it has been created.

`downgrade()` recreates the objects exactly as `0001` defined them.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UP = [
    "DROP TABLE costs",  # its indexes and triggers go with it
    "DROP FUNCTION costs_forbid_truncate()",
    "DROP FUNCTION costs_guard()",
    "DROP TYPE cost_kind",
]

DOWN = [
    "CREATE TYPE cost_kind AS ENUM ('purchase', 'repair', 'parts', 'other')",
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


def upgrade() -> None:
    bind = op.get_bind()
    for statement in UP:
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    bind = op.get_bind()
    for statement in DOWN:
        bind.exec_driver_sql(statement)
