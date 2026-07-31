"""
Unit tests for CcAgentStatusService.list_transfer_queues.
"""
from unittest.mock import AsyncMock

import pytest

from app.repositories.employee_group_repository import EmployeeGroupRepository
from app.services.cc_agent_status_service import CcAgentStatusService
from app.services import queue_resource_provider as qrp
from app.services.queue_resource_provider import CallCenterResourceProvider
from app.services.queue_strategy import QueueCandidate


def _group(group_id: int, name: str) -> dict:
    return {
        "id": group_id,
        "name": name,
        "description": None,
        "member_count": 0,
        "created_at": None,
        "updated_at": None,
    }


def _pass_through_ringable(monkeypatch):
    async def fake_filter(r, tenant_id, candidates):
        return [c for c in candidates if c.available]

    monkeypatch.setattr(qrp, "filter_ringable_call_center_candidates", fake_filter)


@pytest.mark.asyncio
async def test_list_transfer_queues_counts_available_agents(monkeypatch):
    groups = [_group(1, "Sales"), _group(2, "Support")]
    monkeypatch.setattr(
        EmployeeGroupRepository,
        "get_paginated",
        AsyncMock(return_value=(groups, 2)),
    )
    _pass_through_ringable(monkeypatch)

    async def fake_list_candidates(self, db, r, tenant_id, queue_type, queue_id, task_context=None):
        assert queue_type == "employee_group"
        if queue_id == 1:
            return [
                QueueCandidate(employee_id=11, available=True),
                QueueCandidate(employee_id=12, available=True),
                QueueCandidate(employee_id=13, available=False),
            ]
        return [
            QueueCandidate(employee_id=21, available=False),
            QueueCandidate(employee_id=22, available=False),
        ]

    monkeypatch.setattr(
        CallCenterResourceProvider, "list_candidates", fake_list_candidates
    )

    result = await CcAgentStatusService.list_transfer_queues(
        db=None, tenant_id=7, keyword=None, r=object()
    )

    by_id = {item["queue_id"]: item for item in result}
    assert len(result) == 2
    assert by_id[1]["available_agent_count"] == 2
    assert by_id[1]["queue_type"] == "employee_group"
    assert by_id[1]["name"] == "Sales"
    assert by_id[2]["available_agent_count"] == 0
    assert by_id[2]["name"] == "Support"


@pytest.mark.asyncio
async def test_list_transfer_queues_orders_available_first(monkeypatch):
    groups = [_group(1, "Alpha"), _group(2, "Beta")]
    monkeypatch.setattr(
        EmployeeGroupRepository,
        "get_paginated",
        AsyncMock(return_value=(groups, 2)),
    )
    _pass_through_ringable(monkeypatch)

    async def fake_list_candidates(self, db, r, tenant_id, queue_type, queue_id, task_context=None):
        if queue_id == 1:
            return [QueueCandidate(employee_id=11, available=False)]
        return [
            QueueCandidate(employee_id=21, available=True),
            QueueCandidate(employee_id=22, available=True),
        ]

    monkeypatch.setattr(
        CallCenterResourceProvider, "list_candidates", fake_list_candidates
    )

    result = await CcAgentStatusService.list_transfer_queues(
        db=None, tenant_id=7, keyword=None, r=object()
    )

    assert [item["queue_id"] for item in result] == [2, 1]
    assert result[0]["available_agent_count"] == 2
    assert result[1]["available_agent_count"] == 0


@pytest.mark.asyncio
async def test_list_transfer_queues_excludes_ghost_ready_agents(monkeypatch):
    groups = [_group(1, "Sales")]
    monkeypatch.setattr(
        EmployeeGroupRepository,
        "get_paginated",
        AsyncMock(return_value=(groups, 1)),
    )

    async def fake_list_candidates(self, db, r, tenant_id, queue_type, queue_id, task_context=None):
        return [
            QueueCandidate(employee_id=11, available=True),  # connected
            QueueCandidate(employee_id=12, available=True),  # ghost
            QueueCandidate(employee_id=13, available=False),
        ]

    async def fake_connected(r, tenant_id, employee_id):
        return employee_id == 11

    monkeypatch.setattr(
        CallCenterResourceProvider, "list_candidates", fake_list_candidates
    )
    monkeypatch.setattr(
        "app.services.agent_status_service.AgentStatusService.is_connected",
        fake_connected,
    )

    result = await CcAgentStatusService.list_transfer_queues(
        db=None, tenant_id=7, keyword=None, r=object()
    )

    assert result[0]["available_agent_count"] == 1


@pytest.mark.asyncio
async def test_list_transfer_queues_passes_keyword(monkeypatch):
    captured: dict = {}

    async def fake_get_paginated(db, tenant_id, page=1, per_page=10, keyword=None, member_id=None):
        captured["keyword"] = keyword
        captured["page"] = page
        captured["per_page"] = per_page
        captured["tenant_id"] = tenant_id
        return [], 0

    monkeypatch.setattr(EmployeeGroupRepository, "get_paginated", fake_get_paginated)

    await CcAgentStatusService.list_transfer_queues(
        db=None, tenant_id=7, keyword="sales", r=object()
    )

    assert captured["keyword"] == "sales"
    assert captured["tenant_id"] == 7
    assert captured["page"] == 1
    assert captured["per_page"] == 200


@pytest.mark.asyncio
async def test_list_transfer_queues_redis_none_returns_zeros(monkeypatch):
    groups = [_group(1, "Sales"), _group(2, "Support")]
    get_paginated = AsyncMock(return_value=(groups, 2))
    list_candidates = AsyncMock()
    monkeypatch.setattr(EmployeeGroupRepository, "get_paginated", get_paginated)
    monkeypatch.setattr(CallCenterResourceProvider, "list_candidates", list_candidates)

    result = await CcAgentStatusService.list_transfer_queues(
        db=None, tenant_id=7, keyword=None, r=None
    )

    assert len(result) == 2
    assert all(item["available_agent_count"] == 0 for item in result)
    list_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_list_transfer_queues_empty_groups(monkeypatch):
    monkeypatch.setattr(
        EmployeeGroupRepository,
        "get_paginated",
        AsyncMock(return_value=([], 0)),
    )
    list_candidates = AsyncMock()
    monkeypatch.setattr(CallCenterResourceProvider, "list_candidates", list_candidates)

    result = await CcAgentStatusService.list_transfer_queues(
        db=None, tenant_id=7, keyword=None, r=object()
    )

    assert result == []
    list_candidates.assert_not_called()
