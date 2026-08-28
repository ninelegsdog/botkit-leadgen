from __future__ import annotations

from aiohttp import web
from sqlalchemy import text

from src.core.bot_factory import AppState


async def health_handler(request: web.Request) -> web.Response:
    try:
        state: AppState = request.app["state"]
        async with state.db.session() as session:
            await session.execute(text("SELECT 1"))
        return web.Response(status=200, text="ok")
    except Exception:
        return web.Response(status=500, text="db unavailable")


async def metrics_handler(request: web.Request) -> web.Response:
    state: AppState = request.app["state"]
    m = state.metrics
    return web.json_response(
        {
            "messages": m.messages_processed,
            "leads": m.leads_created,
            "taken": m.leads_taken,
            "errors": m.errors,
            "uptime": m.uptime_seconds(),
        }
    )


def create_app(state: AppState) -> web.Application:
    app = web.Application()
    app["state"] = state
    app.router.add_get("/health", health_handler)
    app.router.add_get("/metrics", metrics_handler)
    return app
