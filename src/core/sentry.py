from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_sentry(dsn: str | None) -> None:
    if not dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=dsn)
        logger.info("Sentry initialized")
    except ImportError:
        logger.warning("sentry-sdk is not installed; Sentry disabled")
