from __future__ import annotations

import asyncio
from datetime import UTC

from aiogram import Bot

from src.core.database import Database
from src.leadgen import service


async def escalation_loop(bot: Bot, db: Database, escalation_minutes: int = 15) -> None:
    while True:
        try:
            leads = await service.get_new_leads(db)
            for lead in leads:
                created = str(lead.get("created_at", ""))
                if not created:
                    continue
                from datetime import datetime

                try:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except ValueError:
                    continue
                now = datetime.now(UTC)
                diff = (now - created_dt).total_seconds() / 60
                if diff >= escalation_minutes:
                    await service.escalate_lead(db, int(lead["id"]))
                    try:
                        await bot.send_message(
                            int(str(lead["client_user_id"])),
                            f"⏰ Лид #{lead['id']} не взят менеджерами. Мы свяжемся с вами.",
                        )
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(60)
