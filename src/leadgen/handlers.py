from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.core.bot_factory import AppState
from src.core.callbacks import parse_callback_int
from src.core.fsm import LeadForm
from src.core.nav import main_menu
from src.core.ui import lead_card, lead_summary
from src.leadgen import service, texts


def create_leadgen_router(app_state: AppState) -> Router:
    router = Router()
    db = app_state.db

    @router.message(Command("start"))
    async def cmd_start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            texts.WELCOME,
            reply_markup=main_menu(),
        )

    @router.message(F.text == "📝 Оставить заявку")
    async def start_form(message: Message, state: FSMContext) -> None:
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
            await message.answer(texts.ASK_INTEREST, reply_markup=kb)
        else:
            await state.set_state(LeadForm.entering_name)
            await message.answer(texts.ASK_NAME)

    @router.callback_query(F.data.startswith("lead_svc:"))
    async def choose_service(callback: CallbackQuery, state: FSMContext) -> None:
        if not callback.data:
            return
        service_key = callback.data.split(":", 1)[1]
        await state.update_data(service=service_key)
        await state.set_state(LeadForm.entering_name)
        await callback.message.edit_text(texts.ASK_NAME)  # type: ignore
        await callback.answer()

    @router.message(LeadForm.entering_name)
    async def enter_name(message: Message, state: FSMContext) -> None:
        await state.update_data(name=message.text or "")
        await state.set_state(LeadForm.entering_phone)
        await message.answer(texts.ASK_PHONE)

    @router.message(LeadForm.entering_phone)
    async def enter_phone(message: Message, state: FSMContext) -> None:
        phone = message.text or ""
        if not phone.startswith("+7") or len(phone) != 12 or not phone[2:].isdigit():
            await message.answer(texts.BAD_PHONE)
            return
        await state.update_data(phone=phone)
        data = await state.get_data()
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
                    InlineKeyboardButton(text=texts.BTN_SEND, callback_data="lead_confirm"),
                    InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data="lead_cancel"),
                ]
            ]
        )
        await state.set_state(LeadForm.confirming)
        await message.answer(texts.confirm_lead(text), reply_markup=kb)

    @router.callback_query(F.data == "lead_confirm", LeadForm.confirming)
    async def confirm_lead(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        lead_id = await service.create_lead(
            db,
            client_user_id=callback.from_user.id,
            client_name=data.get("name"),
            client_phone=data.get("phone"),
            field_values=json.dumps({"Интерес": data.get("service", "")}),
        )
        app_state.metrics.inc_leads()
        await state.clear()
        await callback.message.edit_text(texts.LEAD_SENT)  # type: ignore
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
                    InlineKeyboardButton(text=texts.BTN_TAKE_WORK, callback_data=f"lead_take:{lead_id}"),
                    InlineKeyboardButton(text=texts.BTN_SKIP, callback_data=f"lead_skip:{lead_id}"),
                ]
            ]
        )
        for mgr in managers:
            try:
                await app_state.bot.send_message(int(str(mgr["user_id"])), card, reply_markup=kb)
            except Exception:
                pass

    @router.callback_query(F.data == "lead_cancel")
    async def cancel_lead(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.message.edit_text(texts.LEAD_CANCELLED)  # type: ignore
        await callback.answer()
        await callback.message.answer(texts.CHOOSE_ACTION, reply_markup=main_menu())  # type: ignore

    @router.callback_query(F.data.startswith("lead_take:"))
    async def take_lead_handler(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        lead_id = parse_callback_int(callback.data, "lead_take:")
        if lead_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        manager_id = callback.from_user.id
        success = await service.take_lead(db, lead_id, manager_id)
        if not success:
            await callback.answer(texts.LEAD_ALREADY_TAKEN, show_alert=True)
            return
        app_state.metrics.inc_leads_taken()
        await callback.answer(texts.LEAD_TAKEN)
        lead = await service.get_lead(db, lead_id)
        if lead:
            try:
                await app_state.bot.send_message(
                    int(str(lead["client_user_id"])),
                    "👋 С вами свяжется менеджер!",
                )
            except Exception:
                pass

    @router.callback_query(F.data.startswith("lead_skip:"))
    async def skip_lead_handler(callback: CallbackQuery) -> None:
        if not callback.data:
            return
        lead_id = parse_callback_int(callback.data, "lead_skip:")
        if lead_id is None:
            await callback.answer(texts.BAD_REQUEST, show_alert=True)
            return
        await service.skip_lead(db, lead_id, callback.from_user.id)
        await callback.answer(texts.SKIPPED)

    @router.message(F.text == "📞 Контакты")
    async def contacts(message: Message) -> None:
        await message.answer(texts.CONTACTS)

    @router.message(F.text == "📋 Очередь лидов")
    async def manager_queue(message: Message) -> None:
        uid = message.from_user.id  # type: ignore[union-attr]
        # Очередь — менеджерская поверхность: активный менеджер из таблицы
        # managers либо админ бота (config.admin_ids — тот же паттерн, что
        # у admin-роутера: is_admin = admin_ids + AdminGate).
        if not await service.is_active_manager(db, uid) and uid not in (
            app_state.config.admin_ids or []
        ):
            return
        leads = await service.get_new_leads(db)
        if not leads:
            await message.answer(texts.NO_NEW_LEADS)
            return
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        for lead in leads[:10]:
            card = lead_card(lead)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text=texts.BTN_TAKE, callback_data=f"lead_take:{lead['id']}"),
                        InlineKeyboardButton(text=texts.BTN_SKIP, callback_data=f"lead_skip:{lead['id']}"),
                    ]
                ]
            )
            await message.answer(card, reply_markup=kb)

    @router.message(F.text == "📊 Моя статистика")
    async def my_stats(message: Message) -> None:
        stats = await service.get_manager_stats(db, message.from_user.id)  # type: ignore
        await message.answer(texts.manager_stats(stats["taken"]))

    return router
