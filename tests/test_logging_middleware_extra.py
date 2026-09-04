"""Extra logging middleware tests for 100% coverage."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.logging import LoggingMiddleware, get_conversation_id, set_conversation_id


@pytest.mark.asyncio
async def test_logging_middleware_chat() -> None:
    mw = LoggingMiddleware()
    chat = MagicMock()
    chat.id = 123
    event = MagicMock()
    event.chat = chat
    event.from_user = None
    event.message = None

    async def handler(event, data):
        return get_conversation_id()

    result = await mw(handler, event, {})
    assert result == "123"
    set_conversation_id("-")


@pytest.mark.asyncio
async def test_logging_middleware_from_user() -> None:
    mw = LoggingMiddleware()
    user = MagicMock()
    user.id = 456
    event = MagicMock()
    event.chat = None
    event.from_user = user
    event.message = None

    async def handler(event, data):
        return get_conversation_id()

    result = await mw(handler, event, {})
    assert result == "456"
    set_conversation_id("-")


@pytest.mark.asyncio
async def test_logging_middleware_message_chat() -> None:
    mw = LoggingMiddleware()
    chat2 = MagicMock()
    chat2.id = 789
    msg = MagicMock()
    msg.chat = chat2
    event = MagicMock()
    event.chat = None
    event.from_user = None
    event.message = msg

    async def handler(event, data):
        return get_conversation_id()

    result = await mw(handler, event, {})
    assert result == "789"
    set_conversation_id("-")


@pytest.mark.asyncio
async def test_logging_middleware_no_ids() -> None:
    mw = LoggingMiddleware()
    event = MagicMock()
    event.chat = None
    event.from_user = None
    event.message = None

    async def handler(event, data):
        return get_conversation_id()

    result = await mw(handler, event, {})
    assert result == "-"
    set_conversation_id("-")
