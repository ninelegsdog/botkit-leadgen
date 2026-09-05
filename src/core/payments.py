"""Payments shim — re-exports botkit_core.payments."""
from __future__ import annotations

from botkit_core.payments import MockPaymentProvider as MockPaymentProvider
from botkit_core.payments import PaymentProvider as PaymentProvider
from botkit_core.payments import YooKassaPaymentProvider as YooKassaPaymentProvider
from botkit_core.payments import create_payment_provider as create_payment_provider

__all__ = [
    "MockPaymentProvider",
    "PaymentProvider",
    "YooKassaPaymentProvider",
    "create_payment_provider",
]
