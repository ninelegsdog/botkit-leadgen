"""CRM outbox worker: claim due rows, deliver, retry with backoff."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from contextlib import suppress

import httpx

from src.core.config import Config
from src.core.database import Database
from src.core.metrics import CRM_EXPORT_TOTAL, CRM_OUTBOX_PENDING
from src.core.migrations import migrate
from src.crm import service
from src.crm.adapters import CrmPermanentError, CrmSettings, CrmTransientError, push

logger = logging.getLogger(__name__)

# Circuit breaker: after N consecutive failures, stop hitting the CRM for a cool-down window.
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_COOLDOWN_SECONDS = 300  # 5 minutes before half-open probe


class CircuitBreaker:
    """Per-provider circuit breaker to stop hammering a failing CRM."""

    def __init__(self) -> None:
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float | None] = {}
        self._half_open: dict[str, bool] = {}

    def record_failure(self, provider: str) -> None:
        self._failures[provider] = self._failures.get(provider, 0) + 1
        if self._failures[provider] >= CIRCUIT_FAILURE_THRESHOLD and self._opened_at.get(provider) is None:
            self._opened_at[provider] = time.monotonic()
            self._half_open[provider] = False
            logger.warning(
                "Circuit breaker OPENED for provider=%s after %s consecutive failures",
                provider,
                self._failures[provider],
            )

    def record_success(self, provider: str) -> None:
        self._failures[provider] = 0
        self._opened_at[provider] = None
        self._half_open[provider] = False

    def is_open(self, provider: str) -> bool:
        opened_at = self._opened_at.get(provider)
        if opened_at is None:
            return False
        # Half-open probe after cool-down: allow one attempt.
        if time.monotonic() - opened_at >= CIRCUIT_COOLDOWN_SECONDS:
            self._half_open[provider] = True
            return True  # still "open" but one probe allowed below
        return True

    def allow_probe(self, provider: str) -> bool:
        """True if a single half-open probe attempt is allowed."""
        return self._half_open.get(provider, False)

    def reset_probe(self, provider: str) -> None:
        self._half_open[provider] = False


_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(provider: str) -> CircuitBreaker:
    if provider not in _circuit_breakers:
        _circuit_breakers[provider] = CircuitBreaker()
    return _circuit_breakers[provider]


async def process_batch(
    db: Database,
    settings: CrmSettings,
    *,
    max_attempts: int = 6,
    limit: int = 20,
    backoff_seconds: tuple[int, ...] = service.BACKOFF_SECONDS,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Deliver one batch. Returns the number of successfully delivered leads."""
    rows = await service.claim_batch(db, limit)
    delivered = 0
    for row in rows:
        provider = str(row["provider"])
        breaker = get_breaker(provider)
        if breaker.is_open(provider) and not breaker.allow_probe(provider):
            # Circuit open: postpone without calling CRM.
            await service.mark_retry(
                db, int(row["id"]), int(row["attempts"]),
                "circuit breaker open", max_attempts,
                backoff_seconds=backoff_seconds,
            )
            CRM_EXPORT_TOTAL.labels(provider=provider, status="retry").inc()
            continue
        try:
            lead = json.loads(str(row["payload"]))
        except ValueError as exc:
            await service.mark_failed(db, int(row["id"]), f"bad payload: {exc}")
            CRM_EXPORT_TOTAL.labels(provider=provider, status="failed").inc()
            continue
        try:
            external_id = await push(lead, settings, client)
        except CrmPermanentError as exc:
            await service.mark_failed(db, int(row["id"]), str(exc))
            CRM_EXPORT_TOTAL.labels(provider=provider, status="failed").inc()
            breaker.record_failure(provider)
            logger.error("CRM export failed permanently: lead=%s provider=%s: %s", row["lead_id"], provider, exc)
        except CrmTransientError as exc:
            await service.mark_retry(
                db, int(row["id"]), int(row["attempts"]), str(exc), max_attempts,
                backoff_seconds=backoff_seconds,
            )
            CRM_EXPORT_TOTAL.labels(provider=provider, status="retry").inc()
            breaker.record_failure(provider)
            logger.warning(
                "CRM export retry: lead=%s provider=%s attempt=%s: %s",
                row["lead_id"],
                provider,
                row["attempts"],
                exc,
            )
        except Exception as exc:  # noqa: BLE001 - a worker must never die on one lead
            await service.mark_retry(
                db, int(row["id"]), int(row["attempts"]), repr(exc), max_attempts,
                backoff_seconds=backoff_seconds,
            )
            CRM_EXPORT_TOTAL.labels(provider=provider, status="retry").inc()
            breaker.record_failure(provider)
            logger.exception("CRM export crashed: lead=%s provider=%s", row["lead_id"], provider)
        else:
            await service.mark_sent(db, int(row["id"]), external_id)
            CRM_EXPORT_TOTAL.labels(provider=provider, status="sent").inc()
            breaker.record_success(provider)
            breaker.reset_probe(provider)
            delivered += 1
    CRM_OUTBOX_PENDING.set(await service.pending_count(db))
    return delivered


async def worker_loop(db: Database, config: Config, stop_event: asyncio.Event) -> None:
    settings = CrmSettings.from_config(config)
    if settings.provider == "off":
        logger.info("CRM export disabled (CRM_PROVIDER=off)")
        return
    logger.info("CRM export worker started: provider=%s", settings.provider)
    while not stop_event.is_set():
        try:
            await process_batch(
                db, settings,
                max_attempts=config.crm_max_attempts,
                backoff_seconds=config.crm_backoff_seconds,
            )
        except Exception:  # noqa: BLE001 - keep the loop alive across DB hiccups
            logger.exception("CRM export batch failed")
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=config.crm_poll_seconds)
    logger.info("CRM export worker stopped")


async def _cli(args: argparse.Namespace) -> int:
    config = Config.from_env()
    db = Database(config)
    await migrate(db)
    try:
        if args.retry_failed:
            count = await service.retry_failed(db)
            print(f"requeued: {count}")
        if args.test:
            row_id = await service.enqueue_test(db, config.crm_provider)
            print(f"test lead queued: outbox id={row_id}")
        if args.once or args.test:
            settings = CrmSettings.from_config(config)
            delivered = await process_batch(
                db, settings,
                max_attempts=config.crm_max_attempts,
                backoff_seconds=config.crm_backoff_seconds,
            )
            print(f"delivered: {delivered}")
        return 0
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="CRM outbox worker")
    parser.add_argument("--once", action="store_true", help="process one batch and exit")
    parser.add_argument("--test", action="store_true", help="queue and send a test lead")
    parser.add_argument("--retry-failed", action="store_true", help="return failed rows to the queue")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_cli(args)))


if __name__ == "__main__":
    main()
