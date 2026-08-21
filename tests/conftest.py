from __future__ import annotations

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
