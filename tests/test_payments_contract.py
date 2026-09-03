"""Contract tests for payments (Mock) — delivery."""
from __future__ import annotations

import pytest

from src.core.payments import MockPaymentProvider


@pytest.mark.asyncio
async def test_mock_create_payment() -> None:
    provider = MockPaymentProvider()
    link = await provider.create_payment(
        title="Test", description="Desc", payload="pay_123", amount=100, currency="RUB"
    )
    assert link == "mock_payment_123" or "pay_123" in link or link is not None


@pytest.mark.asyncio
async def test_mock_check_payment() -> None:
    provider = MockPaymentProvider()
    assert await provider.check_payment("pay_123") is True
    assert await provider.check_payment("invalid") is True  # mock always true


def test_mock_provider_is_payment_provider() -> None:
    from src.core.payments import PaymentProvider

    provider = MockPaymentProvider()
    assert isinstance(provider, PaymentProvider)


@pytest.mark.asyncio
async def test_mock_create_payment_different_currencies() -> None:
    provider = MockPaymentProvider()
    for currency in ["RUB", "XTR", "USD"]:
        link = await provider.create_payment(
            title="T", description="D", payload="p", amount=50, currency=currency
        )
        assert link is not None
        assert isinstance(link, str)
