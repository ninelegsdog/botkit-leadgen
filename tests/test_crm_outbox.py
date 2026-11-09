"""Transactional outbox: enqueue, idempotency and worker delivery."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text

from src.core.database import Database
from src.crm import service as crm_service
from src.crm.adapters import CrmSettings
from src.crm.worker import process_batch
from src.leadgen import service as lead_service


@pytest.mark.asyncio
async def test_create_lead_enqueues_when_provider(db: Database) -> None:
    lead_id = await lead_service.create_lead(
        db, client_user_id=1, crm_provider="generic"
    )
    async with db.session() as session:
        row = await session.execute(
            text("SELECT provider, status FROM crm_outbox WHERE lead_id = :id"),
            {"id": lead_id},
        )
        mapping = row.mappings().fetchone()
    assert mapping is not None
    assert mapping["provider"] == "generic"
    assert mapping["status"] == "pending"


@pytest.mark.asyncio
async def test_create_lead_no_enqueue_when_off(db: Database) -> None:
    lead_id = await lead_service.create_lead(db, client_user_id=1)
    async with db.session() as session:
        row = await session.execute(
            text("SELECT COUNT(*) FROM crm_outbox WHERE lead_id = :id"),
            {"id": lead_id},
        )
        assert row.scalar_one() == 0


@pytest.mark.asyncio
async def test_enqueue_is_idempotent(db: Database) -> None:
    async with db.transaction() as session:
        await crm_service.enqueue_lead(
            session, lead_id=42, lead={"client_name": "A"}, provider="generic"
        )
        await crm_service.enqueue_lead(
            session, lead_id=42, lead={"client_name": "A"}, provider="generic"
        )
    async with db.session() as session:
        row = await session.execute(
            text("SELECT COUNT(*) FROM crm_outbox WHERE lead_id = 42")
        )
        assert row.scalar_one() == 1


@pytest.mark.asyncio
async def test_worker_delivers_pending(db: Database) -> None:
    async with db.transaction() as session:
        await crm_service.enqueue_lead(
            session,
            lead_id=5,
            lead={"client_name": "Alice", "client_phone": "+7", "field_values": "{}"},
            provider="generic",
        )
    settings = CrmSettings(provider="generic", webhook_url="https://example.com/hook")
    transport = httpx.MockTransport(lambda request: httpx.Response(202))
    async with httpx.AsyncClient(transport=transport) as client:
        delivered = await process_batch(db, settings, max_attempts=3, client=client)
    assert delivered == 1
    async with db.session() as session:
        row = await session.execute(
            text("SELECT status, external_id FROM crm_outbox WHERE lead_id = 5")
        )
        mapping = row.mappings().fetchone()
    assert mapping is not None
    assert mapping["status"] == "sent"


@pytest.mark.asyncio
async def test_worker_retries_on_server_error(db: Database) -> None:
    async with db.transaction() as session:
        await crm_service.enqueue_lead(
            session,
            lead_id=6,
            lead={"client_name": "Bob", "field_values": "{}"},
            provider="generic",
        )
    settings = CrmSettings(provider="generic", webhook_url="https://example.com/hook")
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as client:
        delivered = await process_batch(db, settings, max_attempts=3, client=client)
    assert delivered == 0
    async with db.session() as session:
        row = await session.execute(
            text("SELECT status, attempts, last_error FROM crm_outbox WHERE lead_id = 6")
        )
        mapping = row.mappings().fetchone()
    assert mapping is not None
    assert mapping["status"] == "pending"
    assert mapping["attempts"] == 1
    assert mapping["last_error"] is not None


@pytest.mark.asyncio
async def test_worker_marks_failed_after_max_attempts(db: Database) -> None:
    async with db.transaction() as session:
        await crm_service.enqueue_lead(
            session,
            lead_id=7,
            lead={"client_name": "Carol", "field_values": "{}"},
            provider="generic",
        )
    settings = CrmSettings(provider="generic", webhook_url="https://example.com/hook")
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as client:
        await process_batch(db, settings, max_attempts=1, client=client)
    async with db.session() as session:
        row = await session.execute(
            text("SELECT status, attempts FROM crm_outbox WHERE lead_id = 7")
        )
        mapping = row.mappings().fetchone()
    assert mapping is not None
    assert mapping["status"] == "failed"
    assert mapping["attempts"] == 1


@pytest.mark.asyncio
async def test_mark_retry_honours_custom_backoff(db: Database) -> None:
    async with db.transaction() as session:
        await crm_service.enqueue_lead(
            session, lead_id=99, lead={"client_name": "Z", "field_values": "{}"}, provider="generic"
        )
    # claim once so attempts=1
    rows = await crm_service.claim_batch(db, limit=1)
    assert rows and rows[0]["lead_id"] == 99
    await crm_service.mark_retry(db, int(rows[0]["id"]), 1, "boom", 6, backoff_seconds=(9999,))
    async with db.session() as session:
        row = await session.execute(
            text("SELECT status, next_attempt_at FROM crm_outbox WHERE lead_id = 99")
        )
        mapping = row.mappings().fetchone()
    assert mapping is not None
    assert mapping["status"] == "pending"
    from datetime import UTC, datetime, timedelta

    next_at = datetime.strptime(str(mapping["next_attempt_at"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    # Jitter of +/-25% on base delay 9999s => delay in [7499, 12499] seconds.
    assert next_at >= datetime.now(UTC) + timedelta(seconds=7400)
    assert next_at <= datetime.now(UTC) + timedelta(seconds=12600)
