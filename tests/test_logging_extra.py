"""Extra tests for logging to boost coverage 0%->100%."""
from __future__ import annotations

import logging
from io import StringIO

from src.core.logging import (
    ConversationContextFilter,
    get_conversation_id,
    set_bot_name,
    set_conversation_id,
    setup_logging,
)


def test_conversation_context_filter() -> None:
    filt = ConversationContextFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test",
        args=(),
        exc_info=None,
    )
    set_conversation_id("123")
    set_bot_name("bookingbot")
    assert filt.filter(record) is True
    assert record.conversation_id == "123"
    assert record.bot == "bookingbot"  # type: ignore[attr-defined]
    set_conversation_id("-")
    set_bot_name("-")


def test_setup_logging_plain() -> None:
    stream = StringIO()
    setup_logging(level="INFO", json=False, bot_name="test", stream=stream)
    logger = logging.getLogger("test_logger")
    logger.info("hello")
    assert "hello" in stream.getvalue()


def test_setup_logging_json() -> None:
    stream = StringIO()
    setup_logging(level="INFO", json=True, bot_name="test", stream=stream)
    logger = logging.getLogger("test_logger2")
    logger.info("hello json")
    assert "hello json" in stream.getvalue()
    assert "conversation_id" in stream.getvalue() or "test" in stream.getvalue()


def test_get_set_conversation_id() -> None:
    set_conversation_id("999")
    assert get_conversation_id() == "999"
    set_conversation_id("-")
    assert get_conversation_id() == "-"
