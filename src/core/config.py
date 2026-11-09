from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    bot_token: str = ""
    admin_password: str = ""
    admin_ids: list[int] = None  # type: ignore[assignment]
    redis_url: str = "redis://127.0.0.1:6380/1"
    db_path: str = "data/leads.db"
    webhook_url: str = ""
    webhook_secret: str = ""
    log_level: str = "INFO"
    sentry_dsn: str = ""
    metrics_port: int = 8082
    escalation_minutes: int = 15
    crm_provider: str = "off"
    crm_webhook_url: str = ""
    crm_webhook_secret: str = ""
    crm_base_url: str = ""
    crm_access_token: str = ""
    crm_bitrix_user_id: str = ""
    crm_bitrix_webhook_token: str = ""
    crm_timeout_seconds: float = 10.0
    crm_poll_seconds: float = 15.0
    crm_max_attempts: int = 6
    crm_backoff_seconds: tuple[int, ...] = (60, 300, 1800, 7200, 21600, 86400)

    @classmethod
    def from_env(cls) -> Config:
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        admin_ids: list[int] = []
        for token in admin_ids_str.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                admin_ids.append(int(token))
            except ValueError:
                logging.warning("Invalid admin id ignored: %r", token)
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            admin_password=os.getenv("ADMIN_PASSWORD", ""),
            admin_ids=admin_ids,
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            db_path=os.getenv("DB_PATH", "data/leads.db"),
            webhook_url=os.getenv("WEBHOOK_URL", ""),
            webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            sentry_dsn=os.getenv("SENTRY_DSN", ""),
            metrics_port=int(os.getenv("METRICS_PORT", "8082")),
            escalation_minutes=int(os.getenv("ESCALATION_MINUTES", "15")),
            crm_provider=os.getenv("CRM_PROVIDER", "off").strip().lower(),
            crm_webhook_url=os.getenv("CRM_WEBHOOK_URL", ""),
            crm_webhook_secret=os.getenv("CRM_WEBHOOK_SECRET", ""),
            crm_base_url=os.getenv("CRM_BASE_URL", "").rstrip("/"),
            crm_access_token=os.getenv("CRM_ACCESS_TOKEN", ""),
            crm_bitrix_user_id=os.getenv("CRM_BITRIX_USER_ID", ""),
            crm_bitrix_webhook_token=os.getenv("CRM_BITRIX_WEBHOOK_TOKEN", ""),
            crm_timeout_seconds=float(os.getenv("CRM_TIMEOUT_SECONDS", "10")),
            crm_poll_seconds=float(os.getenv("CRM_POLL_SECONDS", "15")),
            crm_max_attempts=int(os.getenv("CRM_MAX_ATTEMPTS", "6")),
            crm_backoff_seconds=_parse_backoff(os.getenv("CRM_BACKOFF_SECONDS", "60,300,1800,7200,21600,86400")),
        )

    def validate(self) -> None:
        if not self.bot_token:
            raise RuntimeError("BOT_TOKEN is not set")
        if not self.admin_password:
            raise RuntimeError("ADMIN_PASSWORD is not set")
        if not self.admin_ids:
            raise RuntimeError("ADMIN_IDS is not set")
        self.validate_crm()

    def validate_crm(self) -> None:
        """Fail fast on an explicit but incomplete CRM configuration.

        Provider "off" is the default, so a missing block never breaks a deploy.
        Once a provider is named, its credentials are mandatory: a bot that
        silently drops every lead is worse than one that refuses to start.
        """
        allowed = {"off", "generic", "bitrix24", "amocrm"}
        if self.crm_provider not in allowed:
            raise RuntimeError(
                f"CRM_PROVIDER must be one of {sorted(allowed)}, got {self.crm_provider!r}"
            )
        if self.crm_provider == "generic" and not self.crm_webhook_url:
            raise RuntimeError("CRM_WEBHOOK_URL is required for CRM_PROVIDER=generic")
        if self.crm_provider == "bitrix24":
            missing = [
                name
                for name, value in (
                    ("CRM_BASE_URL", self.crm_base_url),
                    ("CRM_BITRIX_USER_ID", self.crm_bitrix_user_id),
                    ("CRM_BITRIX_WEBHOOK_TOKEN", self.crm_bitrix_webhook_token),
                )
                if not value
            ]
            if missing:
                raise RuntimeError(f"missing for CRM_PROVIDER=bitrix24: {', '.join(missing)}")
        if self.crm_provider == "amocrm":
            missing = [
                name
                for name, value in (
                    ("CRM_BASE_URL", self.crm_base_url),
                    ("CRM_ACCESS_TOKEN", self.crm_access_token),
                )
                if not value
            ]
            if missing:
                raise RuntimeError(f"missing for CRM_PROVIDER=amocrm: {', '.join(missing)}")


@dataclass
class State:
    config: Config = field(default_factory=Config.from_env)


def _parse_backoff(raw: str) -> tuple[int, ...]:
    values: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            value = int(token)
        except ValueError as exc:
            raise RuntimeError(f"CRM_BACKOFF_SECONDS contains a non-integer value: {token!r}") from exc
        if value < 0:
            raise RuntimeError(f"CRM_BACKOFF_SECONDS values must be >= 0, got {value}")
        values.append(value)
    if not values:
        raise RuntimeError("CRM_BACKOFF_SECONDS must not be empty")
    return tuple(values)
