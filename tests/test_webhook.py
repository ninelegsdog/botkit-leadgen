"""Server-surface tests for the aiohttp app (health + metrics).

Leadgen runs in polling mode: it exposes /health and /metrics but has no
Telegram webhook secret endpoint. The webhook security contract (if a bot ever
serves Telegram webhooks) must verify X-Telegram-Bot-Api-Secret-Token; here we
assert the absence of an unauthenticated mutation path instead.
"""

from __future__ import annotations

from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from src.core.webhook import create_app


class _FakeMetrics:
    def __getattr__(self, name: str):
        return 0

    def uptime_seconds(self) -> float:
        return 0.0


@pytest.fixture
async def client(db: Any):
    state = type("State", (), {"db": db, "metrics": _FakeMetrics()})()
    app = create_app(state)
    server = TestServer(app)
    cl = TestClient(server)
    await cl.start_server()
    yield cl
    await cl.close()


@pytest.mark.no_req
@pytest.mark.webhook
async def test_health_ok(client: TestClient):
    resp = await client.get("/health")
    assert resp.status == 200
    assert (await resp.text()) == "ok"


@pytest.mark.no_req
@pytest.mark.webhook
async def test_metrics_json(client: TestClient):
    resp = await client.get("/metrics")
    assert resp.status == 200
    body = await resp.json()
    assert isinstance(body, dict)


@pytest.mark.no_req
@pytest.mark.webhook
async def test_no_telegram_webhook_endpoint(client: TestClient):
    # Polling bot: no Telegram webhook secret endpoint exists to attack.
    resp = await client.post("/webhook", json={"update_id": 1})
    assert resp.status == 404
