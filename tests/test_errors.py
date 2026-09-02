from __future__ import annotations

import asyncio
from typing import Any

from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.types import CallbackQuery, Message, Update, User
from prometheus_client import generate_latest
from pytest import MonkeyPatch

from src.core.errors import RetryMiddleware, default_error_handler, register_error_handler
from src.core.metrics import UPDATES_TOTAL, create_metrics_app


async def test_retry_after_handled(monkeypatch: MonkeyPatch) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    exc = TelegramRetryAfter(method=Any, message="flood", retry_after=5)
    await default_error_handler(event=None, exception=exc)  # type: ignore[arg-type]
    assert 5.0 in slept


async def test_network_error_handled() -> None:
    exc = TelegramNetworkError(method=Any, message="boom")
    await default_error_handler(event=None, exception=exc)  # type: ignore[arg-type]


async def test_unhandled_logged(caplog: Any) -> None:
    await default_error_handler(event=None, exception=ValueError("x"))  # type: ignore[arg-type]
    assert any("Unhandled error" in r.message for r in caplog.records)


def test_register_error_handler_on_dispatcher() -> None:
    from aiogram import Dispatcher

    dp = Dispatcher()
    register_error_handler(dp)


async def test_retry_middleware_retries_then_succeeds() -> None:
    calls = 0

    async def handler(event: Any, data: dict[str, Any]) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TelegramNetworkError(method=Any, message="net")
        return "ok"

    mw = RetryMiddleware(max_retries=3, delay=0)
    result = await mw(handler, event=None, data={})  # type: ignore[arg-type]
    assert result == "ok"
    assert calls == 2


async def test_retry_middleware_raises_after_max() -> None:
    async def handler(event: Any, data: dict[str, Any]) -> None:
        raise TelegramNetworkError(method=Any, message="net")

    mw = RetryMiddleware(max_retries=2, delay=0)
    try:
        await mw(handler, event=None, data={})  # type: ignore[arg-type]
        raised = False
    except TelegramNetworkError:
        raised = True
    assert raised is True


def test_metrics_endpoint_exposes_counters() -> None:
    UPDATES_TOTAL.labels(type="message").inc()
    app = create_metrics_app()
    assert app.router.routes()  # /health and /metrics registered
    assert b"botkit_updates_total" in generate_latest()


def test_update_types_importable() -> None:
    # smoke: aiogram types used by handlers exist in this version
    assert Update and Message and CallbackQuery and User
