"""Mock CRM server for local development and testing.

Imitates Bitrix24, AmoCRM and generic webhook endpoints. Configurable via
query parameters:

  ?status=200            - HTTP status to return (default 200)
  ?result=<id>           - Bitrix24: return {"result": <id>}
  ?error=<msg>           - Return application error in body
  ?error_code=<code>     - Bitrix24: return {"error": <msg>, "error_code": <code>}
  ?delay=<seconds>       - Artificial delay before response
  ?rate_limit=1          - Return 429 Too Many Requests

All received requests are logged to stdout for verification.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from aiohttp import web

logger = logging.getLogger("mock_crm")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

REQUESTS: list[dict[str, Any]] = []


async def _log_request(request: web.Request, body: Any) -> None:
    entry = {
        "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "method": request.method,
        "path": request.path,
        "query": str(request.query_string),
        "headers": dict(request.headers),
        "body": body,
    }
    REQUESTS.append(entry)
    logger.info("%s %s %s", request.method, request.path, request.query_string)
    if body:
        logger.info("  body: %s", json.dumps(body, ensure_ascii=False)[:500])


def _parse_params(request: web.Request) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key in ("status", "result", "error", "error_code", "delay", "rate_limit"):
        if key in request.query:
            params[key] = request.query[key]
    return params


async def _handle(request: web.Request) -> web.Response:
    params = _parse_params(request)

    # Rate limit simulation
    if params.get("rate_limit") == "1":
        return web.Response(status=429, text="Too Many Requests")

    # Artificial delay
    if "delay" in params:
        try:
            await asyncio.sleep(float(params["delay"]))
        except ValueError:
            pass

    # Read body
    body: Any = None
    try:
        body = await request.json()
    except Exception:
        body = await request.text()

    await _log_request(request, body)

    # Determine response
    status = int(params.get("status", 200))

    if status >= 400:
        return web.Response(status=status, text=f"HTTP {status} error")

    # Bitrix24 style: check for "error" in params
    if "error" in params or "error_code" in params:
        error_body: dict[str, Any] = {"error": params.get("error", "API error")}
        if "error_code" in params:
            try:
                error_body["error_code"] = int(params["error_code"])
            except ValueError:
                error_body["error_code"] = params["error_code"]
        return web.json_response(error_body, status=200)

    # Bitrix24 style: return result
    if "result" in params:
        return web.json_response({"result": params["result"]}, status=status)

    # AmoCRM style: return embedded leads
    if request.path == "/api/v4/leads":
        lead_id = params.get("result", "1")
        return web.json_response(
            {
                "_embedded": {
                    "leads": [
                        {
                            "id": int(lead_id) if str(lead_id).isdigit() else 1,
                            "name": "Mock Lead",
                        }
                    ]
                }
            },
            status=status,
        )

    # Generic webhook: return 202 with optional X-External-Id
    headers: dict[str, str] = {}
    if "result" in params:
        headers["X-External-Id"] = str(params["result"])
    return web.Response(status=202, headers=headers)


async def _list_requests(request: web.Request) -> web.Response:
    return web.json_response({"count": len(REQUESTS), "requests": REQUESTS})


async def _clear_requests(request: web.Request) -> web.Response:
    REQUESTS.clear()
    return web.Response(text="cleared")


async def _health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", _health)
    app.router.add_get("/requests", _list_requests)
    app.router.add_delete("/requests", _clear_requests)
    # Catch-all for CRM endpoints
    app.router.add_route("*", "/{path:.*}", _handle)
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=8090)
