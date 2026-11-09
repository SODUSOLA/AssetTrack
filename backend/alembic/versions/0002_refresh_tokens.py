"""refresh tokens for rotation, reuse detection and logout

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23

Mutable operational table (not part of the audit trail): rows are revoked, never edited otherwise.
Only the SHA-256 hash of each token is stored.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql(
        """CREATE TABLE refresh_tokens (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id UUID NOT NULL REFERENCES users(id),
          token_hash TEXT NOT NULL UNIQUE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          expires_at TIMESTAMPTZ NOT NULL,
          revoked_at TIMESTAMPTZ
        )"""
    )
    bind.exec_driver_sql("CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id)")


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE refresh_tokens")
