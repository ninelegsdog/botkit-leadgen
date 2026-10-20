from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from src.leadgen import texts


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_NEW_LEAD), KeyboardButton(text=texts.BTN_CONTACTS)],
        ],
        resize_keyboard=True,
    )


def manager_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_QUEUE), KeyboardButton(text=texts.BTN_MY_STATS)],
        ],
        resize_keyboard=True,
    )


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_MANAGERS), KeyboardButton(text=texts.BTN_STATS)],
            [KeyboardButton(text=texts.BTN_SETTINGS)],
        ],
        resize_keyboard=True,
    )
