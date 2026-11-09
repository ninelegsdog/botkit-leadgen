"""Provider adapters for CRM export.

Each adapter turns the stored lead payload into a provider-specific request and
maps HTTP failures onto two outcomes: retry later (transient) or give up
(permanent). A wrong payload must not be retried forever.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CrmError(Exception):
    """Base class for CRM export failures."""


class CrmTransientError(CrmError):
    """Network, timeout, rate limit or 5xx: safe to retry."""


class CrmPermanentError(CrmError):
    """Bad credentials or payload: retrying will not help."""


@dataclass(frozen=True)
class CrmSettings:
    provider: str
    webhook_url: str = ""
    webhook_secret: str = ""
    base_url: str = ""
    access_token: str = ""
    bitrix_user_id: str = ""
    bitrix_webhook_token: str = ""
    timeout: float = 10.0

    @classmethod
    def from_config(cls, config: Any) -> CrmSettings:
        return cls(
            provider=config.crm_provider,
            webhook_url=config.crm_webhook_url,
            webhook_secret=config.crm_webhook_secret,
            base_url=config.crm_base_url,
            access_token=config.crm_access_token,
            bitrix_user_id=config.crm_bitrix_user_id,
            bitrix_webhook_token=config.crm_bitrix_webhook_token,
            timeout=config.crm_timeout_seconds,
        )


def _field_values(lead: dict[str, Any]) -> dict[str, Any]:
    raw = lead.get("field_values") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _comments(lead: dict[str, Any]) -> str:
    parts = [f"{key}: {value}" for key, value in _field_values(lead).items()]
    return "\n".join(parts)


def _title(lead: dict[str, Any]) -> str:
    return f"Заявка #{lead.get('id')} из Telegram"


def _check_response(response: httpx.Response, provider: str) -> None:
    if 200 <= response.status_code < 300:
        # Bitrix24 returns HTTP 200 even on application errors; detect via body.
        try:
            body = response.json()
        except ValueError:
            return
        if isinstance(body, dict) and body.get("error"):
            detail = str(body.get("error"))[:300]
            message = f"{provider} API error: {detail}"
            if body.get("error_code") in {429} or str(body.get("error_code", "")).startswith("5"):
                raise CrmTransientError(message)
            raise CrmPermanentError(message)
        return
    if response.status_code == 409:
        # Duplicate delivery: the provider already has this lead.
        return
    detail = response.text[:300]
    message = f"{provider} HTTP {response.status_code}: {detail}"
    if response.status_code in {408, 425, 429} or response.status_code >= 500:
        raise CrmTransientError(message)
    raise CrmPermanentError(message)


async def _post(
    settings: CrmSettings,
    url: str,
    *,
    client: httpx.AsyncClient | None,
    **kwargs: Any,
) -> httpx.Response:
    if client is not None:
        return await client.post(url, **kwargs)
    async with httpx.AsyncClient(timeout=settings.timeout) as owned:
        return await owned.post(url, **kwargs)


async def _push_bitrix24(
    lead: dict[str, Any], settings: CrmSettings, client: httpx.AsyncClient | None
) -> str:
    url = (
        f"{settings.base_url}/rest/{settings.bitrix_user_id}/"
        f"{settings.bitrix_webhook_token}/crm.lead.add.json"
    )
    phone = lead.get("client_phone")
    fields: dict[str, Any] = {
        "TITLE": _title(lead),
        "NAME": lead.get("client_name") or "Клиент",
        "COMMENTS": _comments(lead),
        "SOURCE_ID": "TELEGRAM",
        "SOURCE_DESCRIPTION": "botkit-leadgen",
    }
    if phone:
        fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "WORK"}]
    response = await _post(settings, url, client=client, json={"fields": fields})
    _check_response(response, "bitrix24")
    try:
        external_id = response.json().get("result")
    except ValueError as exc:
        raise CrmPermanentError(f"bitrix24 returned non-JSON: {exc}") from exc
    if external_id is None and response.status_code != 409:
        raise CrmPermanentError("bitrix24 response has no result id")
    return str(external_id) if external_id is not None else ""


async def _push_amocrm(
    lead: dict[str, Any], settings: CrmSettings, client: httpx.AsyncClient | None
) -> str:
    url = f"{settings.base_url}/api/v4/leads"
    custom_fields: list[dict[str, Any]] = []
    phone = lead.get("client_phone")
    if phone:
        custom_fields.append(
            {
                "field_code": "PHONE",
                "values": [{"value": phone, "enum_code": "WORK"}],
            }
        )
    body = [
        {
            "name": _title(lead),
            "price": 0,
            "custom_fields_values": custom_fields,
        }
    ]
    response = await _post(
        settings,
        url,
        client=client,
        json=body,
        headers={"Authorization": f"Bearer {settings.access_token}"},
    )
    _check_response(response, "amocrm")
    if response.status_code == 409:
        return ""
    try:
        leads = response.json()["_embedded"]["leads"]
        return str(leads[0]["id"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise CrmPermanentError(f"amocrm response has no lead id: {exc}") from exc


async def _push_generic(
    lead: dict[str, Any], settings: CrmSettings, client: httpx.AsyncClient | None
) -> str:
    body = json.dumps({"event": "lead.created", "lead": lead}, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Idempotency-Key": f"lead-{lead.get('id')}",
    }
    if settings.webhook_secret:
        digest = hmac.new(
            settings.webhook_secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        headers["X-Signature"] = f"sha256={digest}"
    response = await _post(
        settings, settings.webhook_url, client=client, content=body, headers=headers
    )
    _check_response(response, "generic")
    return str(response.headers.get("X-External-Id", ""))


_ADAPTERS = {
    "bitrix24": _push_bitrix24,
    "amocrm": _push_amocrm,
    "generic": _push_generic,
}


async def push(
    lead: dict[str, Any],
    settings: CrmSettings,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Send one lead to the configured provider. Returns the external id."""
    adapter = _ADAPTERS.get(settings.provider)
    if adapter is None:
        raise CrmPermanentError(f"unknown CRM provider: {settings.provider!r}")
    try:
        return await adapter(lead, settings, client)
    except httpx.TimeoutException as exc:
        raise CrmTransientError(f"{settings.provider} timeout: {exc}") from exc
    except httpx.TransportError as exc:
        raise CrmTransientError(f"{settings.provider} transport error: {exc}") from exc
