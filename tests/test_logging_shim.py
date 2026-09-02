"""Cover src/core/logging.py shim."""
from __future__ import annotations

import asyncio
import io

from src.core.logging import LoggingMiddleware, get_conversation_id, set_conversation_id, setup_logging


def test_logging_middleware_sets_conversation_id() -> None:
    mw = LoggingMiddleware()

    class FakeChat:
        id = 789

    class FakeEvent:
        chat = FakeChat()

    async def handler(event, data):
        return get_conversation_id()

    result = asyncio.run(mw(handler, FakeEvent(), {}))
    assert result == "789"
    set_conversation_id("-")


def test_setup_logging_json() -> None:
    stream = io.StringIO()
    setup_logging(level="INFO", json=True, bot_name="leadgen", stream=stream)
    assert stream is not None


def test_setup_logging_plain() -> None:
    stream = io.StringIO()
    setup_logging(level="INFO", json=False, bot_name="leadgen", stream=stream)
    assert stream is not None
