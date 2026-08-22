from __future__ import annotations

from abc import ABC, abstractmethod


class PaymentProvider(ABC):
    @abstractmethod
    async def create_payment(
        self, *, title: str, description: str, payload: str, amount: int, currency: str = "RUB"
    ) -> str:
        ...

    @abstractmethod
    async def check_payment(self, payment_id: str) -> bool:
        ...


class MockPaymentProvider(PaymentProvider):
    async def create_payment(
        self, *, title: str, description: str, payload: str, amount: int, currency: str = "RUB"
    ) -> str:
        return "mock_payment_123"

    async def check_payment(self, payment_id: str) -> bool:
        return True


class YooKassaPaymentProvider(PaymentProvider):
    def __init__(self, shop_id: str, secret_key: str) -> None:
        self._shop_id = shop_id
        self._secret_key = secret_key

    async def create_payment(
        self, *, title: str, description: str, payload: str, amount: int, currency: str = "RUB"
    ) -> str:
        from yookassa import Payment  # type: ignore[import-untyped]

        payment = Payment.create(
            {
                "amount": {"value": f"{amount / 100:.2f}", "currency": currency},
                "confirmation": {"type": "redirect", "return_url": "https://t.me/"},
                "capture": True,
                "description": description,
                "metadata": {"payload": payload},
            },
            idempotency_key=payload,
        )
        url: str = payment.confirmation.confirmation_url
        return url

    async def check_payment(self, payment_id: str) -> bool:
        from yookassa import Payment

        payment = Payment.find_one(payment_id)
        result: bool = payment.status == "succeeded"
        return result
