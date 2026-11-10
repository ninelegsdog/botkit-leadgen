"""``is_admin`` must accept a user who proved the admin password.

``is_admin`` read only ``config.admin_ids``, so a user who authenticated through
``/admin`` was shown the admin menu and then refused by every panel button. The
comment claimed the gate's authorised users were included; the code did not. This
drives the handler the router actually registered, so the guard is exercised.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.admin.handlers import create_admin_router
from src.core.config import Config
from src.core.nav import admin_menu, main_menu


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
    fsm = MagicMock()
    fsm.set_state = AsyncMock()
    fsm.clear = AsyncMock()
    return fsm


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


@pytest.mark.asyncio
async def test_cmd_admin_sets_password_state() -> None:
    router = create_admin_router(_state([1]))
    handler = _router_handler(router, "message", "cmd_admin")
    msg = _message(1)
    await handler(msg, _fsm())
    msg.answer.assert_awaited_once_with("🔑 Введите пароль:")


@pytest.mark.asyncio
async def test_check_password_wrong() -> None:
    router = create_admin_router(_state([1]))
    handler = _router_handler(router, "message", "check_password")
    msg = _message(1, "wrong")
    await handler(msg, _fsm())
    msg.answer.assert_awaited_once()
    args = msg.answer.call_args[0][0]
    assert "Неверный пароль" in args


@pytest.mark.asyncio
async def test_list_managers_non_admin() -> None:
    router = create_admin_router(_state([1]))
    handler = _router_handler(router, "message", "list_managers")
    msg = _message(999, "👥 Менеджеры")
    await handler(msg)
    msg.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_managers_admin_empty() -> None:
    from src.leadgen import service as lead_service
    router = create_admin_router(_state([1]))
    handler = _router_handler(router, "message", "list_managers")
    msg = _message(1, "👥 Менеджеры")
    lead_service.get_active_managers = AsyncMock(return_value=[])  # type: ignore[assignment]
    await handler(msg)
    msg.answer.assert_awaited_once_with("Менеджеров нет. Добавьте первого.")


@pytest.mark.asyncio
async def test_list_managers_admin_with_managers() -> None:
    from src.leadgen import service as lead_service
    router = create_admin_router(_state([1]))
    handler = _router_handler(router, "message", "list_managers")
    msg = _message(1, "👥 Менеджеры")
    lead_service.get_active_managers = AsyncMock(
        return_value=[{"name": "Ivan", "user_id": 42}]
    )
    await handler(msg)
    msg.answer.assert_awaited_once()
    args = msg.answer.call_args[0][0]
    assert "Менеджеры" in args
    assert "Ivan" in args


@pytest.mark.asyncio
async def test_admin_stats_non_admin() -> None:
    router = create_admin_router(_state([1]))
    handler = _router_handler(router, "message", "admin_stats")
    msg = _message(999, "📊 Статистика")
    await handler(msg)
    msg.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_stats_admin() -> None:
    from src.leadgen import service as lead_service
    router = create_admin_router(_state([1]))
    handler = _router_handler(router, "message", "admin_stats")
    msg = _message(1, "📊 Статистика")
    lead_service.get_lead_stats = AsyncMock(
        side_effect=lambda db, period: {"new": 1, "taken": 2, "closed": 3}
    )
    await handler(msg)
    msg.answer.assert_awaited_once()
    args = msg.answer.call_args[0][0]
    assert "Статистика" in args


@pytest.mark.asyncio
async def test_cmd_crm_test_provider_off() -> None:
    cfg = Config(
        bot_token="123456789:AAfake",
        admin_password="secret",
        admin_ids=[1],
        crm_provider="off",
    )
    state = SimpleNamespace(config=cfg, db=MagicMock())
    router = create_admin_router(state)
    handler = _router_handler(router, "message", "cmd_crm_test")
    msg = _message(1)
    await handler(msg)
    msg.answer.assert_awaited_once_with("CRM_PROVIDER=off — экспорт отключён.")


@pytest.mark.asyncio
async def test_cmd_crm_test_non_admin() -> None:
    router = create_admin_router(_state([1]))
    handler = _router_handler(router, "message", "cmd_crm_test")
    msg = _message(999)
    await handler(msg)
    msg.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_cmd_crm_dlq_non_admin() -> None:
    router = create_admin_router(_state([1]))
    handler = _router_handler(router, "message", "cmd_crm_dlq")
    msg = _message(999)
    await handler(msg)
    msg.answer.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.admin.handlers.dlq_list", new_callable=AsyncMock, return_value=[])
async def test_cmd_crm_dlq_empty(mock_dlq: Any) -> None:
    router = create_admin_router(_state([1]))
    handler = _router_handler(router, "message", "cmd_crm_dlq")
    msg = _message(1)
    await handler(msg)
    msg.answer.assert_awaited_once_with("DLQ пуста.")
