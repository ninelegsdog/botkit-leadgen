"""Logging shim - re-exports botkit_core.logging + aiogram middleware for conversation_id."""
from __future__ import annotations

from typing import Any

from botkit_core.logging import (
    ConversationContextFilter,
    get_conversation_id,
    get_json_formatter,
    set_bot_name,
    set_conversation_id,
    setup_logging,
)

__all__ = [
    "ConversationContextFilter",
    "LoggingMiddleware",
    "get_conversation_id",
    "get_json_formatter",
    "set_bot_name",
    "set_conversation_id",
    "setup_logging",
]


class LoggingMiddleware:
    """Sets conversation_id (chat_id or user_id) per update for JSON logs."""

    async def __call__(self, handler: Any, event: Any, data: dict[str, Any]) -> Any:
        cid = "-"
        chat = getattr(event, "chat", None)
        if chat is not None and hasattr(chat, "id"):
            cid = str(chat.id)
        else:
            user = getattr(event, "from_user", None)
            if user is not None and hasattr(user, "id"):
                cid = str(user.id)
            else:
                msg = getattr(event, "message", None)
                if msg is not None:
                    c2 = getattr(msg, "chat", None)
                    if c2 is not None and hasattr(c2, "id"):
                        cid = str(c2.id)
        set_conversation_id(cid)
        return await handler(event, data)
