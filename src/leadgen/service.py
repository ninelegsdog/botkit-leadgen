from __future__ import annotations

from typing import Any

from sqlalchemy import text

from src.core.database import Database


async def create_lead(
    db: Database,
    *,
    client_user_id: int,
    client_name: str | None = None,
    client_phone: str | None = None,
    field_values: str = "{}",
) -> int:
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "INSERT INTO leads (client_user_id, client_name, client_phone, field_values, status) "
                "VALUES (:uid, :name, :phone, :fv, 'new')"
            ),
            {"uid": client_user_id, "name": client_name, "phone": client_phone, "fv": field_values},
        )
        lead_id = result.lastrowid  # type: ignore[attr-defined]
        assert lead_id is not None
        await session.execute(
            text("INSERT INTO lead_events (lead_id, user_id, action) VALUES (:lid, :uid, 'created')"),
            {"lid": lead_id, "uid": client_user_id},
        )
        return int(lead_id)


async def get_lead(db: Database, lead_id: int) -> dict[str, Any] | None:
    async with db.session() as session:
        result = await session.execute(text("SELECT * FROM leads WHERE id = :id"), {"id": lead_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def get_new_leads(db: Database) -> list[dict[str, Any]]:
    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM leads WHERE status = 'new' ORDER BY created_at ASC")
        )
        return [dict(r) for r in result.mappings().all()]


async def take_lead(db: Database, lead_id: int, manager_id: int) -> bool:
    async with db.transaction() as session:
        result = await session.execute(
            text(
                "UPDATE leads SET manager_user_id = :mid, status = 'taken', taken_at = datetime('now') "
                "WHERE id = :lid AND status = 'new'"
            ),
            {"mid": manager_id, "lid": lead_id},
        )
        if result.rowcount == 0:  # type: ignore[attr-defined]
            return False
        await session.execute(
            text("INSERT INTO lead_events (lead_id, user_id, action) VALUES (:lid, :mid, 'taken')"),
            {"lid": lead_id, "mid": manager_id},
        )
        return True


async def skip_lead(db: Database, lead_id: int, manager_id: int) -> None:
    async with db.transaction() as session:
        await session.execute(
            text("INSERT INTO lead_events (lead_id, user_id, action) VALUES (:lid, :mid, 'skipped')"),
            {"lid": lead_id, "mid": manager_id},
        )


async def close_lead(db: Database, lead_id: int) -> None:
    async with db.transaction() as session:
        await session.execute(
            text("UPDATE leads SET status = 'closed', closed_at = datetime('now') WHERE id = :lid"),
            {"lid": lead_id},
        )
        await session.execute(
            text("INSERT INTO lead_events (lead_id, user_id, action) VALUES (:lid, 0, 'closed')"),
            {"lid": lead_id},
        )


async def escalate_lead(db: Database, lead_id: int) -> None:
    async with db.transaction() as session:
        await session.execute(
            text("UPDATE leads SET status = 'escalated' WHERE id = :lid AND status = 'new'"),
            {"lid": lead_id},
        )
        await session.execute(
            text("INSERT INTO lead_events (lead_id, user_id, action) VALUES (:lid, 0, 'escalated')"),
            {"lid": lead_id},
        )


async def find_lead_by_phone(db: Database, phone: str) -> dict[str, Any] | None:
    async with db.session() as session:
        result = await session.execute(
            text(
                "SELECT * FROM leads WHERE client_phone = :phone AND status != 'closed' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"phone": phone},
        )
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def add_feedback(db: Database, lead_id: int, rating: int, feedback_text: str) -> None:
    async with db.transaction() as session:
        await session.execute(
            text("INSERT INTO feedback (lead_id, rating, text) VALUES (:lid, :r, :t)"),
            {"lid": lead_id, "r": rating, "t": feedback_text},
        )


async def get_lead_stats(db: Database, period: str = "day") -> dict[str, int]:
    interval = "1 day" if period == "day" else "7 days"
    async with db.session() as session:
        result = await session.execute(
            text(
                f"SELECT status, COUNT(*) as cnt FROM leads "
                f"WHERE created_at >= datetime('now', '-{interval}') GROUP BY status"
            )
        )
        rows = result.mappings().all()
        return {r["status"]: r["cnt"] for r in rows}


async def get_manager_stats(db: Database, manager_id: int) -> dict[str, int]:
    async with db.session() as session:
        result = await session.execute(
            text("SELECT COUNT(*) as cnt FROM leads WHERE manager_user_id = :mid AND status = 'closed'"),
            {"mid": manager_id},
        )
        row = result.fetchone()
        return {"taken": int(row[0]) if row else 0}


async def get_active_managers(db: Database) -> list[dict[str, Any]]:
    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM managers WHERE is_active = 1 ORDER BY name")
        )
        return [dict(r) for r in result.mappings().all()]


async def get_active_fields(db: Database) -> list[dict[str, Any]]:
    async with db.session() as session:
        result = await session.execute(
            text("SELECT * FROM lead_fields WHERE is_active = 1 ORDER BY field_order")
        )
        return [dict(r) for r in result.mappings().all()]
