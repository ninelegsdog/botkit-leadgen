from __future__ import annotations

import pytest

from src.core.config import Config
from src.core.ui import escape, mask_phone


@pytest.mark.asyncio
async def test_config_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
    config = Config.from_env()
    assert config.bot_token == "test_token"


def test_escape():
    assert escape("<script>") == "&lt;script&gt;"
    assert escape("hello") == "hello"
    assert escape(None) == ""


def test_mask_phone():
    assert mask_phone("+71234567890") == "+712(***)90"
    assert mask_phone(None) == "***"
