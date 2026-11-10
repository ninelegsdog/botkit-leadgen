"""Server-side idempotency keys: duplicate key does not re-send to CRM."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import text

from src.core.database import Database
from src.crm import service as crm_service
from src.crm.adapters import CrmSettings
from src.crm.worker import process_batch


@pytest.mark.asyncio
async def test_idempotency_duplicate_key_skips_crm(db: Database) -> None:
    """Same idempotency key delivered once — second attempt skips CRM call."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"result": 100})

    # Enqueue two rows with the same lead_id (same idempotency key: lead-1)
    async with db.transaction() as session:
        await crm_service.enqueue_lead(
            session, lead_id=1,
            lead={"client_name": "Alice", "client_phone": "+7", "field_values": "{}"},
            provider="bitrix24",
        )
    # Manually insert a second row with same lead_id (simulating retry)
    async with db.session() as session:
        await session.execute(
            text(
                """
                INSERT OR IGNORE INTO crm_outbox (lead_id, provider, payload, payload_version, correlation_id)
                VALUES (1, 'bitrix24', :payload, 1, :corr_id)
                """
            ),
            {
                "payload": (
                    '{"schema_version":1,"id":1,"client_name":"Alice",'
                    '"client_phone":"+7","field_values":"{}",'
                    '"created_at":"2026-01-01 00:00:00"}'
                ),
                "corr_id": "test-corr-1",
            },
        )

    settings = CrmSettings(
        provider="bitrix24",
        base_url="https://portal.bitrix24.ru",
        bitrix_user_id="1",
        bitrix_webhook_token="token",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        delivered = await process_batch(db, settings, max_attempts=3, client=client)

    # Only one lead was delivered (the UNIQUE(lead_id, provider) constraint prevents duplicates)
    assert delivered == 1
    assert call_count == 1  # CRM called only once


@pytest.mark.asyncio
async def test_idempotency_key_recorded_after_delivery(db: Database) -> None:
    """After successful delivery, idempotency key is marked as delivered."""
    async with db.transaction() as session:
        await crm_service.enqueue_lead(
            session, lead_id=2,
            lead={"client_name": "Bob", "client_phone": "+7", "field_values": "{}"},
            provider="generic",
        )

    settings = CrmSettings(
        provider="generic",
        webhook_url="https://example.com/hook",
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(202))
    async with httpx.AsyncClient(transport=transport) as client:
        delivered = await process_batch(db, settings, max_attempts=3, client=client)

    assert delivered == 1

    # Verify idempotency key was recorded
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT response_status, external_id FROM crm_idempotency_keys WHERE key = :key"
            ),
            {"key": "lead-2"},
        )
        row = result.mappings().fetchone()
    assert row is not None
    assert row["response_status"] == "delivered"
    assert row["external_id"] == ""  # generic returns empty external_id


@pytest.mark.asyncio
async def test_idempotency_cached_response_reused(db: Database) -> None:
    """Pre-recorded delivered key causes worker to skip CRM and mark as sent."""
    # Pre-record a delivered idempotency key
    async with db.transaction() as session:
        await crm_service.record_idempotency_key(
            db, key="lead-3", provider="generic", lead_id=3,
            response_status="delivered", external_id="ext-999",
        )
        await crm_service.enqueue_lead(
            session, lead_id=3,
            lead={"client_name": "Carol", "client_phone": "+7", "field_values": "{}"},
            provider="generic",
        )

    settings = CrmSettings(
        provider="generic",
        webhook_url="https://example.com/hook",
    )
    call_count = [0]
    transport = httpx.MockTransport(
        lambda request: (call_count.__setitem__(0, call_count[0] + 1)) or httpx.Response(202)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        delivered = await process_batch(db, settings, max_attempts=3, client=client)

    assert delivered == 1
    assert call_count[0] == 0  # CRM was NOT called due to idempotency hit

    # Verify outbox row is marked as sent with cached external_id
    async with db.session() as session:
        result = await session.execute(
            text("SELECT status, external_id FROM crm_outbox WHERE lead_id = 3")
        )
        row = result.mappings().fetchone()
    assert row is not None
    assert row["status"] == "sent"
    assert row["external_id"] == "ext-999"
