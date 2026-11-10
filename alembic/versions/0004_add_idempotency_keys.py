"""Server-side idempotency keys for CRM export (Bitrix24/AmoCRM).

Bitrix24 and AmoCRM do not support native idempotency keys, so we track
processed keys ourselves: a key is recorded before the request and the
response is stored after delivery. A repeated key short-circuits the send.

Revision ID: 0004_add_idempotency_keys
Revises: 0003_add_claimed_by
Create Date: 2026-11-10 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_add_idempotency_keys"
down_revision: str | None = "0003_add_claimed_by"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create crm_idempotency_keys table and add idempotency_key column to crm_outbox."""
    try:
        op.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS crm_idempotency_keys (
                    key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    lead_id INTEGER NOT NULL,
                    response_status TEXT NOT NULL DEFAULT 'pending',
                    response_body TEXT,
                    external_id TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    delivered_at TEXT
                )
                """
            )
        )
    except Exception:
        pass
    try:
        op.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_crm_idempotency_provider_lead "
                "ON crm_idempotency_keys(provider, lead_id)"
            )
        )
    except Exception:
        pass
    # Add idempotency_key column to crm_outbox for cross-reference.
    try:
        op.execute(
            text("ALTER TABLE crm_outbox ADD COLUMN idempotency_key TEXT")
        )
    except Exception:
        pass
    try:
        op.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_crm_outbox_idempotency_key "
                "ON crm_outbox(idempotency_key)"
            )
        )
    except Exception:
        pass


def downgrade() -> None:
    """Drop idempotency key tracking objects."""
    try:
        op.execute(text("DROP INDEX IF EXISTS idx_crm_outbox_idempotency_key"))
    except Exception:
        pass
    try:
        op.execute(text("DROP TABLE IF EXISTS crm_idempotency_keys"))
    except Exception:
        pass
