from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage

from src.core.config import Config
from src.core.database import Database
from src.core.metrics import Metrics
from src.core.storage import Storage


class AppState:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.db = Database(config)
        self.storage = Storage(self.db)
        self.metrics = Metrics()
        self.bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
        self.dp = Dispatcher()
        self.fsm_storage = RedisStorage.from_url(config.redis_url)


def create_app(config: Config | None = None) -> AppState:
    cfg = config or Config.from_env()
    return AppState(cfg)
