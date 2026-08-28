"""Generate a Telethon StringSession for real Telegram E2E tests."""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    load_dotenv()
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()
    try:
        print(client.session.save())
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
