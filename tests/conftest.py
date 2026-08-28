from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.core.config import Config
from src.core.database import Database
from src.core.migrations import migrate


@pytest.fixture
async def db():
    config = Config(db_path=":memory:")
    database = Database(config)
    await migrate(database)
    yield database
    await database.close()


_PAYLOADS_DIR = Path(__file__).parent / "fixtures" / "payloads"


@pytest.fixture
def load_payload():
    """Load a JSON Telegram-update fixture from tests/fixtures/payloads/."""

    def _load(name: str) -> dict:
        return json.loads((_PAYLOADS_DIR / name).read_text(encoding="utf-8"))

    return _load


def pytest_collection_modifyitems(config, items):
    """Tag offline tests as no_req; skip real Telegram (req) tests unless RUN_TELEGRAM_E2E=1."""
    for item in items:
        fname = Path(item.fspath).name if getattr(item, "fspath", None) else ""
        is_req_file = fname == "test_e2e.py"
        if "req" in item.keywords or is_req_file:
            if os.getenv("RUN_TELEGRAM_E2E") != "1":
                item.add_marker(
                    pytest.mark.skip(reason="set RUN_TELEGRAM_E2E=1 to run real Telegram tests")
                )
        elif "no_req" not in item.keywords:
            item.add_marker(pytest.mark.no_req)
