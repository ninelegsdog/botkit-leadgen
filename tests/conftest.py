"""Shared fixtures for leadgen tests + testcontainers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from src.core.config import Config
from src.core.database import Database
from src.core.migrations import migrate


@pytest.fixture(scope="session")
def postgres_container() -> Any:
    """PostgreSQL 16 container for integration tests."""
    container = PostgresContainer("postgres:16-alpine")
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def redis_container() -> Any:
    """Redis 7 container for integration tests."""
    container = RedisContainer("redis:7-alpine")
    container.start()
    yield container
    container.stop()


@pytest.fixture
def postgres_url(postgres_container) -> str:
    """Get PostgreSQL connection URL."""
    return postgres_container.get_connection_url().replace("postgresql+psycopg2", "postgresql+asyncpg")


@pytest.fixture
def redis_url(redis_container) -> str:
    """Get Redis connection URL."""
    return f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"


@pytest.fixture
async def db_engine(postgres_url: str):
    """Create async SQLAlchemy engine."""
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(postgres_url, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """Create database session for tests."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    async_session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.fixture
async def redis_client(redis_url: str):
    """Create Redis client for tests."""
    import redis.asyncio as redis
    client = redis.from_url(redis_url, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
async def db():
    config = Config(db_path=":memory:")
    database = Database(config)
    await migrate(database)
    yield database
    await database.close()


_PAYLOADS_DIR = Path(__file__).parent / "fixtures" / "payloads"


@pytest.fixture
def load_payload() -> Any:
    """Load a JSON Telegram-update fixture from tests/fixtures/payloads/."""

    def _load(name: str) -> dict[str, Any]:
        return json.loads((_PAYLOADS_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    return _load


def pytest_collection_modifyitems(config: Any, items: Any) -> None:
    """Tag offline tests as no_req; skip real Telegram (req) tests unless RUN_TELEGRAM_E2E=1."""
    for item in items:
        path = getattr(item, "path", None)
        fname = Path(path).name if path else ""
        is_req_file = fname == "test_e2e.py"
        if "integration" in item.keywords:
            continue
        if "req" in item.keywords or is_req_file:
            if os.getenv("RUN_TELEGRAM_E2E") != "1":
                item.add_marker(
                    pytest.mark.skip(reason="set RUN_TELEGRAM_E2E=1 to run real Telegram tests")
                )
        elif "no_req" not in item.keywords:
            item.add_marker(pytest.mark.no_req)


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run integration tests with testcontainers",
    )
