"""AmoCRM access token refresh on 401."""

from __future__ import annotations

import httpx
import pytest

from src.crm.adapters import CrmPermanentError, CrmSettings, push


@pytest.mark.asyncio
async def test_amocrm_401_refresh_and_retry() -> None:
    """401 → refresh token → retry with new token → success."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if "/oauth2/access_token" in request.url.path:
            return httpx.Response(200, json={"access_token": "new-token-123"})
        # First lead request gets 401, second gets 200
        if len([c for c in calls if c == "/api/v4/leads"]) == 1:
            return httpx.Response(401, json={"error": "token expired"})
        return httpx.Response(200, json={"_embedded": {"leads": [{"id": 55}]}})

    settings = CrmSettings(
        provider="amocrm",
        base_url="https://example.amocrm.ru",
        access_token="old-token",
        amocrm_refresh_token="refresh-token",
        amocrm_client_id="client-id",
        amocrm_client_secret="client-secret",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        external_id = await push(
            {"id": 1, "client_name": "Alice", "field_values": "{}"},
            settings,
            client,
        )
    assert external_id == "55"
    assert "/oauth2/access_token" in calls  # refresh was called


@pytest.mark.asyncio
async def test_amocrm_refresh_fails_goes_permanent() -> None:
    """Refresh token expired → refresh fails → permanent error (DLQ)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "/oauth2/access_token" in request.url.path:
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(401, json={"error": "token expired"})

    settings = CrmSettings(
        provider="amocrm",
        base_url="https://example.amocrm.ru",
        access_token="old-token",
        amocrm_refresh_token="expired-refresh",
        amocrm_client_id="client-id",
        amocrm_client_secret="client-secret",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(CrmPermanentError, match="amocrm token refresh"):
            await push(
                {"id": 2, "field_values": "{}"},
                settings,
                client,
            )


@pytest.mark.asyncio
async def test_amocrm_success_without_refresh() -> None:
    """200 on first try → no refresh call."""
    refresh_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal refresh_called
        if "/oauth2/access_token" in request.url.path:
            refresh_called = True
        return httpx.Response(200, json={"_embedded": {"leads": [{"id": 7}]}})

    settings = CrmSettings(
        provider="amocrm",
        base_url="https://example.amocrm.ru",
        access_token="valid-token",
        amocrm_refresh_token="refresh-token",
        amocrm_client_id="client-id",
        amocrm_client_secret="client-secret",
    )
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        external_id = await push(
            {"id": 3, "field_values": "{}"},
            settings,
            client,
        )
    assert external_id == "7"
    assert not refresh_called  # refresh not called on success
