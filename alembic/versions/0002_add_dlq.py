"""Add CRM dead letter queue table

Revision ID: 0002_add_dlq
Revises: 0001_initial_schema
Create Date: 2026-11-09 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_dlq"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create crm_dlq table for permanently failed outbox rows."""
    schema = """
    CREATE TABLE IF NOT EXISTS crm_dlq (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        outbox_id INTEGER NOT NULL,
        lead_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        payload TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        failed_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (outbox_id)
    );

    CREATE INDEX IF NOT EXISTS idx_crm_dlq_provider ON crm_dlq(provider);
    CREATE INDEX IF NOT EXISTS idx_crm_dlq_failed_at ON crm_dlq(failed_at);
    """

    for statement in schema.strip().split(";"):
        stmt = statement.strip()
        if stmt:
            op.execute(text(stmt))


def downgrade() -> None:
    """Drop crm_dlq table."""
    op.execute(text("DROP INDEX IF EXISTS idx_crm_dlq_failed_at"))
    op.execute(text("DROP INDEX IF EXISTS idx_crm_dlq_provider"))
    op.execute(text("DROP TABLE IF EXISTS crm_dlq"))
