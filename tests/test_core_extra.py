from __future__ import annotations

import asyncio
import time
from datetime import datetime
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from src.core import config as config_mod
from src.core.bot_factory import AppState, create_app
from src.core.errors import (
    RetryMiddleware,
    default_error_handler,
    register_error_handler,
)
from src.core.fsm import AdminAuth, LeadForm
from src.core.metrics import (
    Metrics,
    UPDATES_TOTAL,
    UpdatesMiddleware,
    create_metrics_app,
    health,
    metrics,
    start_metrics_server,
)
from src.core.nav import admin_menu, main_menu, manager_menu
from src.core.sentry import init_sentry
from src.core import storage as storage_mod
from src.core import throttling
from src.core.webhook import create_app as create_webhook_app
from src.core.auth import AuthMiddleware
from src.app import register_routers
from src.escalation import scheduler as esc_scheduler
from src.leadgen import service as lead_service
from src.leadgen.handlers import create_leadgen_router
from src.admin.handlers import create_admin_router
from src.core.ui import escape, lead_card, lead_summary, mask_phone


def _fake_db() -> tuple[MagicMock, MagicMock]:
    sess = MagicMock()
    sess.execute = AsyncMock(
        return_value=MagicMock(
            fetchone=MagicMock(return_value=(1,)),
            mappings=MagicMock(
                all=MagicMock(return_value=[]), fetchone=MagicMock(return_value=None)
            ),
            rowcount=1,
        )
    )
    cm = AsyncMock()
    cm.__aenter__.return_value = sess
    cm.__aexit__.return_value = False
    db = MagicMock()
    db.session = MagicMock(return_value=cm)
    db.transaction = MagicMock(return_value=cm)
    return db, sess


def _make_state() -> AppState:
    with patch("src.core.bot_factory.RedisStorage.from_url", return_value=MemoryStorage()):
        return create_app(
            config_mod.Config(
                bot_token="123456789:AAfake",
                admin_password="secret",
                admin_ids=[1],
                redis_url="redis://localhost:6379/0",
                metrics_port=8082,
            )
        )


# --- config ---
def test_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("ADMIN_PASSWORD", "p")
    monkeypatch.setenv("ADMIN_IDS", "1,2")
    monkeypatch.setenv("REDIS_URL", "redis://r")
    monkeypatch.setenv("METRICS_PORT", "8082")
    c = config_mod.Config.from_env()
    assert c.bot_token == "x"
    assert c.admin_ids == [1, 2]
    assert c.metrics_port == 8082


def test_config_validate_raises(monkeypatch) -> None:
    c = config_mod.Config(bot_token="", admin_password="", admin_ids=[])
    with pytest.raises(RuntimeError):
        c.validate()


# --- bot_factory / app ---
def test_create_app_builds_state() -> None:
    with patch("src.core.bot_factory.RedisStorage.from_url", return_value=MemoryStorage()):
        state = create_app(config_mod.Config(bot_token="123456789:AAfake"))
    assert isinstance(state.bot, Bot)
    assert state.dp is not None


def test_register_routers() -> None:
    state = _make_state()
    register_routers(state)
    assert len(state.dp.sub_routers) >= 1


# --- errors ---
@pytest.mark.asyncio
async def test_retry_middleware_retries() -> None:
    from aiogram.exceptions import TelegramRetryAfter

    calls = {"n": 0}

    async def handler(event, data):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TelegramRetryAfter(None, "r", 0)
        return "ok"

    mw = RetryMiddleware(max_retries=3, delay=0)
    assert await mw(handler, MagicMock(), {}) == "ok"


@pytest.mark.asyncio
async def test_retry_middleware_network() -> None:
    from aiogram.exceptions import TelegramNetworkError

    async def handler(event, data):
        raise TelegramNetworkError(None, "n")

    mw = RetryMiddleware(max_retries=2, delay=0)
    with pytest.raises(TelegramNetworkError):
        await mw(handler, MagicMock(), {})


@pytest.mark.asyncio
async def test_default_error_handler_retry_after() -> None:
    from aiogram.exceptions import TelegramRetryAfter

    await default_error_handler(MagicMock(), TelegramRetryAfter(None, "r", 0))


