"""State-dependent view tests for leadgen."""

from __future__ import annotations

import pytest

from src.leadgen import service


@pytest.mark.asyncio
async def test_new_leads_empty_vs_populated(db):
    assert await service.get_new_leads(db) == []

    await service.create_lead(db, client_user_id=1, client_name="Alice", client_phone="+1")
    leads = await service.get_new_leads(db)
    assert len(leads) == 1
    assert leads[0]["client_name"] == "Alice"


@pytest.mark.asyncio
async def test_lead_missing_vs_present(db):
    assert await service.get_lead(db, 99999) is None

    lid = await service.create_lead(db, client_user_id=1, client_name="Alice")
    lead = await service.get_lead(db, lid)
    assert lead is not None
    assert lead["client_name"] == "Alice"


@pytest.mark.asyncio
async def test_find_lead_by_phone(db):
    assert await service.find_lead_by_phone(db, "+999") is None

    await service.create_lead(db, client_user_id=1, client_name="Alice", client_phone="+123")
    lead = await service.find_lead_by_phone(db, "+123")
    assert lead is not None


@pytest.mark.asyncio
async def test_close_lead_changes_state(db):
    lid = await service.create_lead(db, client_user_id=1, client_name="Alice")
    lead = await service.get_lead(db, lid)
    assert lead["status"] == "new"

    await service.close_lead(db, lid)
    lead = await service.get_lead(db, lid)
    assert lead["status"] == "closed"
    assert lead["closed_at"] is not None


@pytest.mark.asyncio
async def test_take_lead_changes_state(db):
    lid = await service.create_lead(db, client_user_id=1, client_name="Alice")
    result = await service.take_lead(db, lid, manager_id=5)
    assert result is True

    lead = await service.get_lead(db, lid)
    assert lead["manager_user_id"] == 5
    assert lead["taken_at"] is not None
