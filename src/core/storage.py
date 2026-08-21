from __future__ import annotations

from sqlalchemy import text

from src.core.database import Database


class Storage:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_setting(self, key: str) -> str | None:
        async with self._db.session() as session:
            result = await session.execute(text("SELECT value FROM settings WHERE key = :k"), {"k": key})
            row = result.fetchone()
            return str(row[0]) if row else None

    async def set_setting(self, key: str, value: str) -> None:
        async with self._db.transaction() as session:
            await session.execute(
                text("INSERT OR REPLACE INTO settings (key, value) VALUES (:k, :v)"), {"k": key, "v": value}
            )
