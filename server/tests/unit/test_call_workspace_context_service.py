"""Server-owned business context for call workspace recovery."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.auto_outbound_repository import AutoOutboundRepository
from app.services.call_workspace_context_service import CallWorkspaceContextService


@pytest.mark.asyncio
async def test_auto_outbound_context_resolves_from_call_record(monkeypatch):
    lookup = AsyncMock(return_value=SimpleNamespace(id=34, task_id=12))
    monkeypatch.setattr(
        AutoOutboundRepository,
        "get_record_by_call_record_id",
        lookup,
    )

    context = await CallWorkspaceContextService.get_auto_outbound_context(
        db=SimpleNamespace(),
        tenant_id=7,
        call_record=SimpleNamespace(id=99, call_source="auto_outbound"),
    )

    assert context == {
        "source": "auto_outbound",
        "task_id": 12,
        "record_id": 34,
    }
    lookup.assert_awaited_once_with(
        SimpleNamespace(),
        tenant_id=7,
        call_record_id=99,
    )


@pytest.mark.asyncio
async def test_auto_outbound_context_ignores_regular_call(monkeypatch):
    lookup = AsyncMock()
    monkeypatch.setattr(
        AutoOutboundRepository,
        "get_record_by_call_record_id",
        lookup,
    )

    context = await CallWorkspaceContextService.get_auto_outbound_context(
        db=SimpleNamespace(),
        tenant_id=7,
        call_record=SimpleNamespace(id=99, call_source="inbound"),
    )

    assert context == {}
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_outbound_contexts_resolve_batch_for_history(monkeypatch):
    lookup = AsyncMock(
        return_value={
            99: SimpleNamespace(id=34, task_id=12),
        }
    )
    monkeypatch.setattr(
        AutoOutboundRepository,
        "get_latest_records_by_call_record_ids",
        lookup,
    )
    db = SimpleNamespace()

    contexts = await CallWorkspaceContextService.get_auto_outbound_contexts(
        db=db,
        tenant_id=7,
        call_records=[
            SimpleNamespace(id=99, call_source="auto_outbound"),
            SimpleNamespace(id=100, call_source="inbound"),
        ],
    )

    assert contexts == {
        99: {
            "source": "auto_outbound",
            "task_id": 12,
            "record_id": 34,
        }
    }
    lookup.assert_awaited_once_with(
        db,
        tenant_id=7,
        call_record_ids=[99],
    )


@pytest.mark.asyncio
async def test_auto_outbound_contexts_skip_lookup_without_eligible_records(monkeypatch):
    lookup = AsyncMock()
    monkeypatch.setattr(
        AutoOutboundRepository,
        "get_latest_records_by_call_record_ids",
        lookup,
    )

    contexts = await CallWorkspaceContextService.get_auto_outbound_contexts(
        db=SimpleNamespace(),
        tenant_id=7,
        call_records=[SimpleNamespace(id=100, call_source="inbound")],
    )

    assert contexts == {}
    lookup.assert_not_awaited()