@pytest.mark.asyncio
async def test_default_error_handler_network() -> None:
    from aiogram.exceptions import TelegramNetworkError

    await default_error_handler(MagicMock(), TelegramNetworkError(None, "n"))


@pytest.mark.asyncio
async def test_register_error_handler() -> None:
    fake_dp = SimpleNamespace(error=MagicMock(return_value=MagicMock()))
    register_error_handler(fake_dp)
    assert fake_dp.error.called


# --- storage ---
@pytest.mark.asyncio
async def test_storage_get_setting() -> None:
    db, sess = _fake_db()
    sess.execute.return_value.fetchone = MagicMock(return_value=("1",))
    assert await storage_mod.Storage(db).get_setting("k") == "1"


@pytest.mark.asyncio
async def test_storage_set_setting() -> None:
    db, sess = _fake_db()
    await storage_mod.Storage(db).set_setting("k", "v")
    assert sess.execute.called


# --- throttling ---
@pytest.mark.asyncio
async def test_throttle_passes_first() -> None:
    mw = throttling.ThrottlingMiddleware(min_interval=2.0)
    ev = Message(
        message_id=1,
        chat=Chat(id=1, type="private"),
        date=datetime.now(),
        from_user=User(id=1, is_bot=False, first_name="U"),
        text="x",
    )
    assert await mw(AsyncMock(return_value="ok"), ev, {}) == "ok"


@pytest.mark.asyncio
async def test_throttle_blocks_recent() -> None:
    mw = throttling.ThrottlingMiddleware(min_interval=2.0)
    ev = Message(
        message_id=1,
        chat=Chat(id=1, type="private"),
        date=datetime.now(),
        from_user=User(id=1, is_bot=False, first_name="U"),
        text="x",
    )
    assert await mw(AsyncMock(return_value="ok"), ev, {}) == "ok"
    mw._last_message[1] = time.time()
    assert await mw(AsyncMock(return_value="ok"), ev, {}) is None


# --- webhook ---
def test_create_webhook_app() -> None:
    state = _make_state()
    app = create_webhook_app(state)
    paths = [r.resource.canonical for r in app.router.routes() if r.resource]
    assert "/health" in paths
    assert "/metrics" in paths


# --- metrics ---
def test_metrics_inc() -> None:
    m = Metrics()
    m.inc_messages()
    m.inc_leads()
    m.inc_leads_taken()
    m.inc_errors()
    assert m.messages_processed == 1
    assert m.leads_created == 1
    assert m.leads_taken == 1
    assert m.errors == 1
    assert m.uptime_seconds() >= 0


@pytest.mark.asyncio
async def test_updates_middleware() -> None:
    mw = UpdatesMiddleware()
    ev = SimpleNamespace(message=SimpleNamespace(text="hi"))
    ev_type = type(ev).__name__.lower()
    before = UPDATES_TOTAL.labels(type=ev_type)._value.get()
    assert await mw(AsyncMock(return_value="x"), ev, {}) == "x"
    after = UPDATES_TOTAL.labels(type=ev_type)._value.get()
    assert after == before + 1


def test_create_metrics_app() -> None:
    app = create_metrics_app()
    paths = [r.resource.canonical for r in app.router.routes() if r.resource]
    assert "/health" in paths
    assert "/metrics" in paths


@pytest.mark.asyncio
async def test_start_metrics_server() -> None:
    runner = await start_metrics_server(18099)
    await runner.cleanup()


# --- sentry ---
def test_init_sentry_no_dsn() -> None:
    init_sentry(None)


def test_init_sentry_missing_sdk() -> None:
    with patch.dict("sys.modules", {"sentry_sdk": None}):
        init_sentry("https://abc@sentry.io/1")


def test_init_sentry_with_sdk() -> None:
    init_sentry("https://abc@sentry.io/1")


# --- fsm / nav / ui / auth ---
def test_fsm_states() -> None:
    assert LeadForm.choosing_service is not None
    assert AdminAuth.waiting_password is not None


