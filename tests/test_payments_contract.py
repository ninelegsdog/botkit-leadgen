"""Contract tests for payments (YooKassa/Stars) — respx-mock."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

try:
    import yookassa  # noqa: F401

    HAS_YOOKASSA = True
except ImportError:
    HAS_YOOKASSA = False

from aiogram.types import Message

from src.core.payments import MockPaymentProvider

try:
    from src.core.payments import YooKassaPaymentProvider
except ImportError:
    YooKassaPaymentProvider = None  # type: ignore


@pytest.mark.asyncio
async def test_mock_provider_create_invoice() -> None:
    provider = MockPaymentProvider(prefix="https://t.me/mock/")
    link = await provider.create_invoice_link(
        title="Test", description="Desc", payload="pay_123", amount=100, currency="XTR"
    )
    assert link == "https://t.me/mock/pay_123"


@pytest.mark.asyncio
async def test_mock_provider_verify_payment_success() -> None:
    provider = MockPaymentProvider()
    msg = Message.model_validate({
        "message_id": 1,
        "date": 0,
        "chat": {"id": 1, "type": "private"},
        "successful_payment": {
            "currency": "XTR",
            "total_amount": 100,
            "invoice_payload": "pay_123",
            "telegram_payment_charge_id": "ch_123",
            "provider_payment_charge_id": "prov_123",
        },
    })
    assert await provider.verify_payment(msg) is True


@pytest.mark.asyncio
async def test_mock_provider_verify_payment_fail() -> None:
    provider = MockPaymentProvider()
    msg = Message.model_validate({
        "message_id": 1,
        "date": 0,
        "chat": {"id": 1, "type": "private"},
    })
    assert await provider.verify_payment(msg) is False


@pytest.mark.skipif(not HAS_YOOKASSA, reason="yookassa not installed")
@pytest.mark.asyncio
@patch("yookassa.Payment.create")
async def test_yookassa_create_invoice_contract(mock_create: MagicMock) -> None:
    from src.core.payments import YooKassaPaymentProvider

    mock_payment = MagicMock()
    mock_payment.confirmation.confirmation_url = "https://yookassa.ru/confirm/pay_123"
    mock_create.return_value = mock_payment

    provider = YooKassaPaymentProvider(shop_id="123", secret_key="test_key")
    link = await provider.create_invoice_link(
        title="Test", description="Desc", payload="pay_123", amount=100, currency="RUB"
    )
    mock_create.assert_called_once()
    call_args = mock_create.call_args[0][0]
    assert call_args["amount"]["value"] == "100.00"
    assert call_args["amount"]["currency"] == "RUB"
    assert call_args["metadata"]["payload"] == "pay_123"
    assert link == "https://yookassa.ru/confirm/pay_123"


@pytest.mark.skipif(not HAS_YOOKASSA, reason="yookassa not installed")
@pytest.mark.asyncio
async def test_yookassa_verify_payment() -> None:
    from src.core.payments import YooKassaPaymentProvider

    provider = YooKassaPaymentProvider(shop_id="123", secret_key="test_key")
    msg = Message.model_validate({
        "message_id": 1,
        "date": 0,
        "chat": {"id": 1, "type": "private"},
        "successful_payment": {
            "currency": "RUB",
            "total_amount": 10000,
            "invoice_payload": "pay_123",
            "telegram_payment_charge_id": "ch_123",
            "provider_payment_charge_id": "prov_123",
        },
    })
    assert await provider.verify_payment(msg) is True


@pytest.mark.skipif(not HAS_YOOKASSA, reason="yookassa not installed")
def test_create_payment_provider_factory() -> None:
    from src.core.payments import create_payment_provider

    mock = create_payment_provider("mock", prefix="https://t.me/mock/")
    assert isinstance(mock, MockPaymentProvider)

    yk = create_payment_provider("yookassa", shop_id="123", secret_key="key")
    assert isinstance(yk, YooKassaPaymentProvider)
