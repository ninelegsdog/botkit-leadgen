from __future__ import annotations

from sqlalchemy import text

from src.core.database import Database

SCHEMA = """
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
    UNIQUE (lead_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_crm_outbox_due ON crm_outbox(status, next_attempt_at);
"""


async def migrate(db: Database) -> None:
    """Apply schema migrations via Alembic.

    Falls back to raw SQL execution if Alembic is not available or the
    alembic_version table does not exist yet (first-time deploy).
    """
    try:
        import asyncio

        from alembic.config import Config as AlembicConfig

        from alembic import command

        alembic_cfg = AlembicConfig("alembic.ini")
        alembic_cfg.set_main_option(
            "sqlalchemy.url", db.url
        )
        # Run alembic upgrade head in a thread since it's blocking.
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    except Exception:
        # Fallback: raw SQL execution for first-time deploys without alembic_version table.
        async with db.transaction() as conn:
            for statement in SCHEMA.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    await conn.execute(text(stmt))
