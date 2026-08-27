from __future__ import annotations

import asyncio
import logging
import signal

from src.app import register_routers
from src.core.auth import AuthMiddleware
from src.core.bot_factory import create_app
from src.core.errors import RetryMiddleware, register_error_handler
from src.core.metrics import UpdatesMiddleware, start_metrics_server
from src.core.migrations import migrate
from src.core.sentry import init_sentry
from src.core.throttling import ThrottlingMiddleware
from src.escalation.scheduler import escalation_loop


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
    await state.bot.delete_webhook(drop_pending_updates=True)
    runner = await start_metrics_server(state.config.metrics_port)

    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        await asyncio.wait([
            asyncio.create_task(state.dp.start_polling(state.bot)),
            asyncio.create_task(shutdown_event.wait()),
        ])
    finally:
        escalation_task.cancel()
        try:
            await escalation_task
        except asyncio.CancelledError:
            pass
        await state.dp.stop_polling()
        await state.bot.session.close()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
