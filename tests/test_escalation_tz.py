"""Сроки эскалации обязаны пережить наивный created_at из SQLite (дефект F2).

Факт прода: `created_at` — TEXT DEFAULT (datetime('now')), то есть наивная
UTC-строка «2026-10-21 09:00:00» без метки пояса. Сравнение now(UTC) − naive
бросало TypeError, который внешний `except Exception: pass` глотал целиком:
эскалация вставала молча. Существовавший тест это не ловил — его фикстура
была aware ("…T00:00:00Z"), то есть не похожа на данные из БД.

Здесь обе формы обязаны работать, включая просроченную заявку, чей срок
записан в другом поясе (тот же момент времени, другая запись), и не
просроченная заявка не должна эскалироваться.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.escalation import scheduler as esc_scheduler
from src.escalation.scheduler import _aware_utc
from src.leadgen import service as lead_service

OVERDUE_MIN = 16  # порог эскалации в тестах — 15 минут


def _lead(created_at: str) -> dict:
    return {"id": 5, "client_user_id": 42, "created_at": created_at, "status": "new"}


async def _one_cycle(lead: dict) -> AsyncMock:
    """Один проход escalation_loop на фикстуре заявки; возвращает escalate_lead."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    escalate = AsyncMock()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lead_service, "get_new_leads", AsyncMock(return_value=[lead]))
        mp.setattr(lead_service, "escalate_lead", escalate)
        task = asyncio.create_task(
            esc_scheduler.escalation_loop(bot, MagicMock(), escalation_minutes=OVERDUE_MIN - 1)
        )
        await asyncio.sleep(0.1)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    return escalate


def _overdue() -> datetime:
    return datetime.now(UTC) - timedelta(minutes=OVERDUE_MIN)


@pytest.mark.asyncio
async def test_naive_sqlite_created_at_escalates() -> None:
    """Прод-формат: наивная строка datetime('now') — основной путь БД."""
    created = _overdue().strftime("%Y-%m-%d %H:%M:%S")
    assert _aware_utc(created) is not None  # наивная строка обязана разбираться
    escalate = await _one_cycle(_lead(created))
    assert escalate.await_count >= 1, "наивный created_at из SQLite не эскалировался"


@pytest.mark.asyncio
async def test_aware_z_created_at_escalates() -> None:
    created = _overdue().strftime("%Y-%m-%dT%H:%M:%SZ")
    escalate = await _one_cycle(_lead(created))
    assert escalate.await_count >= 1, "aware-строка с Z не эскалировалась"


@pytest.mark.asyncio
async def test_aware_offset_created_at_escalates() -> None:
    """Тот же просроченный момент, записанный в поясе +03:00."""
    created = _overdue().astimezone(timezone(timedelta(hours=3))).isoformat()
    escalate = await _one_cycle(_lead(created))
    assert escalate.await_count >= 1, "aware-строка со смещением +03:00 не эскалировалась"


@pytest.mark.asyncio
async def test_not_overdue_is_not_escalated() -> None:
    created = (datetime.now(UTC) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    escalate = await _one_cycle(_lead(created))
    assert escalate.await_count == 0, "заявка в срок эскалировалась зря"


@pytest.mark.asyncio
async def test_unparseable_created_at_is_skipped() -> None:
    escalate = await _one_cycle(_lead("не дата"))
    assert escalate.await_count == 0


def test_aware_utc_normalization() -> None:
    naive = datetime(2026, 10, 21, 9, 0, 0)
    got = _aware_utc(naive.isoformat())
    assert got is not None and got.tzinfo is not None
    assert got.utcoffset() == timedelta(0)  # наивное в БД — это UTC
    aware_z = _aware_utc("2026-10-21T09:00:00Z")
    assert aware_z == got
    aware_off = _aware_utc("2026-10-21T12:00:00+03:00")
    assert aware_off is not None and aware_off.astimezone(UTC) == got
    assert _aware_utc("мусор") is None
