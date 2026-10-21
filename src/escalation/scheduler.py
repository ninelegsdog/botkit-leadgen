from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot

from src.core.database import Database
from src.leadgen import service

logger = logging.getLogger(__name__)


def _aware_utc(raw: str) -> datetime | None:
    """ISO-строка из БД → aware UTC; None — не разобрать.

    Прод хранит `created_at` как TEXT DEFAULT (datetime('now')) — наивную
    строку UTC. Наивная форма получает метку UTC, aware (Z или смещение)
    переводится в UTC. До правки F2 сравнение now(UTC) − naive бросало
    TypeError, который внешний except глотал целиком: эскалация вставала
    молча, а тест с aware-фиксатурой это не замечал.
    """
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)  # наивное в БД — это UTC
    return parsed.astimezone(UTC)


async def escalation_loop(bot: Bot, db: Database, escalation_minutes: int = 15) -> None:
    while True:
        try:
            leads = await service.get_new_leads(db)
            for lead in leads:
                created = str(lead.get("created_at", ""))
                if not created:
                    continue
                created_dt = _aware_utc(created)
                if created_dt is None:
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
            # Наружу, а не в молчание: именно except: pass прятал F2, пока
            # эскалация не была мертва в проде целиком.
            logger.exception("escalation cycle failed")
        await asyncio.sleep(60)
