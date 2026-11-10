"""CRM configuration validation."""

from __future__ import annotations

import pytest

from src.core.config import Config


def test_validate_crm_rejects_unknown_provider() -> None:
    cfg = Config(crm_provider="salesforce")
    with pytest.raises(RuntimeError, match="CRM_PROVIDER"):
        cfg.validate_crm()


def test_validate_crm_generic_requires_url() -> None:
    cfg = Config(crm_provider="generic")
    with pytest.raises(RuntimeError, match="CRM_WEBHOOK_URL"):
        cfg.validate_crm()


def test_validate_crm_bitrix_requires_credentials() -> None:
    cfg = Config(crm_provider="bitrix24")
    with pytest.raises(RuntimeError, match="CRM_BASE_URL"):
        cfg.validate_crm()


def test_validate_crm_amocrm_requires_credentials() -> None:
    cfg = Config(crm_provider="amocrm")
    with pytest.raises(RuntimeError, match="CRM_BASE_URL"):
        cfg.validate_crm()


def test_validate_crm_off_is_valid() -> None:
    Config(crm_provider="off").validate_crm()


def test_backoff_default_matches_original_schedule() -> None:
    cfg = Config()
    assert cfg.crm_backoff_seconds == (60, 300, 1800, 7200, 21600, 86400)


def test_backoff_env_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRM_BACKOFF_SECONDS", "1, 2,3")
    cfg = Config.from_env()
    assert cfg.crm_backoff_seconds == (1, 2, 3)


def test_backoff_env_rejects_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRM_BACKOFF_SECONDS", "1,abc")
    with pytest.raises(RuntimeError, match="CRM_BACKOFF_SECONDS"):
        Config.from_env()


def test_backoff_env_rejects_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRM_BACKOFF_SECONDS", "   ")
    with pytest.raises(RuntimeError, match="CRM_BACKOFF_SECONDS"):
        Config.from_env()


def test_validate_crm_amocrm_requires_refresh_token_fields() -> None:
    cfg = Config(
        crm_provider="amocrm",
        crm_base_url="https://example.amocrm.ru",
        crm_access_token="token",
        crm_amocrm_refresh_token="",
        crm_amocrm_client_id="",
        crm_amocrm_client_secret="",
    )
    with pytest.raises(RuntimeError, match="CRM_AMOCRM_REFRESH_TOKEN"):
        cfg.validate_crm()


def test_validate_crm_amocrm_with_refresh_fields_is_valid() -> None:
    cfg = Config(
        crm_provider="amocrm",
        crm_base_url="https://example.amocrm.ru",
        crm_access_token="token",
        crm_amocrm_refresh_token="refresh",
        crm_amocrm_client_id="client-id",
        crm_amocrm_client_secret="client-secret",
    )
    cfg.validate_crm()  # should not raise
