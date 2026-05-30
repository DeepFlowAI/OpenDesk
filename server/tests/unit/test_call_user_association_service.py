from types import SimpleNamespace

import pytest

from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.user_repository import UserRepository
from app.services.call_user_association_service import (
    CallUserAssociationService,
    customer_number_for_call,
    phone_match_keys,
)
from app.services.user_service import UserService


def _record(**overrides):
    data = {
        "id": 10,
        "call_id": "call-1",
        "direction": "inbound",
        "from_number": "+86 186-0112-3206",
        "to_number": "4001681715",
        "user_id": None,
        "extra_metadata": {},
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _user(user_id: int, *, name: str = "Alice", phone: str = "18601123206"):
    return SimpleNamespace(
        id=user_id,
        tenant_id=1,
        public_id=f"usr_test_{user_id}",
        name=name,
        phone=phone,
        email=None,
    )


@pytest.mark.asyncio
async def test_identify_links_single_normalized_phone_match(monkeypatch):
    row = _record()
    user = _user(22, phone="186 0112 3206")

    async def fake_list_with_phone(_db, _tenant_id):
        return [user]

    async def fake_update(_db, record, patch):
        for key, value in patch.items():
            setattr(record, key, value)
        return record

    monkeypatch.setattr(UserRepository, "list_with_phone", fake_list_with_phone)
    monkeypatch.setattr(CallRecordRepository, "update", fake_update)

    result = await CallUserAssociationService.identify_for_record(object(), 1, row)

    assert result["status"] == "linked"
    assert row.user_id == user.id
    assert result["user"]["id"] == user.id


@pytest.mark.asyncio
async def test_identify_returns_candidates_for_multiple_matches(monkeypatch):
    row = _record(from_number="18800001111")
    users = [_user(1, name="First", phone="18800001111"), _user(2, name="Second", phone="188-0000-1111")]

    async def fake_list_with_phone(_db, _tenant_id):
        return users

    async def fake_update(_db, record, patch):
        for key, value in patch.items():
            setattr(record, key, value)
        return record

    monkeypatch.setattr(UserRepository, "list_with_phone", fake_list_with_phone)
    monkeypatch.setattr(CallRecordRepository, "update", fake_update)

    result = await CallUserAssociationService.identify_for_record(object(), 1, row)

    assert result["status"] == "multiple"
    assert row.user_id is None
    assert {candidate["id"] for candidate in result["candidates"]} == {1, 2}


@pytest.mark.asyncio
async def test_identify_creates_user_when_no_match(monkeypatch):
    row = _record(direction="outbound", from_number="4001681715", to_number="15500008888")
    created_user = _user(33, name="15500008888", phone="15500008888")

    async def fake_list_with_phone(_db, _tenant_id):
        return []

    async def fake_create_user(_db, tenant_id, data, actor_id=None):
        assert tenant_id == 1
        assert data.phone == "15500008888"
        assert actor_id == 7
        return {"id": created_user.id}

    async def fake_get_by_id(_db, user_id):
        assert user_id == created_user.id
        return created_user

    async def fake_update(_db, record, patch):
        for key, value in patch.items():
            setattr(record, key, value)
        return record

    monkeypatch.setattr(UserRepository, "list_with_phone", fake_list_with_phone)
    monkeypatch.setattr(UserService, "create_user", fake_create_user)
    monkeypatch.setattr(UserRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(CallRecordRepository, "update", fake_update)

    result = await CallUserAssociationService.identify_for_record(object(), 1, row, actor_id=7)

    assert result["status"] == "created"
    assert row.user_id == created_user.id
    assert result["user"]["phone"] == "15500008888"


def test_phone_matching_variants_and_customer_number():
    assert "18601123206" in phone_match_keys("+86 (186) 0112-3206")
    assert customer_number_for_call("inbound", "13800138000", "400") == "13800138000"
    assert customer_number_for_call("outbound", "400", "13800138000") == "13800138000"
