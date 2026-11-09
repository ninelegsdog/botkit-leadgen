"""Transactional outbox for CRM export.

The outbox row is written in the same transaction as the lead. Delivery is a
separate concern: the worker can fail, retry and lag without ever losing a lead.
Permanently failed rows are archived to the dead-letter queue (crm_dlq) so no
lead is ever silently dropped.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Database

logger = logging.getLogger(__name__)

# 1m, 5m, 30m, 2h, 6h, 24h. Attempts are incremented on claim, so the index is
# attempts - 1 and the last value is reused after that.
BACKOFF_SECONDS: tuple[int, ...] = (60, 300, 1800, 7200, 21600, 86400)

# Jitter applied to each backoff delay to avoid thundering herd on CRM recovery.
JITTER_RATIO = 0.25  # +/-25%


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def build_payload(lead: dict[str, Any]) -> str:
    return json.dumps(
        {
            "id": lead.get("id"),
            "client_name": lead.get("client_name"),
            "client_phone": lead.get("client_phone"),
            "field_values": lead.get("field_values") or "{}",
            "created_at": lead.get("created_at") or utc_now(),
        },
        ensure_ascii=False,
    )


async def enqueue_lead(
    session: AsyncSession,
    *,
    lead_id: int,
    lead: dict[str, Any],
    provider: str,
) -> None:
    """Queue a lead for export inside the caller's transaction."""
    if provider == "off":
        return
    await session.execute(
        text(
            "INSERT OR IGNORE INTO crm_outbox (lead_id, provider, payload) "
            "VALUES (:lid, :provider, :payload)"
        ),
        {"lid": lead_id, "provider": provider, "payload": build_payload({**lead, "id": lead_id})},
    )


async def enqueue_test(db: Database, provider: str) -> int:
    """Queue a synthetic lead for a connectivity check. Returns the outbox id."""
    payload = build_payload(
        {
            "id": 0,
            "client_name": "CRM test",
            "client_phone": "+70000000000",
            "field_values": json.dumps({"source": "admin-test"}, ensure_ascii=False),
        }
    )
    async with db.transaction() as session:
        await session.execute(
            text("DELETE FROM crm_outbox WHERE lead_id = 0 AND provider = :p"),
            {"p": provider},
        )
        result = await session.execute(
            text("INSERT INTO crm_outbox (lead_id, provider, payload) VALUES (0, :p, :payload)"),
            {"p": provider, "payload": payload},
        )
        return int(result.lastrowid or 0)  # type: ignore[attr-defined]


async def claim_batch(
    db: Database,
    limit: int = 20,
    worker_id: str | None = None,
    stale_after_seconds: int = 300,
) -> list[dict[str, Any]]:
    """Atomically move due rows to 'sending' and return them.

    RETURNING makes the claim a single statement, so two workers cannot send the
    same row twice. Rows claimed by another worker more than
    ``stale_after_seconds`` ago are reclaimed (stale claim recovery).
    """
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "UPDATE crm_outbox SET status = 'sending', attempts = attempts + 1, "
                "claimed_by = :worker_id, claimed_at = datetime('now') "
                "WHERE id IN ("
                "  SELECT id FROM crm_outbox "
                "  WHERE ("
                "    (status = 'pending' AND next_attempt_at <= datetime('now'))"
                "    OR (claimed_by IS NOT NULL AND claimed_at <= datetime('now', :stale_clause))"
                "  )"
                "  ORDER BY id LIMIT :limit"
                ") RETURNING id, lead_id, provider, payload, attempts, claimed_by"
            ),
            {
                "limit": limit,
                "worker_id": worker_id,
                "stale_clause": f"-{stale_after_seconds} seconds",
            },
        )
        return [dict(row) for row in result.mappings().all()]


async def release_claim(db: Database, row_id: int) -> None:  # pragma: no cover
    """Release a claim on an outbox row (set status back to pending, clear claimed_by)."""
    async with db.transaction() as session:
        await session.execute(
            text(
                "UPDATE crm_outbox SET status = 'pending', claimed_by = NULL, "
                "claimed_at = NULL WHERE id = :id"
            ),
            {"id": row_id},
        )


