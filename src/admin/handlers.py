from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.core.auth import AdminGate
from src.core.bot_factory import AppState
from src.core.fsm import AdminAuth
from src.core.nav import admin_menu, main_menu
from src.leadgen import service


def create_admin_router(app_state: AppState) -> Router:
    router = Router()
    db = app_state.db

    # The password check below compared in constant time but had no attempt
    # limit, so the admin surface allowed unlimited guesses. AdminGate adds the
    # throttle; is_throttled is checked BEFORE authorize so guesses are refused
    # for the whole window.
    # The gate tracks only password-authorised users here; configured admins are
    # read dynamically below, so both sources agree with the running config.
    gate = AdminGate(app_state.config.admin_password)

    def is_admin(user_id: int) -> bool:
        # Config admins, plus anyone the gate has authorised.
        return user_id in (app_state.config.admin_ids or []) or gate.is_admin(user_id)

    @router.message(Command("admin"))
    async def cmd_admin(message: Message, state: FSMContext) -> None:
        await state.set_state(AdminAuth.waiting_password)
        await message.answer("🔑 Введите пароль:")

    @router.message(AdminAuth.waiting_password)
    async def check_password(message: Message, state: FSMContext) -> None:
        user_id = message.from_user.id  # type: ignore[union-attr]
        if gate.is_throttled(user_id):
            await state.clear()
            await message.answer(
                "⏳ Слишко много попыток. "
                "Попробуйте через 5 минут.",
                reply_markup=main_menu(),
            )
            return
        if gate.authorize(user_id, message.text or ""):
            await state.clear()
            await message.answer("✅ Добро пожаловать!", reply_markup=admin_menu())
        else:
            await state.clear()
            await message.answer("❌ Неверный пароль.", reply_markup=main_menu())

    @router.message(F.text == "👥 Менеджеры")
    async def list_managers(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        managers = await service.get_active_managers(db)
        if not managers:
            await message.answer("Менеджеров нет. Добавьте первого.")
            return
        text = "👥 Менеджеры:\n" + "\n".join(f"• {m['name']} (ID: {m['user_id']})" for m in managers)
        await message.answer(text)

    @router.message(F.text == "📊 Статистика")
    async def admin_stats(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        day = await service.get_lead_stats(db, "day")
        week = await service.get_lead_stats(db, "week")
        await message.answer(
            f"📊 Статистика:\n\nСегодня:\n  Новых: {day.get('new', 0)}\n"
            f"  В работе: {day.get('taken', 0)}\n  Закрытых: {day.get('closed', 0)}\n\n"
            f"За неделю:\n  Новых: {week.get('new', 0)}\n"
            f"  В работе: {week.get('taken', 0)}\n  Закрытых: {week.get('closed', 0)}"
        )

    @router.message(F.text == "⚙️ Настройки")
    async def admin_settings(message: Message) -> None:
        if not is_admin(message.from_user.id):  # type: ignore[union-attr]
            return
        await message.answer("⚙️ Настройки:\n• Эскалация: 15 мин\n• Приветствие: default")

    return router
