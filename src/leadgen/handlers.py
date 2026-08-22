from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.core.bot_factory import AppState
from src.core.fsm import LeadForm
from src.core.nav import main_menu
from src.core.ui import lead_card, lead_summary
from src.leadgen import service


def create_leadgen_router(state: AppState) -> Router:
    router = Router()
    db = state.db

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(
            "👋 Здравствуйте! Оставьте заявку, и мы свяжемся с вами.",
            reply_markup=main_menu(),
        )

    @router.message(F.text == "📝 Оставить заявку")
    async def start_form(message: Message, state_fsm: FSMContext) -> None:
        fields = await service.get_active_fields(db) if hasattr(service, "get_active_fields") else []
        if fields:
            buttons = [[{"text": f["label"], "callback_data": f"lead_svc:{f['key']}"}] for f in fields]
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=b[0]["text"], callback_data=b[0]["callback_data"])]
                    for b in buttons
                ]
            )
            await message.answer("Что вас интересует?", reply_markup=kb)
        else:
            await state_fsm.set_state(LeadForm.entering_name)
            await message.answer("Как вас зовут?")

    @router.callback_query(F.data.startswith("lead_svc:"))
    async def choose_service(callback: CallbackQuery, state_fsm: FSMContext) -> None:
        if not callback.data:
            return
        service_key = callback.data.split(":", 1)[1]
        await state_fsm.update_data(service=service_key)
        await state_fsm.set_state(LeadForm.entering_name)
        await callback.message.edit_text("Как вас зовут?")  # type: ignore
        await callback.answer()

    @router.message(LeadForm.entering_name)
    async def enter_name(message: Message, state_fsm: FSMContext) -> None:
        await state_fsm.update_data(name=message.text or "")
        await state_fsm.set_state(LeadForm.entering_phone)
        await message.answer("📱 Телефон (+71234567890):")

    @router.message(LeadForm.entering_phone)
    async def enter_phone(message: Message, state_fsm: FSMContext) -> None:
        phone = message.text or ""
        if not phone.startswith("+7") or len(phone) != 12 or not phone[2:].isdigit():
            await message.answer("❌ Неверный формат. Введите телефон: +71234567890")
            return
        await state_fsm.update_data(phone=phone)
        data = await state_fsm.get_data()
        text = lead_summary({
            "id": 0,
            "field_values": json.dumps({"Интерес": data.get("service", "")}),
            "client_name": data.get("name", ""),
            "client_phone": data.get("phone", ""),
        })
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Отправить", callback_data="lead_confirm"),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="lead_cancel"),
                ]
            ]
        )
        await state_fsm.set_state(LeadForm.confirming)
        await message.answer(f"Подтвердите заявку:\n{text}", reply_markup=kb)

    @router.callback_query(F.data == "lead_confirm", LeadForm.confirming)
    async def confirm_lead(callback: CallbackQuery, state_fsm: FSMContext) -> None:
        data = await state_fsm.get_data()
        lead_id = await service.create_lead(
            db,
            client_user_id=callback.from_user.id,
            client_name=data.get("name"),
            client_phone=data.get("phone"),
            field_values=json.dumps({"Интерес": data.get("service", "")}),
        )
        state.metrics.inc_leads()
        await state_fsm.clear()
        await callback.message.edit_text("✅ Заявка отправлена! С вами свяжутся в течение 15 минут.")  # type: ignore
        await callback.answer()

        managers = await service.get_active_managers(db)
        card = lead_card({
            "id": lead_id,
            "client_name": data.get("name"),
            "client_phone": data.get("phone"),
            "field_values": json.dumps({"Интерес": data.get("service", "")}),
        })
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Взять в работу", callback_data=f"lead_take:{lead_id}"),
                    InlineKeyboardButton(text="✖ Пропустить", callback_data=f"lead_skip:{lead_id}"),
                ]
            ]
        )
        for mgr in managers:
            try:
                await state.bot.send_message(int(str(mgr["user_id"])), card, reply_markup=kb)
            except Exception:
                pass

    @router.callback_query(F.data == "lead_cancel")
    async def cancel_lead(callback: CallbackQuery, state_fsm: FSMContext) -> None:
        await state_fsm.clear()
        await callback.message.edit_text("Заявка отменена.")  # type: ignore
        await callback.answer()
        await callback.message.answer("Выберите действие:", reply_markup=main_menu())  # type: ignore

    @router.callback_query(F.data.startswith("lead_take:"))
    async def take_lead_handler(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        lead_id = int(callback.data.split(":")[1])
        manager_id = callback.from_user.id
        success = await service.take_lead(db, lead_id, manager_id)
        if not success:
            await callback.answer("Лид уже взят другим менеджером.", show_alert=True)
            return
        state.metrics.inc_leads_taken()
        await callback.answer("✅ Вы взяли лид!")
        lead = await service.get_lead(db, lead_id)
        if lead:
            try:
                await state.bot.send_message(
                    int(str(lead["client_user_id"])),
                    "👋 С вами свяжется менеджер!",
                )
            except Exception:
                pass

    @router.callback_query(F.data.startswith("lead_skip:"))
    async def skip_lead_handler(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        lead_id = int(callback.data.split(":")[1])
        await service.skip_lead(db, lead_id, callback.from_user.id)
        await callback.answer("Пропущено.")

    @router.message(F.text == "📞 Контакты")
    async def contacts(message: Message) -> None:
        await message.answer("📞 Контакты:\nТелефон: +7 (999) 123-45-67\nEmail: info@example.com")

    @router.message(F.text == "📋 Очередь лидов")
    async def manager_queue(message: Message) -> None:
        leads = await service.get_new_leads(db)
        if not leads:
            await message.answer("Нет новых лидов.")
            return
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        for lead in leads[:10]:
            card = lead_card(lead)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Взять", callback_data=f"lead_take:{lead['id']}"),
                        InlineKeyboardButton(text="✖ Пропустить", callback_data=f"lead_skip:{lead['id']}"),
                    ]
                ]
            )
            await message.answer(card, reply_markup=kb)

    @router.message(F.text == "📊 Моя статистика")
    async def my_stats(message: Message) -> None:
        stats = await service.get_manager_stats(db, message.from_user.id)  # type: ignore
        await message.answer(f"📊 Ваша статистика:\nЗакрытых лидов: {stats['taken']}")

    return router
