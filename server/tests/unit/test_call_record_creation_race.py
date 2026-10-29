"""Concurrent creators must reuse the same CDR across inbound/outbound paths."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.repositories.call_record_repository import CallRecordRepository
from app.services.call_record_service import CallRecordService


@pytest.mark.asyncio
@pytest.mark.parametrize('methods', [
    ('create_for_outbound', 'create_for_outbound'),
    ('create_for_incoming', 'create_for_incoming'),
    ('create_for_outbound', 'create_for_incoming'),
])
async def test_concurrent_creators_lock_before_lookup_and_reuse_record(monkeypatch, methods):
    lock = asyncio.Lock()
    records = {}
    created = []
    held_by = set()

    async def acquire(db, tenant_id, call_id):
        assert (tenant_id, call_id) == (1, 'call-race')
        await lock.acquire()
        held_by.add(id(db))

    async def lookup(db, call_id, tenant_id):
        assert id(db) in held_by
        await asyncio.sleep(0)
        return records.get((tenant_id, call_id))

    async def create(db, data, *, commit):
        assert not commit
        key = (data['tenant_id'], data['call_id'])
        assert key not in records
        await asyncio.sleep(0)
        row = SimpleNamespace(id=1, public_id=uuid4(), **data)
        records[key] = row
        created.append(row)
        return row

    monkeypatch.setattr(CallRecordRepository, 'lock_creation', acquire)
    monkeypatch.setattr(CallRecordRepository, 'get_by_call_id', lookup)
    monkeypatch.setattr(CallRecordRepository, 'create', create)
    monkeypatch.setattr('app.services.call_record_service.CallTrajectoryService.append_event', AsyncMock())
    monkeypatch.setattr('app.services.call_record_service._to_detail', lambda row, _: {'id': row.id})

    async def request(method):
        db = AsyncMock()

        async def commit():
            held_by.remove(id(db))
            lock.release()

        db.commit.side_effect = commit
        try:
            return await getattr(CallRecordService, method)(
                db, 1, call_id='call-race', conversation_id=None,
                root_call_id=None, from_number='12025550100',
                to_number='12025550101', identify_user=False,
            )
        finally:
            if id(db) in held_by:
                held_by.remove(id(db))
                lock.release()

    results = await asyncio.gather(*(request(method) for method in methods))
    assert results == [{'id': 1}, {'id': 1}]
    assert len(created) == 1


@pytest.mark.asyncio
async def test_creation_lock_is_transaction_scoped_and_parameterized():
    db = AsyncMock()
    await CallRecordRepository.lock_creation(db, 7, "call'; --")
    statement, params = db.execute.await_args.args
    assert 'pg_advisory_xact_lock' in str(statement)
    assert ':key' in str(statement)
    assert params == {'key': "call-record:7:call'; --"}
