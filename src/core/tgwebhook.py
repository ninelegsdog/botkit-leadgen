from typing import Any

from aiohttp import web


def build_webhook_app(dispatcher: Any, bot: Any, secret_token: str) -> web.Application:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    app = web.Application()
    handler = SimpleRequestHandler(dispatcher, bot, secret_token=secret_token)
    app.router.add_post("/webhook", handler.handle)
    setup_application(app, dispatcher, bot=bot)
    return app
