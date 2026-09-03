"""Session-scoped Telethon client fixture for real Telegram E2E tests.

These tests are skipped automatically unless RUN_TELEGRAM_E2E=1 and the
required secrets are present. Telethon is imported lazily so collecting
the suite without the `e2e` extras installed does not fail.
"""
from __future__ import annotations

import os

import pytest

pytest_asyncio = pytest.importorskip("pytest_asyncio")


@pytest_asyncio.fixture(scope="session")
async def telegram_user_client():
    telethon = pytest.importorskip("telethon")
    TelegramClient = telethon.TelegramClient
    StringSession = telethon.sessions.StringSession

    required = [
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "TELEGRAM_SESSION_STRING",
        "TEST_BOT_USERNAME",
    ]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        pytest.skip("missing E2E secrets: " + ", ".join(missing))

    client = TelegramClient(
        StringSession(os.environ["TELEGRAM_SESSION_STRING"]),
        int(os.environ["TELEGRAM_API_ID"]),
        os.environ["TELEGRAM_API_HASH"],
    )
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        pytest.fail("TELEGRAM_SESSION_STRING is not authorized")

    try:
        yield client
    finally:
        await client.disconnect()
