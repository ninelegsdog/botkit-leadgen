"""Add claimed_by and claimed_at columns to crm_outbox for multi-worker support

Revision ID: 0003_add_claimed_by
Revises: 0002_add_dlq
Create Date: 2026-11-09 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_claimed_by"
down_revision: str | None = "0002_add_dlq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add claimed_by and claimed_at columns for stale claim reclamation.

    Uses try/except so the migration is idempotent: fresh installs already have
    the columns from 0001_initial_schema, existing installs add them here.
    """
    for column in ("claimed_by", "claimed_at"):
        try:
            op.execute(
                text(f"ALTER TABLE crm_outbox ADD COLUMN {column} TEXT")
            )
        except Exception:
            # Column already exists (fresh install via 0001) — skip.
            pass
    try:
        op.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_crm_outbox_claimed "
                "ON crm_outbox(claimed_by, claimed_at)"
            )
        )
    except Exception:
        pass


def downgrade() -> None:
    """Remove claimed_by and claimed_at columns."""
    try:
        op.execute(text("DROP INDEX IF EXISTS idx_crm_outbox_claimed"))
    except Exception:
        pass
    # SQLite doesn't support DROP COLUMN in older versions — leave columns.
