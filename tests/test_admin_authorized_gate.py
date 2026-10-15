"""``is_admin`` must accept a user who proved the admin password.

``is_admin`` read only ``config.admin_ids``, so a user who authenticated through
``/admin`` was shown the admin menu and then refused by every panel button. The
comment claimed the gate's authorised users were included; the code did not. This
drives the handler the router actually registered, so the guard is exercised.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.admin.handlers import create_admin_router
from src.core.config import Config


def _state(admin_ids: list[int]) -> Any:
    cfg = Config(bot_token="123456789:AAfake", admin_password="secret", admin_ids=admin_ids)
    return SimpleNamespace(config=cfg, db=MagicMock())


def _router_handler(router: Any, attr: str, name: str) -> Any:
    for h in getattr(router, attr).handlers:
        if getattr(h.callback, "__name__", None) == name:
            return h.callback
    raise AssertionError(f"{attr} handler {name!r} not found")


def _message(uid: int, text: str = "") -> Any:
    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = uid
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _fsm() -> Any:
    return MagicMock(clear=AsyncMock())


@pytest.mark.asyncio
async def test_config_admin_reads_panel() -> None:
    router = create_admin_router(_state([1]))
    panel = _router_handler(router, "message", 'admin_settings')
    msg = _message(1)
    await panel(msg)
    msg.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_admin_cannot_read_panel() -> None:
    router = create_admin_router(_state([1]))
    panel = _router_handler(router, "message", 'admin_settings')
    msg = _message(999)
    await panel(msg)
    msg.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_authorised_user_reads_panel() -> None:
    router = create_admin_router(_state([1]))
    check_password = _router_handler(router, "message", "check_password")
    uid = 2
    await check_password(_message(uid, "secret"), _fsm())

    panel = _router_handler(router, "message", 'admin_settings')
    msg = _message(uid)
    await panel(msg)
    msg.answer.assert_awaited_once()
