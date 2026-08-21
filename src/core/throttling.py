from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, min_interval: float = 2.0) -> None:
        super().__init__()
        self._min_interval = min_interval
        self._last_message: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else 0
            now = time.time()
            last = self._last_message.get(user_id, 0.0)
            if now - last < self._min_interval:
                return None
            self._last_message[user_id] = now
        return await handler(event, data)
