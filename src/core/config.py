from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    bot_token: str = ""
    admin_password: str = ""
    admin_ids: list[int] = None  # type: ignore[assignment]
    redis_url: str = "redis://localhost:6379/0"
    db_path: str = "data/leads.db"
    webhook_url: str = ""
    webhook_secret: str = ""
    log_level: str = "INFO"
    sentry_dsn: str = ""
    metrics_port: int = 8082
    escalation_minutes: int = 15

    @classmethod
    def from_env(cls) -> Config:
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        admin_ids = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
        return cls(
            bot_token=os.getenv("BOT_TOKEN", ""),
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
        )

    def validate(self) -> None:
        if not self.bot_token:
            raise RuntimeError("BOT_TOKEN is not set")
        if not self.admin_password:
            raise RuntimeError("ADMIN_PASSWORD is not set")
        if not self.admin_ids:
            raise RuntimeError("ADMIN_IDS is not set")


@dataclass
class State:
    config: Config = field(default_factory=Config.from_env)
