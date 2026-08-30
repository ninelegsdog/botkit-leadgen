from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Any

from aiogram.types import BufferedInputFile
from aiohttp import web

from src.app import register_routers
from src.core.auth import AuthMiddleware
from src.core.bot_factory import create_app
from src.core.errors import RetryMiddleware, register_error_handler
from src.core.metrics import UpdatesMiddleware, health, metrics, start_metrics_server
from src.core.migrations import migrate
from src.core.sentry import init_sentry
from src.core.tgwebhook import build_webhook_app
from src.core.throttling import ThrottlingMiddleware
from src.escalation.scheduler import escalation_loop


def _load_cert(path: str) -> BufferedInputFile | None:
    cert_path = Path(path)
    if not cert_path.is_file():
        return None
    return BufferedInputFile(cert_path.read_bytes(), filename="webhook_public.pem")


async def _run_webhook(state: Any, shutdown_event: asyncio.Event) -> None:
    app = build_webhook_app(state.dp, state.bot, state.config.webhook_secret)
    app["state"] = state
    app.router.add_get("/health", health)
    app.router.add_get("/metrics", metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", state.config.metrics_port)
    await site.start()
    logging.info("Webhook HTTP server listening on :%s", state.config.metrics_port)

    await state.bot.delete_webhook(drop_pending_updates=True)
    cert = await asyncio.to_thread(_load_cert, state.config.webhook_cert_path)
    if cert is None:
        logging.warning("WEBHOOK_CERT_PATH not found: %s", state.config.webhook_cert_path)
    await state.bot.set_webhook(
        url=state.config.webhook_url,
        secret_token=state.config.webhook_secret or None,
        certificate=cert,
    )
    logging.info("Telegram webhook registered: %s", state.config.webhook_url)
    try:
        await shutdown_event.wait()
    finally:
        await state.bot.delete_webhook()
        await runner.cleanup()


async def _run_polling(state: Any, shutdown_event: asyncio.Event) -> None:
    await state.bot.delete_webhook(drop_pending_updates=True)
    runner = await start_metrics_server(state.config.metrics_port)
    try:
        await asyncio.wait([
            asyncio.create_task(state.dp.start_polling(state.bot)),
            asyncio.create_task(shutdown_event.wait()),
        ])
    finally:
        await state.dp.stop_polling()
        await state.bot.session.close()
        await runner.cleanup()


async def main() -> None:
    state = create_app()
    state.config.validate()
    init_sentry(state.config.sentry_dsn)
    await migrate(state.db)
    state.dp.message.middleware(AuthMiddleware(state.db))
    state.dp.message.middleware(ThrottlingMiddleware(redis_url=state.config.redis_url))
    state.dp.callback_query.middleware(AuthMiddleware(state.db))
    state.dp.update.outer_middleware(UpdatesMiddleware())
    state.dp.message.middleware(RetryMiddleware())
    register_error_handler(state.dp)
    register_routers(state)
    logging.basicConfig(level=state.config.log_level)
    escalation_task = asyncio.create_task(
        escalation_loop(state.bot, state.db, state.config.escalation_minutes)
    )

    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        if state.config.webhook_url:
            await _run_webhook(state, shutdown_event)
        else:
            await _run_polling(state, shutdown_event)
    finally:
        escalation_task.cancel()
        try:
            await escalation_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
