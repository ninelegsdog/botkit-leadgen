"""Initial CRM and lead schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-09 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables from the application schema."""
    schema = """
    CREATE TABLE IF NOT EXISTS lead_fields (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        label TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'text',
        field_order INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_user_id INTEGER NOT NULL,
        client_name TEXT,
        client_phone TEXT,
        field_values TEXT DEFAULT '{}',
        manager_user_id INTEGER,
        taken_at TEXT,
        closed_at TEXT,
        status TEXT NOT NULL DEFAULT 'new',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS lead_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS managers (
        user_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL UNIQUE,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        text TEXT,
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status, taken_at);
    CREATE INDEX IF NOT EXISTS idx_leads_client ON leads(client_user_id);
    CREATE INDEX IF NOT EXISTS idx_lead_events_lead ON lead_events(lead_id);

    CREATE TABLE IF NOT EXISTS crm_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_error TEXT,
        external_id TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        claimed_by TEXT,
        claimed_at TEXT,
        UNIQUE (lead_id, provider)
    );

    CREATE INDEX IF NOT EXISTS idx_crm_outbox_due ON crm_outbox(status, next_attempt_at);
    """

    for statement in schema.strip().split(";"):
        stmt = statement.strip()
        if stmt:
            op.execute(text(stmt))


def downgrade() -> None:
    """Drop all tables created in upgrade."""
    op.execute(text("DROP INDEX IF EXISTS idx_crm_outbox_due"))
    op.execute(text("DROP TABLE IF EXISTS crm_outbox"))
    op.execute(text("DROP INDEX IF EXISTS idx_lead_events_lead"))
    op.execute(text("DROP INDEX IF EXISTS idx_leads_client"))
    op.execute(text("DROP INDEX IF EXISTS idx_leads_status"))
    op.execute(text("DROP TABLE IF EXISTS feedback"))
    op.execute(text("DROP TABLE IF EXISTS settings"))
    op.execute(text("DROP TABLE IF EXISTS managers"))
    op.execute(text("DROP TABLE IF EXISTS lead_events"))
    op.execute(text("DROP TABLE IF EXISTS leads"))
    op.execute(text("DROP TABLE IF EXISTS lead_fields"))
