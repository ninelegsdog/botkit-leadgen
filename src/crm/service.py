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
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import Database
from src.core.metrics import CRM_DLQ_DEPTH
from src.core.migrations import CRM_PAYLOAD_SCHEMA_VERSION

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
            "schema_version": CRM_PAYLOAD_SCHEMA_VERSION,
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
    correlation_id = lead.get("correlation_id") or str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT OR IGNORE INTO crm_outbox (lead_id, provider, payload, "
            "payload_version, correlation_id) "
            "VALUES (:lid, :provider, :payload, :version, :corr_id)"
        ),
        {
            "lid": lead_id,
            "provider": provider,
            "payload": build_payload({**lead, "id": lead_id, "correlation_id": correlation_id}),
            "version": CRM_PAYLOAD_SCHEMA_VERSION,
            "corr_id": correlation_id,
        },
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
    retry_after: int | None = None,
) -> None:
    if attempts >= max_attempts:
        await mark_failed(db, row_id, error)
        return
    # If the CRM returned Retry-After, honour it instead of computed backoff.
    if retry_after is not None and retry_after > 0:
        delay = float(retry_after)
    else:
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



async def record_idempotency_key(
    db: Database,
    *,
    key: str,
    provider: str,
    lead_id: int,
    response_status: str = "pending",
    response_body: str | None = None,
    external_id: str | None = None,
) -> None:
    """Record or upsert an idempotency key before/after CRM delivery."""
    async with db.transaction() as session:
        await session.execute(
            text(
                """
                INSERT INTO crm_idempotency_keys
                    (key, provider, lead_id, response_status, response_body,
                     external_id, created_at, delivered_at)
                VALUES (:key, :provider, :lead_id, :status, :body, :ext,
                        datetime('now'), NULL)
                ON CONFLICT(key) DO UPDATE SET
                    response_status = excluded.response_status,
                    response_body = excluded.response_body,
                    external_id = excluded.external_id,
                    delivered_at = CASE WHEN excluded.response_status = 'delivered'
                                        THEN datetime('now')
                                        ELSE crm_idempotency_keys.delivered_at END
                """
            ),
            {
                "key": key,
                "provider": provider,
                "lead_id": lead_id,
                "status": response_status,
                "body": response_body,
                "ext": external_id,
            },
        )


async def check_idempotency_key(
    db: Database, *, key: str
) -> dict[str, str] | None:
    """Return cached response if the key was already delivered, else None."""
    async with db.session() as session:
        result = await session.execute(
            text(
                """
                SELECT response_status, response_body, external_id, delivered_at
                FROM crm_idempotency_keys WHERE key = :key
                """
            ),
            {"key": key},
        )
        row = result.mappings().fetchone()
        if row is None:
            return None
        if row["response_status"] == "delivered":
            return {
                "status": row["response_status"],
                "body": row["response_body"] or "",
                "external_id": row["external_id"] or "",
            }
        return None


async def update_idempotency_key_delivered(
    db: Database,
    *,
    key: str,
    external_id: str,
    response_body: str,
) -> None:
    """Mark an idempotency key as delivered after successful CRM push."""
    async with db.transaction() as session:
        await session.execute(
            text(
                """
                UPDATE crm_idempotency_keys
                SET response_status = 'delivered',
                    external_id = :ext,
                    response_body = :body,
                    delivered_at = datetime('now')
                WHERE key = :key
                """
            ),
            {"key": key, "ext": external_id, "body": response_body[:5000]},
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
        # Update DLQ depth metric for the provider.
        try:
            result = await session.execute(
                text(
                    "SELECT provider, COUNT(*) as cnt FROM crm_dlq "
                    "GROUP BY provider"
                )
            )
            for provider_row in result.mappings().all():
                CRM_DLQ_DEPTH.labels(provider=provider_row["provider"]).set(
                    int(provider_row["cnt"])
                )
        except Exception:  # noqa: BLE001 - metric update must not break delivery
            pass


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
        # Refresh DLQ depth metric after requeue.
        try:
            result = await session.execute(
                text(
                    "SELECT provider, COUNT(*) as cnt FROM crm_dlq "
                    "GROUP BY provider"
                )
            )
            for provider_row in result.mappings().all():
                CRM_DLQ_DEPTH.labels(provider=provider_row["provider"]).set(
                    int(provider_row["cnt"])
                )
        except Exception:  # noqa: BLE001 - metric update must not break retry
            pass
        return True


async def save_amocrm_access_token(db: Database, token: str) -> None:
    """Persist refreshed AmoCRM access token so it survives bot restarts."""
    async with db.transaction() as session:
        await session.execute(
            text(
                """
                INSERT INTO settings (key, value) VALUES ('crm_amocrm_access_token', :token)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            ),
            {"token": token},
        )


async def load_amocrm_access_token(db: Database) -> str | None:
    """Load persisted AmoCRM access token, if any."""
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT value FROM settings WHERE key = 'crm_amocrm_access_token'"
            )
        )
        row = result.mappings().fetchone()
        return str(row["value"]) if row else None
