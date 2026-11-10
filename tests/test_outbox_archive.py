"""Test for outbox archive script: deletes only old sent/failed rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text as sql_text

from scripts.archive_outbox import archive_outbox
from src.core.config import Config
from src.core.database import Database
from src.core.migrations import migrate
from src.crm import service as crm_service


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


@pytest.mark.asyncio
async def test_dlq_list_and_retry(tmp_path) -> None:
    """DLQ rows can be listed and requeued back to crm_outbox."""
    db_path = str(tmp_path / "leads.db")
    config = Config(db_path=db_path)
    db = Database(config)
    await migrate(db)

    # Insert a row directly into crm_dlq
    async with db.transaction() as session:
        from sqlalchemy import text as sql_text
        await session.execute(
            sql_text(
                "INSERT INTO crm_dlq (outbox_id, lead_id, provider, payload, "
                "attempts, last_error, failed_at) "
                "VALUES (:oid, :lid, :provider, :payload, :attempts, :err, "
                "datetime('now'))"
            ),
            {
                "oid": 42,
                "lid": 7,
                "provider": "generic",
                "payload": "{}",
                "attempts": 6,
                "err": "permanent failure",
            },
        )

    # List DLQ
    rows = await crm_service.dlq_list(db)
    assert len(rows) == 1
    assert rows[0]["lead_id"] == 7
    assert rows[0]["provider"] == "generic"
    assert rows[0]["attempts"] == 6

    # Retry from DLQ
    ok = await crm_service.dlq_retry(db, rows[0]["id"])
    assert ok is True

    # Row should now be in crm_outbox as pending
    async with db.session() as session:
        from sqlalchemy import text as sql_text
        result = await session.execute(
            sql_text("SELECT status, attempts FROM crm_outbox WHERE lead_id = 7")
        )
        row = result.mappings().fetchone()
        assert row is not None
        assert row["status"] == "pending"
        assert row["attempts"] == 0

    # DLQ should be empty now
    rows_after = await crm_service.dlq_list(db)
    assert len(rows_after) == 0

    # Retry non-existent id
    ok2 = await crm_service.dlq_retry(db, 999)
    assert ok2 is False

    await db.close()


@pytest.mark.asyncio
async def test_enqueue_lead_off_provider_is_noop(tmp_path) -> None:
    """enqueue_lead with provider='off' must not insert into crm_outbox."""
    db_path = str(tmp_path / "leads.db")
    config = Config(db_path=db_path)
    db = Database(config)
    await migrate(db)

    await crm_service.enqueue_lead(
        None,  # type: ignore[arg-type]
        lead_id=1,
        lead={"client_name": "X"},
        provider="off",
    )

    async with db.session() as session:
        from sqlalchemy import text as sql_text
        result = await session.execute(
            sql_text("SELECT COUNT(*) FROM crm_outbox WHERE lead_id = 1")
        )
        assert result.scalar_one() == 0

    await db.close()
