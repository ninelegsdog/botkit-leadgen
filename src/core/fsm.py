from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class LeadForm(StatesGroup):
    choosing_service = State()
    entering_name = State()
    entering_phone = State()
    confirming = State()


class AdminAuth(StatesGroup):
    waiting_password = State()
