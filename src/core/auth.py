from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.core.database import Database


class AuthMiddleware(BaseMiddleware):
    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self._db
        return await handler(event, data)


# The admin password gate now lives in botkit-core: the fleet had three
# different shapes of admin auth, none of them enforced everywhere, so a security
# fix here had to be applied by hand nine times and was missed. Re-export it so the
# routers import one implementation instead of a per-bot copy.
from botkit_core.admin import AdminGate as AdminGate  # noqa: E402
