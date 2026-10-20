"""Тексты бота: константы существуют, хелперы подставляют свои аргументы.

Зачем
=====

`src/leadgen/texts.py` — единый источник строк, которые бот отправляет. Тест
держит две вещи:

1. **Константы на месте и непусты.** Обработчик, отдавший пустую строку, —
   молчаливый дефект: пользователь видит пузырь без текста, а тест на поведение
   (если он сверяет вхождение) проходит.
2. **Хелперы действительно подставляют переданное.** Правка, выбросившая аргумент
   (сводка заявки, счётчик лидов), иначе прошла бы незамеченной: строка всё ещё
   «есть».

Каждая проверка имеет негативного близнеца: сломай подстановку — тест красный.
"""

from __future__ import annotations

import pytest

from src.leadgen import texts

CONSTANTS = [
    texts.WELCOME,
    texts.ASK_INTEREST,
    texts.ASK_NAME,
    texts.ASK_PHONE,
    texts.BAD_PHONE,
    texts.LEAD_SENT,
    texts.LEAD_CANCELLED,
    texts.CHOOSE_ACTION,
    texts.LEAD_ALREADY_TAKEN,
    texts.LEAD_TAKEN,
    texts.SKIPPED,
    texts.NO_NEW_LEADS,
    texts.CONTACTS,
    texts.ASK_PASSWORD,
    texts.ADMIN_WELCOME,
    texts.BAD_PASSWORD,
    texts.TOO_MANY_ATTEMPTS,
    texts.NO_MANAGERS,
    texts.MANAGERS_HEADER,
    texts.SETTINGS_STUB,
    texts.BAD_REQUEST,
]

BUTTON_LABELS = [
    texts.BTN_NEW_LEAD,
    texts.BTN_CONTACTS,
    texts.BTN_SEND,
    texts.BTN_CANCEL,
    texts.BTN_QUEUE,
    texts.BTN_MY_STATS,
    texts.BTN_TAKE_WORK,
    texts.BTN_TAKE,
    texts.BTN_SKIP,
    texts.BTN_MANAGERS,
    texts.BTN_STATS,
    texts.BTN_SETTINGS,
]


@pytest.mark.parametrize("value", CONSTANTS, ids=lambda v: v[:24])
def test_текст_непуст(value: str) -> None:
    """Пустой ответ — пузырь без текста; пользователь не поймёт, что случилось."""
    assert value.strip(), "текст сообщения пуст или из пробелов"


@pytest.mark.parametrize("label", BUTTON_LABELS, ids=lambda v: v[:24])
def test_подпись_кнопки_непуста(label: str) -> None:
    """Кнопка без подписи неотличима от декоративного разделителя."""
    assert label.strip(), "подпись кнопки пуста"


def test_все_подписи_кнопок_уникальны() -> None:
    """Две кнопки с одной подписью — пользователь нажмёт не ту.

    Обработчики выше различают кнопки по тексту (`F.text == ...`), так что
    совпадение подписей ломает маршрутизацию, а не только вид.
    """
    duplicates = {x for x in BUTTON_LABELS if BUTTON_LABELS.count(x) > 1}
    assert not duplicates, f"дубли подписей кнопок: {duplicates}"


def test_приветствие_содержит_подстроку_из_кейсов() -> None:
    """Кейс фермы и e2e-тест цитируют подстроку без эмодзи — она обязана быть.

    `text_contains` сверяет вхождение, поэтому ведущий эмодзи правке не мешает,
    но сама фраза обязана остаться: это тот текст, который ловят оба пути.
    """
    assert "Здравствуйте! Оставьте заявку" in texts.WELCOME


# ── хелперы: подстановка аргумента, а не литерал ────────────────────────────


def test_confirm_lead_вставляет_сводку() -> None:
    """Пустая сводка вместо данных — пользователь подтверждает вслепую."""
    got = texts.confirm_lead("• Интерес: внедрение")
    assert "• Интерес: внедрение" in got, got


def test_manager_stats_вставляет_число() -> None:
    """Литерал вместо счётчика показал бы менеджеру чужое число."""
    assert "7" in texts.manager_stats(7)


def test_manager_stats_различает_числа() -> None:
    """Негативный близнец: фиксированное число прошло бы первую проверку."""
    assert texts.manager_stats(1) != texts.manager_stats(2)


def test_admin_stats_несёт_шесть_счётчиков() -> None:
    """Статистика, где день и неделя совпали, — одна цифра под двумя ярлыками."""
    got = texts.admin_stats(1, 2, 3, 4, 5, 6)
    for n in ("1", "2", "3", "4", "5", "6"):
        assert n in got, f"{n} нет в {got!r}"
