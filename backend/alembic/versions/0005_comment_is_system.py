"""flag system-written complaint comments

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-29

`is_system` marks comments the application wrote to explain a state change (assignment, status,
priority), so clients can tell them from comments people typed. Adding a column with a constant
default is a catalog-only change in PostgreSQL: no rows are rewritten and the append-only trigger
does not fire. The API never lets a client set it.
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        "ALTER TABLE complaint_comments ADD COLUMN is_system BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("ALTER TABLE complaint_comments DROP COLUMN is_system")
