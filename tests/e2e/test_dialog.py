"""Example real-Telegram E2E: send a command, wait for the reply (no sleep)."""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytest.importorskip("telethon")
from telethon import events  # noqa: E402

pytestmark = [
    pytest.mark.req,
    pytest.mark.e2e,
    pytest.mark.serial,
]


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


async def test_echo_real_telegram(telegram_user_client) -> None:
    client = telegram_user_client
    bot = await client.get_entity(os.environ["TEST_BOT_USERNAME"])
    wait_timeout = float(os.getenv("TELEGRAM_E2E_TIMEOUT", "20"))
    correlation = f"e2e-{uuid.uuid4().hex[:12]}"

    response = await wait_for_bot_message(
        client,
        bot,
        predicate=lambda message: correlation in (message.raw_text or ""),
        trigger=lambda: client.send_message(bot, f"/echo {correlation}"),
        wait_timeout=wait_timeout,
    )

    assert correlation in response.raw_text
