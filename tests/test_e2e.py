from __future__ import annotations

import pytest

from src.core.ui import lead_card
from src.leadgen import service


@pytest.mark.asyncio
async def test_full_flow(db):
    lead_id = await service.create_lead(
        db, client_user_id=111, client_name="Alice", client_phone="+71234567890",
        field_values='{"Интерес": "ремонт"}'
    )
    assert lead_id > 0

    taken = await service.take_lead(db, lead_id, 222)
    assert taken is True

    await service.close_lead(db, lead_id)
    lead = await service.get_lead(db, lead_id)
    assert lead["status"] == "closed"


@pytest.mark.asyncio
async def test_two_managers_race(db):
    lead_id = await service.create_lead(db, client_user_id=111)
    first = await service.take_lead(db, lead_id, 222)
    second = await service.take_lead(db, lead_id, 333)
    assert first is True
    assert second is False
    lead = await service.get_lead(db, lead_id)
    assert lead["manager_user_id"] == 222


@pytest.mark.asyncio
async def test_escalation_flow(db):
    lead_id = await service.create_lead(db, client_user_id=111)
    await service.escalate_lead(db, lead_id)
    lead = await service.get_lead(db, lead_id)
    assert lead["status"] == "escalated"


@pytest.mark.asyncio
async def test_lead_card_html():
    card = lead_card({
        "id": 1,
        "client_name": "Test <script>",
        "client_phone": "+71234567890",
        "field_values": '{"Интерес": "ремонт"}',
    })
    assert "<script>" not in card
    assert "Новый лид! #1" in card
