from __future__ import annotations

from copy import deepcopy
from time import time
from typing import Any


def message_update(
    *,
    text: str = "hello",
    user_id: int = 1001,
    chat_id: int = 1001,
    update_id: int = 1,
) -> dict[str, Any]:
    """Build a valid Telegram `message` Update dict with sane defaults."""
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time()),
            "chat": {"id": chat_id, "type": "private"},
            "from": {
                "id": user_id,
                "is_bot": False,
                "first_name": "E2E Test",
            },
            "text": text,
        },
    }


def callback_update(
    *,
    data: str = "confirm",
    callback_id: str = "cb-1",
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a valid Telegram `callback_query` Update dict."""
    message = deepcopy(message_update(**kwargs)["message"])
    return {
        "update_id": kwargs.get("update_id", 1),
        "callback_query": {
            "id": callback_id,
            "from": message["from"],
            "message": message,
            "chat_instance": "test",
            "data": data,
        },
    }
