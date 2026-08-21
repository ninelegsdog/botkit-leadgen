from __future__ import annotations

import asyncio
import logging

from src.app import register_routers
from src.core.auth import AuthMiddleware
from src.core.bot_factory import create_app
from src.core.migrations import migrate
from src.core.throttling import ThrottlingMiddleware
from src.escalation.scheduler import escalation_loop


async def main() -> None:
    state = create_app()
    await migrate(state.db)
    state.dp.message.middleware(AuthMiddleware(state.db))
    state.dp.message.middleware(ThrottlingMiddleware())
    state.dp.callback_query.middleware(AuthMiddleware(state.db))
    register_routers(state)
    logging.basicConfig(level=state.config.log_level)
    asyncio.create_task(escalation_loop(state.bot, state.db, state.config.escalation_minutes))
    await state.bot.delete_webhook(drop_pending_updates=True)
    await state.dp.start_polling(state.bot)


if __name__ == "__main__":
    asyncio.run(main())
