"""Add payload_version and correlation_id columns to crm_outbox.

Supports payload schema versioning and end-to-end correlation tracing.

Revision ID: 0005_add_payload_version
Revises: 0004_add_idempotency_keys
Create Date: 2026-11-10 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_add_payload_version"
down_revision: str | None = "0004_add_idempotency_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add payload_version and correlation_id columns to crm_outbox."""
    try:
        op.execute(
            text("ALTER TABLE crm_outbox ADD COLUMN payload_version INTEGER NOT NULL DEFAULT 1")
        )
    except Exception:
        # Column already exists (fresh install via 0001) — skip.
        pass
    try:
        op.execute(
            text("ALTER TABLE crm_outbox ADD COLUMN correlation_id TEXT")
        )
    except Exception:
        pass
    try:
        op.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_crm_outbox_correlation_id "
                "ON crm_outbox(correlation_id)"
            )
        )
    except Exception:
        pass


def downgrade() -> None:
    """Remove correlation_id index."""
    try:
        op.execute(text("DROP INDEX IF EXISTS idx_crm_outbox_correlation_id"))
    except Exception:
        pass
    # SQLite doesn't support DROP COLUMN in older versions — leave columns.
