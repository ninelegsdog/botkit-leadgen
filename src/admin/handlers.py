from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.core.bot_factory import AppState
from src.core.fsm import AdminAuth
from src.core.nav import admin_menu, main_menu
from src.leadgen import service


def create_admin_router(app_state: AppState) -> Router:
    router = Router()
    db = app_state.db

    def is_admin(user_id: int) -> bool:
        return user_id in (app_state.config.admin_ids or [])

    @router.message(Command("admin"))
    async def cmd_admin(message: Message, state: FSMContext) -> None:
        await state.set_state(AdminAuth.waiting_password)
        await message.answer("🔑 Введите пароль:")

    @router.message(AdminAuth.waiting_password)
    async def check_password(message: Message, state: FSMContext) -> None:
        if message.text == app_state.config.admin_password:
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
