"""Test for outbox archive script: deletes only old sent/failed rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text as sql_text

from scripts.archive_outbox import archive_outbox
from src.core.config import Config
from src.core.database import Database
from src.core.migrations import migrate


async def _insert_row(db: Database, status: str, days_ago: int, lead_id: int) -> int:
    created = (datetime.now(UTC) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    async with db.transaction() as session:
        result = await session.execute(
            sql_text(
                "INSERT INTO crm_outbox (lead_id, provider, payload, status, created_at) "
                "VALUES (:lid, :provider, :payload, :status, :created)"
            ),
            {
                "lid": lead_id,
                "provider": "generic",
                "payload": "{}",
                "status": status,
                "created": created,
            },
        )
        return int(result.lastrowid or 0)


async def _get_status(db: Database, lead_id: int) -> str | None:
    async with db.session() as session:
        result = await session.execute(
            sql_text("SELECT status FROM crm_outbox WHERE lead_id = :lid"),
            {"lid": lead_id},
        )
        row = result.mappings().fetchone()
        return row["status"] if row else None


@pytest.mark.asyncio
async def test_archive_deletes_old_sent_and_failed(tmp_path) -> None:
    """Rows with status sent/failed older than archive_days are deleted."""
    db_path = str(tmp_path / "leads.db")
    config = Config(db_path=db_path)
    db = Database(config)
    await migrate(db)

    # old sent (31d), old failed (31d), fresh sent (1d), old pending (31d), old sending (31d)
    await _insert_row(db, "sent", 31, 1)
    await _insert_row(db, "failed", 31, 2)
    await _insert_row(db, "sent", 1, 3)
    await _insert_row(db, "pending", 31, 4)
    await _insert_row(db, "sending", 31, 5)

    count = await archive_outbox(db, archive_days=30, dry_run=False)
    assert count == 2  # only the 2 old processed rows

    assert await _get_status(db, 1) is None  # old sent deleted
    assert await _get_status(db, 2) is None  # old failed deleted
    assert await _get_status(db, 3) == "sent"  # fresh sent kept
    assert await _get_status(db, 4) == "pending"  # pending kept regardless of age
    assert await _get_status(db, 5) == "sending"  # sending kept regardless of age

    await db.close()


@pytest.mark.asyncio
async def test_archive_dry_run_deletes_nothing(tmp_path) -> None:
    """Dry-run reports count but does not delete."""
    db_path = str(tmp_path / "leads.db")
    config = Config(db_path=db_path)
    db = Database(config)
    await migrate(db)

    await _insert_row(db, "sent", 31, 1)
    await _insert_row(db, "failed", 31, 2)

    count = await archive_outbox(db, archive_days=30, dry_run=True)
    assert count == 2

    assert await _get_status(db, 1) == "sent"  # nothing deleted
    assert await _get_status(db, 2) == "failed"

    await db.close()
