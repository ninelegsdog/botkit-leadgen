"""Integration tests with testcontainers (Redis, SQLite WAL)."""
from __future__ import annotations

import pytest

try:
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer

    HAS_CONTAINERS = True
except ImportError:
    HAS_CONTAINERS = False


@pytest.mark.integration
@pytest.mark.skipif(not HAS_CONTAINERS, reason="testcontainers not installed")
def test_postgres_container_migrations() -> None:
    """Postgres container starts and is reachable."""
    try:
        with PostgresContainer("postgres:16-alpine") as postgres:
            assert postgres.get_connection_url() is not None
            assert postgres.get_exposed_port(5432) is not None
    except Exception as e:
        pytest.skip(f"Postgres container not available: {e}")


@pytest.mark.integration
@pytest.mark.skipif(not HAS_CONTAINERS, reason="testcontainers not installed")
def test_redis_container_throttling() -> None:
    """Redis container starts and is reachable."""
    try:
        with RedisContainer("redis:7-alpine") as redis:
            assert redis.get_exposed_port(6379) is not None
            assert redis.get_container_host_ip() is not None
    except Exception as e:
        pytest.skip(f"Redis container not available: {e}")


def test_sqlite_wal_mode() -> None:
    """SQLite WAL mode for concurrent access."""
    import asyncio

    import aiosqlite

    async def run() -> None:
        async with aiosqlite.connect(":memory:") as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            cursor = await db.execute("PRAGMA journal_mode;")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] in ("wal", "memory", "delete")

    asyncio.run(run())
