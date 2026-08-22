from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.types import TelegramObject

from src.core.metrics import ERRORS_TOTAL

logger = logging.getLogger(__name__)


async def default_error_handler(event: TelegramObject, exception: Exception) -> None:
    if isinstance(exception, TelegramRetryAfter):
        ERRORS_TOTAL.labels(error_type="retry_after").inc()
        logger.warning("TelegramRetryAfter: %s", exception)
        await asyncio.sleep(exception.retry_after)
        return
    if isinstance(exception, TelegramNetworkError):
        ERRORS_TOTAL.labels(error_type="network").inc()
        logger.warning("TelegramNetworkError: %s", exception)
        return
    ERRORS_TOTAL.labels(error_type="unhandled").inc()
    logger.critical("Unhandled error: %s", exception, exc_info=True)


def register_error_handler(dp: Any) -> None:
    @dp.error()  # type: ignore[untyped-decorator]
    async def _on_error(event: TelegramObject, exception: Exception) -> None:
        await default_error_handler(event, exception)


class RetryMiddleware:
    """Retries handler execution on transient Telegram errors."""

    def __init__(self, max_retries: int = 3, delay: float = 1.0) -> None:
        self._max_retries = max_retries
        self._delay = delay

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        retries = 0
        while True:
            try:
                return await handler(event, data)
            except TelegramRetryAfter as exc:
                ERRORS_TOTAL.labels(error_type="retry_after").inc()
                retries += 1
                if retries >= self._max_retries:
                    raise
                logger.warning("RetryAfter in handler: %s", exc)
                await asyncio.sleep(exc.retry_after)
            except TelegramNetworkError as exc:
                ERRORS_TOTAL.labels(error_type="network").inc()
                retries += 1
                if retries >= self._max_retries:
                    raise
                logger.warning("NetworkError in handler (attempt %s): %s", retries, exc)
                await asyncio.sleep(self._delay * retries)