async def mark_sent(db: Database, row_id: int, external_id: str) -> None:
    async with db.transaction() as session:
        await session.execute(
            text(
                "UPDATE crm_outbox SET status = 'sent', external_id = :ext, "
                "last_error = NULL WHERE id = :id"
            ),
            {"id": row_id, "ext": external_id},
        )


async def mark_retry(
    db: Database,
    row_id: int,
    attempts: int,
    error: str,
    max_attempts: int,
    backoff_seconds: tuple[int, ...] = BACKOFF_SECONDS,
) -> None:
    if attempts >= max_attempts:
        await mark_failed(db, row_id, error)
        return
    base_delay = backoff_seconds[min(attempts - 1, len(backoff_seconds) - 1)]
    jitter = random.uniform(-JITTER_RATIO, JITTER_RATIO) * base_delay
    delay = max(0, base_delay + jitter)
    next_at = (datetime.now(UTC) + timedelta(seconds=delay)).strftime("%Y-%m-%d %H:%M:%S")
    async with db.transaction() as session:
        await session.execute(
            text(
                "UPDATE crm_outbox SET status = 'pending', last_error = :err, "
                "next_attempt_at = :next WHERE id = :id"
            ),
            {"id": row_id, "err": error[:1000], "next": next_at},
        )


async def mark_failed(db: Database, row_id: int, error: str) -> None:
    """Move a permanently failed outbox row to the dead-letter queue.

    The row is copied to crm_dlq and deleted from crm_outbox so it is never
    silently lost and can be inspected or retried manually.
    """
    async with db.transaction() as session:
        # Read the row before deleting it.
        result = await session.execute(
            text(
                "SELECT lead_id, provider, payload, attempts, last_error "
                "FROM crm_outbox WHERE id = :id"
            ),
            {"id": row_id},
        )
        row = result.mappings().fetchone()
        if row is None:
            return
        await session.execute(
            text(
                "INSERT INTO crm_dlq (outbox_id, lead_id, provider, payload, "
                "attempts, last_error, failed_at) "
                "VALUES (:oid, :lid, :provider, :payload, :attempts, :err, "
                "datetime('now'))"
            ),
            {
                "oid": row_id,
                "lid": row["lead_id"],
                "provider": row["provider"],
                "payload": row["payload"],
                "attempts": row["attempts"],
                "err": error[:1000],
            },
        )
        await session.execute(
            text("DELETE FROM crm_outbox WHERE id = :id"),
            {"id": row_id},
        )


async def pending_count(db: Database) -> int:
    async with db.session() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM crm_outbox WHERE status IN ('pending', 'sending')")
        )
        return int(result.scalar_one())


async def retry_failed(db: Database) -> int:
    """Return failed rows to the queue. Used by the CLI and after a fix."""
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "UPDATE crm_outbox SET status = 'pending', attempts = 0, "
                "next_attempt_at = datetime('now') WHERE status = 'failed'"
            )
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def dlq_list(db: Database, limit: int = 100) -> list[dict[str, Any]]:
    """List dead-letter queue rows, most recent first."""
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT id, outbox_id, lead_id, provider, payload, attempts, "
                "last_error, failed_at FROM crm_dlq "
                "ORDER BY failed_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
        return [dict(row) for row in result.mappings().all()]


async def dlq_retry(db: Database, dlq_id: int) -> bool:
    """Move a DLQ row back to crm_outbox with attempts reset to 0.

    Returns True if the row was found and requeued, False otherwise.
    """
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "SELECT lead_id, provider, payload FROM crm_dlq WHERE id = :id"
            ),
            {"id": dlq_id},
        )
        row = result.mappings().fetchone()
        if row is None:
            return False
        await session.execute(
            text(
                "INSERT INTO crm_outbox (lead_id, provider, payload, status, "
                "attempts, next_attempt_at) "
                "VALUES (:lid, :provider, :payload, 'pending', 0, datetime('now'))"
            ),
            {
                "lid": row["lead_id"],
                "provider": row["provider"],
                "payload": row["payload"],
            },
        )
        await session.execute(
            text("DELETE FROM crm_dlq WHERE id = :id"),
            {"id": dlq_id},
        )
        return True
