from __future__ import annotations

import pytest

from src.leadgen import service


@pytest.mark.asyncio
async def test_create_lead(db):
    lead_id = await service.create_lead(
        db, client_user_id=123, client_name="Test", client_phone="+71234567890"
    )
    assert lead_id > 0


@pytest.mark.asyncio
async def test_get_lead(db):
    lead_id = await service.create_lead(db, client_user_id=123, client_name="Test")
    lead = await service.get_lead(db, lead_id)
    assert lead is not None
    assert lead["client_name"] == "Test"


@pytest.mark.asyncio
async def test_take_lead(db):
    lead_id = await service.create_lead(db, client_user_id=123)
    success = await service.take_lead(db, lead_id, 456)
    assert success is True
    lead = await service.get_lead(db, lead_id)
    assert lead["status"] == "taken"


@pytest.mark.asyncio
async def test_take_lead_race_condition(db):
    lead_id = await service.create_lead(db, client_user_id=123)
    first = await service.take_lead(db, lead_id, 456)
    assert first is True
    second = await service.take_lead(db, lead_id, 789)
    assert second is False


@pytest.mark.asyncio
async def test_get_new_leads(db):
    await service.create_lead(db, client_user_id=123)
    await service.create_lead(db, client_user_id=456)
    leads = await service.get_new_leads(db)
    assert len(leads) == 2


@pytest.mark.asyncio
async def test_close_lead(db):
    lead_id = await service.create_lead(db, client_user_id=123)
    await service.take_lead(db, lead_id, 456)
    await service.close_lead(db, lead_id)
    lead = await service.get_lead(db, lead_id)
    assert lead["status"] == "closed"


@pytest.mark.asyncio
async def test_escalate_lead(db):
    lead_id = await service.create_lead(db, client_user_id=123)
    await service.escalate_lead(db, lead_id)
    lead = await service.get_lead(db, lead_id)
    assert lead["status"] == "escalated"


@pytest.mark.asyncio
async def test_find_lead_by_phone(db):
    await service.create_lead(db, client_user_id=123, client_phone="+71234567890")
    found = await service.find_lead_by_phone(db, "+71234567890")
    assert found is not None


@pytest.mark.asyncio
async def test_add_feedback(db):
    lead_id = await service.create_lead(db, client_user_id=123)
    await service.add_feedback(db, lead_id, 5, "Great service!")
