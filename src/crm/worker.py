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
from src.crm.service import (
    check_idempotency_key,
    load_amocrm_access_token,
    record_idempotency_key,
    update_idempotency_key_delivered,
)

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
    worker_id: str | None = None,
) -> int:
    """Deliver one batch. Returns the number of successfully delivered leads."""
    rows = await service.claim_batch(db, limit, worker_id=worker_id)
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
        lead_id = int(row["lead_id"])
        idempotency_key = f"lead-{lead_id}"

        # Idempotency: if this key was already delivered, skip the CRM call.
        cached = await check_idempotency_key(db, key=idempotency_key)
        if cached is not None:
            await service.mark_sent(db, int(row["id"]), cached["external_id"])
            CRM_EXPORT_TOTAL.labels(provider=provider, status="sent").inc()
            breaker.record_success(provider)
            breaker.reset_probe(provider)
            delivered += 1
            logger.debug(
                "Idempotency hit: lead=%s provider=%s key=%s external_id=%s",
                lead_id, provider, idempotency_key, cached["external_id"],
            )
            continue

        # Record the key as in-flight before calling the CRM.
        await record_idempotency_key(
            db, key=idempotency_key, provider=provider, lead_id=lead_id,
            response_status="pending",
        )

        try:
            external_id = await push(lead, settings, client, db=db)
        except CrmPermanentError as exc:
            await service.mark_failed(db, int(row["id"]), str(exc))
            await record_idempotency_key(
                db, key=idempotency_key, provider=provider, lead_id=lead_id,
                response_status="failed", response_body=str(exc),
            )
            CRM_EXPORT_TOTAL.labels(provider=provider, status="failed").inc()
            breaker.record_failure(provider)
            logger.error("CRM export failed permanently: lead=%s provider=%s: %s", row["lead_id"], provider, exc)
        except CrmTransientError as exc:
            await service.mark_retry(
                db, int(row["id"]), int(row["attempts"]), str(exc), max_attempts,
                backoff_seconds=backoff_seconds,
            )
            await record_idempotency_key(
                db, key=idempotency_key, provider=provider, lead_id=lead_id,
                response_status="retry", response_body=str(exc),
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
            await record_idempotency_key(
                db, key=idempotency_key, provider=provider, lead_id=lead_id,
                response_status="error", response_body=repr(exc),
            )
            CRM_EXPORT_TOTAL.labels(provider=provider, status="retry").inc()
            breaker.record_failure(provider)
            logger.exception("CRM export crashed: lead=%s provider=%s", row["lead_id"], provider)
        else:
            await service.mark_sent(db, int(row["id"]), external_id)
            await update_idempotency_key_delivered(
                db, key=idempotency_key, external_id=external_id,
                response_body="",
            )
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
    # Load persisted AmoCRM access token from DB if available (survives restarts).
    if settings.provider == "amocrm":
        persisted_token = await load_amocrm_access_token(db)
        if persisted_token:
            # dataclass is frozen — recreate with persisted token.
            settings = CrmSettings(
                provider=settings.provider,
                webhook_url=settings.webhook_url,
                webhook_secret=settings.webhook_secret,
                base_url=settings.base_url,
                access_token=persisted_token,
                amocrm_refresh_token=settings.amocrm_refresh_token,
                amocrm_client_id=settings.amocrm_client_id,
                amocrm_client_secret=settings.amocrm_client_secret,
                bitrix_user_id=settings.bitrix_user_id,
                bitrix_webhook_token=settings.bitrix_webhook_token,
                timeout=settings.timeout,
            )
            logger.info("Loaded persisted AmoCRM access token from DB")
    logger.info("CRM export worker started: provider=%s", settings.provider)
    # Single HTTP client reused across all batches — avoids TCP/TLS handshake per lead.
    timeout = httpx.Timeout(settings.timeout, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while not stop_event.is_set():
            try:
                await process_batch(
                    db, settings,
                    max_attempts=config.crm_max_attempts,
                    backoff_seconds=config.crm_backoff_seconds,
                    client=client,
                    worker_id=f"worker-{id(client)}",
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
        if args.dlq_list:
            rows = await service.dlq_list(db)
            if not rows:
                print("DLQ is empty")
            else:
                print(f"{'ID':<6} {'OutboxID':<10} {'LeadID':<8} {'Provider':<12} {'Attempts':<10} {'FailedAt'}")
                print("-" * 80)
                for r in rows:
                    print(
                        f"{r['id']:<6} {r['outbox_id']:<10} {r['lead_id']:<8} "
                        f"{r['provider']:<12} {r['attempts']:<10} {r['failed_at']}"
                    )
                    if r["last_error"]:
                        print(f"    error: {r['last_error'][:200]}")
        if args.dlq_retry is not None:
            ok = await service.dlq_retry(db, args.dlq_retry)
            if ok:
                print(f"DLQ id={args.dlq_retry} requeued to crm_outbox")
            else:
                print(f"DLQ id={args.dlq_retry} not found")
        if args.test:
            row_id = await service.enqueue_test(db, config.crm_provider)
            print(f"test lead queued: outbox id={row_id}")
        if args.once or args.test:
            settings = CrmSettings.from_config(config)
            timeout = httpx.Timeout(settings.timeout, connect=5.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                delivered = await process_batch(
                    db, settings,
                    max_attempts=config.crm_max_attempts,
                    backoff_seconds=config.crm_backoff_seconds,
                    client=client,
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
    parser.add_argument(
        "--dlq-list",
        action="store_true",
        help="list dead-letter queue rows (most recent first)",
    )
    parser.add_argument(
        "--dlq-retry",
        type=int,
        metavar="ID",
        help="requeue a DLQ row by id back to crm_outbox",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_cli(args)))


if __name__ == "__main__":
    main()
