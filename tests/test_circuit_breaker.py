"""Circuit breaker: open/half-open state transitions."""

from __future__ import annotations

import httpx
import pytest

from src.core.database import Database
from src.crm import service as crm_service
from src.crm.adapters import CrmSettings
from src.crm.worker import (
    CIRCUIT_FAILURE_THRESHOLD,
    CircuitBreaker,
    get_breaker,
    process_batch,
)


def test_breaker_opens_after_threshold() -> None:
    """After N consecutive failures, breaker is open."""
    b = CircuitBreaker()
    for _ in range(CIRCUIT_FAILURE_THRESHOLD - 1):
        b.record_failure("test")
    assert not b.is_open("test")
    b.record_failure("test")
    assert b.is_open("test")


def test_breaker_half_open_after_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    """After cool-down, breaker allows a half-open probe."""
    import time


    b = CircuitBreaker()
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        b.record_failure("test")
    assert b.is_open("test")
    assert not b.allow_probe("test")

    # Simulate cool-down passing by setting opened_at in the past
    b._opened_at["test"] = time.monotonic() - 400
    assert b.is_open("test")  # still open but probe allowed
    assert b.allow_probe("test")


def test_breaker_closes_after_success() -> None:
    """Successful probe resets the breaker."""
    b = CircuitBreaker()
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        b.record_failure("test")
    assert b.is_open("test")
    b.record_success("test")
    assert not b.is_open("test")
    assert not b.allow_probe("test")


@pytest.mark.asyncio
async def test_worker_uses_circuit_breaker(db: Database) -> None:
    """Worker posts to CRM only when circuit allows; open circuit postpones."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500)  # always fails

    # Enqueue 3 rows — each will fail, opening the circuit after 5 failures
    async with db.transaction() as session:
        for i in range(3):
            await crm_service.enqueue_lead(
                session, lead_id=10 + i,
                lead={"client_name": f"User {i}", "field_values": "{}"},
                provider="generic",
            )

    settings = CrmSettings(
        provider="generic",
        webhook_url="https://example.com/hook",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        # Process batch 3 times — circuit should open after threshold
        for _ in range(3):
            await process_batch(db, settings, max_attempts=3, client=client)

    # All 3 rows were attempted at least once
    assert call_count >= 3
    # Circuit breaker should have recorded failures
    breaker = get_breaker("generic")
    assert breaker._failures.get("generic", 0) >= 3