def test_nav_menus() -> None:
    assert main_menu().keyboard
    assert manager_menu().keyboard
    assert admin_menu().keyboard


def test_ui_helpers() -> None:
    assert escape(None) == ""
    assert escape("<b>") == "&lt;b&gt;"
    assert mask_phone("+79991234567") == "+799(***)67"
    lead = {"id": 1, "client_name": "Иван", "client_phone": "+79991234567",
            "field_values": '{"Интерес": "SEO"}'}
    card = lead_card(lead)
    assert "Иван" in card and "SEO" in card
    summ = lead_summary(lead)
    assert "Иван" in summ


@pytest.mark.asyncio
async def test_auth_middleware_sets_db() -> None:
    mw = AuthMiddleware(MagicMock())
    data: dict = {}
    assert await mw(AsyncMock(return_value="ok"), MagicMock(), data) == "ok"
    assert data["db"] is not None


# --- escalation scheduler ---
@pytest.mark.asyncio
async def test_escalation_loop_escalates() -> None:
    bot = Bot(token="123456789:AAfake")
    with patch.object(bot.session, "make_request", new_callable=AsyncMock):
        db, _ = _fake_db()
        lead = {"id": 5, "client_user_id": 42, "created_at": "2020-01-01T00:00:00Z"}
        with patch.object(lead_service, "get_new_leads", new=AsyncMock(return_value=[lead])), \
             patch.object(lead_service, "escalate_lead", new=AsyncMock()):
            task = asyncio.create_task(
                esc_scheduler.escalation_loop(bot, db, escalation_minutes=1)
            )
            await asyncio.sleep(0.05)
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            assert lead_service.escalate_lead.await_count >= 1


# --- handlers ---
@pytest.mark.asyncio
async def test_leadgen_start() -> None:
    state = _make_state()
    state.dp.include_router(create_leadgen_router(state))
    bot = state.bot
    with patch.object(bot.session, "make_request", new_callable=AsyncMock) as mr:
        msg = Message(
            message_id=1,
            date=MagicMock(),
            chat=Chat(id=1, type="private"),
            from_user=User(id=1, is_bot=False, first_name="U"),
            text="/start",
        )
        await state.dp.feed_update(bot, Update(update_id=1, message=msg))
    assert mr.await_count >= 1


@pytest.mark.asyncio
async def test_leadgen_contacts() -> None:
    state = _make_state()
    state.dp.include_router(create_leadgen_router(state))
    bot = state.bot
    with patch.object(bot.session, "make_request", new_callable=AsyncMock) as mr:
        msg = Message(
            message_id=2,
            date=MagicMock(),
            chat=Chat(id=1, type="private"),
            from_user=User(id=1, is_bot=False, first_name="U"),
            text="📞 Контакты",
        )
        await state.dp.feed_update(bot, Update(update_id=2, message=msg))
    assert mr.await_count >= 1


@pytest.mark.asyncio
async def test_admin_auth_flow() -> None:
    state = _make_state()
    state.dp.include_router(create_admin_router(state))
    bot = state.bot
    with patch.object(bot.session, "make_request", new_callable=AsyncMock) as mr:
        for text in ["/admin", "secret"]:
            msg = Message(
                message_id=3,
                date=MagicMock(),
                chat=Chat(id=1, type="private"),
                from_user=User(id=1, is_bot=False, first_name="U"),
                text=text,
            )
            await state.dp.feed_update(bot, Update(update_id=3, message=msg))
    assert mr.await_count >= 1


@pytest.mark.asyncio
async def test_admin_stats_not_admin() -> None:
    state = _make_state()
    state.dp.include_router(create_admin_router(state))
    bot = state.bot
    with patch.object(bot.session, "make_request", new_callable=AsyncMock) as mr:
        msg = Message(
            message_id=4,
            date=MagicMock(),
            chat=Chat(id=1, type="private"),
            from_user=User(id=7, is_bot=False, first_name="X"),
            text="📊 Статистика",
        )
        await state.dp.feed_update(bot, Update(update_id=4, message=msg))
    assert mr.await_count == 0
