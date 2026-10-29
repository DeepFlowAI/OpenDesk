"""Unit tests for platform phone-number delete conflict checks."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessError
from app.extensions.telephony.phone_number_service import PhoneNumberService
from app.repositories.personal_auto_outbound_repository import (
    ACTIVE_SESSION_STATUSES,
    PersonalAutoOutboundRepository,
)
from app.repositories.phone_number_repository import PhoneNumberRepository


@pytest.mark.asyncio
async def test_delete_phone_number_ok_when_no_session_refs(monkeypatch):
    row = SimpleNamespace(id="pn-1")
    deleted: list[object] = []

    async def fake_get_by_id(_db, phone_id):
        assert phone_id == "pn-1"
        return row

    async def fake_count(_db, phone_id, *, statuses=None):
        assert phone_id == "pn-1"
        return 0

    async def fake_delete(_db, target):
        deleted.append(target)

    monkeypatch.setattr(PhoneNumberRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        PersonalAutoOutboundRepository,
        "count_by_outbound_phone_number_id",
        fake_count,
    )
    monkeypatch.setattr(PhoneNumberRepository, "delete", fake_delete)

    await PhoneNumberService.delete_phone_number(AsyncMock(), "pn-1")

    assert deleted == [row]


@pytest.mark.asyncio
async def test_delete_phone_number_409_when_active_session(monkeypatch):
    row = SimpleNamespace(id="pn-1")
    calls: list[tuple[str, ...] | None] = []

    async def fake_get_by_id(_db, phone_id):
        return row

    async def fake_count(_db, phone_id, *, statuses=None):
        calls.append(statuses)
        if statuses == ACTIVE_SESSION_STATUSES:
            return 1
        return 0

    async def fail_delete(*_args, **_kwargs):
        raise AssertionError("delete must not run when active sessions exist")

    monkeypatch.setattr(PhoneNumberRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        PersonalAutoOutboundRepository,
        "count_by_outbound_phone_number_id",
        fake_count,
    )
    monkeypatch.setattr(PhoneNumberRepository, "delete", fail_delete)

    with pytest.raises(BusinessError) as exc_info:
        await PhoneNumberService.delete_phone_number(AsyncMock(), "pn-1")

    err = exc_info.value
    assert err.status_code == 409
    assert err.code == "PHONE_IN_ACTIVE_PERSONAL_AUTO_OUTBOUND"
    assert "end the session first" in err.message
    assert calls == [ACTIVE_SESSION_STATUSES]


@pytest.mark.asyncio
async def test_delete_phone_number_409_when_only_history(monkeypatch):
    row = SimpleNamespace(id="pn-1")
    calls: list[tuple[str, ...] | None] = []

    async def fake_get_by_id(_db, phone_id):
        return row

    async def fake_count(_db, phone_id, *, statuses=None):
        calls.append(statuses)
        if statuses == ACTIVE_SESSION_STATUSES:
            return 0
        return 2

    async def fail_delete(*_args, **_kwargs):
        raise AssertionError("delete must not run when history refs exist")

    monkeypatch.setattr(PhoneNumberRepository, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        PersonalAutoOutboundRepository,
        "count_by_outbound_phone_number_id",
        fake_count,
    )
    monkeypatch.setattr(PhoneNumberRepository, "delete", fail_delete)

    with pytest.raises(BusinessError) as exc_info:
        await PhoneNumberService.delete_phone_number(AsyncMock(), "pn-1")

    err = exc_info.value
    assert err.status_code == 409
    assert err.code == "PHONE_IN_PERSONAL_AUTO_OUTBOUND_HISTORY"
    assert "ask an administrator" in err.message
    assert calls == [ACTIVE_SESSION_STATUSES, None]
