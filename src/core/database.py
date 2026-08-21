from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import Config


class Database:
    def __init__(self, config: Config) -> None:
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{config.db_path}",
            echo=False,
        )
        self._session_factory = sessionmaker(  # type: ignore[call-overload]
    self._engine, class_=AsyncSession, expire_on_commit=False
)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session, session.begin():
            yield session

    async def close(self) -> None:
        await self._engine.dispose()
