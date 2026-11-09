"""serial numbers are unique regardless of letter case

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28

The plain UNIQUE constraint on devices.serial_number stays (it is case-sensitive); this index
additionally rejects "sn-1" when "SN-1" exists. NULL serials never collide.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        "CREATE UNIQUE INDEX uq_devices_serial_lower ON devices (lower(serial_number))"
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP INDEX uq_devices_serial_lower")
