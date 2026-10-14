"""Real-Telegram E2E: ``/start`` must be answered with the bot's greeting (no sleep).

This replaces the earlier ``/echo`` template, which asserted a command no bot
implements: every run timed out and the suite could never go green. The
``/start`` greeting is the one reply each bot is guaranteed to send, and it is
the same string the live ``ops/e2e`` runner already asserts, so this test and
that runner cannot drift apart.
"""
from __future__ import annotations

import asyncio
import os

import pytest

pytest.importorskip("telethon")
from telethon import events  # noqa: E402

pytestmark = [
    pytest.mark.req,
    pytest.mark.e2e,
    pytest.mark.serial,
]

# Proven live by the ops/e2e runner: this exact substring is in every /start reply.
START_GREETING = "Здравствуйте! Оставьте заявку"


async def wait_for_bot_message(client, bot, *, predicate, trigger, wait_timeout):
    done = asyncio.Event()
    matched: dict = {}

    async def on_message(event):
        if predicate(event.message):
            matched["message"] = event.message
            done.set()

    client.add_event_handler(on_message, events.NewMessage(from_users=bot))
    try:
        await trigger()
        await asyncio.wait_for(done.wait(), timeout=wait_timeout)
        return matched["message"]
    finally:
        client.remove_event_handler(on_message)


async def test_start_real_telegram(telegram_user_client) -> None:
    client = telegram_user_client
    bot = await client.get_entity(os.environ["TEST_BOT_USERNAME"])
    wait_timeout = float(os.getenv("TELEGRAM_E2E_TIMEOUT", "20"))

    response = await wait_for_bot_message(
        client,
        bot,
        predicate=lambda message: START_GREETING in (message.raw_text or ""),
        trigger=lambda: client.send_message(bot, "/start"),
        wait_timeout=wait_timeout,
    )

    assert START_GREETING in response.raw_text
