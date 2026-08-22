from __future__ import annotations

from typing import Any

import pytest

from src.core.payments import MockPaymentProvider, YooKassaPaymentProvider


async def test_mock_provider_roundtrip() -> None:
    p = MockPaymentProvider()
    url = await p.create_payment(
        title="t", description="d", payload="p1", amount=10000
    )
    assert url == "mock_payment_123"
    assert await p.check_payment(url) is True


class _FakeConfirmation:
    confirmation_url = "https://yoomoney.ru/checkout/pay?x=1"


class _FakePaymentCreated:
    confirmation = _FakeConfirmation()


class _FakePaymentFound:
    status = "succeeded"


def test_yookassa_create_payment_contract(monkeypatch: pytest.MonkeyPatch) -> None:

    calls: dict[str, Any] = {}

    def fake_create(body: dict[str, Any], idempotency_key: str | None = None) -> Any:
        calls["body"] = body
        calls["idem"] = idempotency_key
        return _FakePaymentCreated()

    import sys

    fake_yookassa = type(sys)("yookassa")
    fake_payment_mod = type(sys)("yookassa.Payment")
    fake_payment_mod.create = fake_create  # type: ignore[attr-defined]
    fake_yookassa.Payment = fake_payment_mod.Payment if hasattr(fake_payment_mod, "Payment") else fake_payment_mod  # noqa: E501
    monkeypatch.setitem(sys.modules, "yookassa", fake_yookassa)
    monkeypatch.setitem(sys.modules, "yookassa.Payment", fake_payment_mod)

    provider = YooKassaPaymentProvider(shop_id="shop", secret_key="sec")

    async def run() -> str:
        return await provider.create_payment(
            title="Consultation",
            description="60 min",
            payload="lead:42",
            amount=50000,
        )

    import asyncio

    url = asyncio.run(run())
    assert url.startswith("https://")
    assert calls["body"]["capture"] is True
    assert calls["body"]["amount"]["value"] == "500.00"
    assert calls["body"]["metadata"]["payload"] == "lead:42"
    assert calls["idem"] == "lead:42"


def test_yookassa_check_payment_contract() -> None:
    from unittest.mock import patch

    provider = YooKassaPaymentProvider(shop_id="shop", secret_key="sec")
    with (
        patch("yookassa.Payment.find_one", return_value=_FakePaymentFound()),
    ):
        import asyncio

        result = asyncio.run(provider.check_payment("pid"))
    assert result is True
