"""Provider adapters: success, error classification, payload shape."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from src.crm.adapters import (
    CrmPermanentError,
    CrmSettings,
    CrmTransientError,
    push,
)


@pytest.mark.asyncio
async def test_bitrix_success_returns_external_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("crm.lead.add.json")
        body = json.loads(request.content)
        assert body["fields"]["NAME"] == "Alice"
        assert body["fields"]["PHONE"] == [{"VALUE": "+7", "VALUE_TYPE": "WORK"}]
        return httpx.Response(200, json={"result": 42})

    settings = CrmSettings(
        provider="bitrix24",
        base_url="https://portal.bitrix24.ru",
        bitrix_user_id="1",
        bitrix_webhook_token="token",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        external_id = await push(
            {"id": 1, "client_name": "Alice", "client_phone": "+7", "field_values": "{}"},
            settings,
            client,
        )
    assert external_id == "42"


@pytest.mark.asyncio
async def test_bitrix_server_error_is_transient() -> None:
    settings = CrmSettings(
        provider="bitrix24",
        base_url="https://portal.bitrix24.ru",
        bitrix_user_id="1",
        bitrix_webhook_token="token",
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(CrmTransientError):
            await push({"id": 1, "field_values": "{}"}, settings, client)


@pytest.mark.asyncio
async def test_bitrix_bad_request_is_permanent() -> None:
    settings = CrmSettings(
        provider="bitrix24",
        base_url="https://portal.bitrix24.ru",
        bitrix_user_id="1",
        bitrix_webhook_token="token",
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(400))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(CrmPermanentError):
            await push({"id": 1, "field_values": "{}"}, settings, client)


@pytest.mark.asyncio
async def test_amocrm_success_returns_lead_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(200, json={"_embedded": {"leads": [{"id": 99}]}})

    settings = CrmSettings(
        provider="amocrm",
        base_url="https://example.amocrm.ru",
        access_token="secret-token",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        external_id = await push(
            {"id": 2, "client_name": "Bob", "client_phone": "+7", "field_values": "{}"},
            settings,
            client,
        )
    assert external_id == "99"


@pytest.mark.asyncio
async def test_generic_sends_signature_and_idempotency_key() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["signature"] = request.headers.get("X-Signature", "")
        captured["idempotency"] = request.headers.get("X-Idempotency-Key", "")
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(202)

    secret = "top-secret"
    settings = CrmSettings(
        provider="generic",
        webhook_url="https://example.com/hook",
        webhook_secret=secret,
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        external_id = await push(
            {"id": 9, "client_name": "Carol", "field_values": "{}"}, settings, client
        )
    assert external_id == ""
    assert captured["idempotency"] == "lead-9"
    assert captured["signature"].startswith("sha256=")
    expected = hmac.new(secret.encode("utf-8"), captured["body"].encode("utf-8"), hashlib.sha256).hexdigest()
    assert captured["signature"] == f"sha256={expected}"


@pytest.mark.asyncio
async def test_generic_rate_limit_is_transient() -> None:
    settings = CrmSettings(provider="generic", webhook_url="https://example.com/hook")
    transport = httpx.MockTransport(lambda request: httpx.Response(429))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(CrmTransientError):
            await push({"id": 3, "field_values": "{}"}, settings, client)


@pytest.mark.asyncio
async def test_unknown_provider_is_permanent() -> None:
    settings = CrmSettings(provider="salesforce")
    with pytest.raises(CrmPermanentError):
        await push({"id": 4, "field_values": "{}"}, settings)
