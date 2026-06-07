"""
Unit tests for ticket workflow configuration service.
"""
from types import SimpleNamespace

import pytest

from app.repositories.ticket_workflow_repository import TicketWorkflowRepository
from app.repositories.ticket_workflow_version_repository import TicketWorkflowVersionRepository
from app.schemas.ticket_workflow import TicketWorkflowUpdate
from app.schemas.ticket_workflow_graph import TicketWorkflowGraph, default_graph
from app.services import ticket_workflow_service as workflow_service
from app.services.ticket_workflow_service import TicketWorkflowService


@pytest.mark.asyncio
async def test_update_locks_workflow_when_creating_graph_version(monkeypatch):
    lock_flags: list[bool] = []

    async def get_by_id(_db, workflow_id, _tenant_id, for_update=False):
        lock_flags.append(for_update)
        return SimpleNamespace(id=workflow_id)

    async def validate_graph(*_args):
        return []

    async def latest_version(*_args):
        return 1

    async def create_version(_db, data):
        return SimpleNamespace(id=20, version_no=data["version_no"])

    async def update_row(_db, row, data):
        row.current_version_id = data["current_version_id"]
        return row

    async def get_detail(*_args):
        return {"id": 5, "current_version_no": 2}

    monkeypatch.setattr(TicketWorkflowRepository, "get_by_id", get_by_id)
    monkeypatch.setattr(TicketWorkflowService, "_validate_graph", validate_graph)
    monkeypatch.setattr(TicketWorkflowVersionRepository, "get_latest_version_no", latest_version)
    monkeypatch.setattr(TicketWorkflowVersionRepository, "create", create_version)
    monkeypatch.setattr(TicketWorkflowRepository, "update", update_row)
    monkeypatch.setattr(TicketWorkflowService, "get_by_id", get_detail)

    result = await TicketWorkflowService.update(
        None,
        workflow_id=5,
        tenant_id=7,
        actor={},
        data=TicketWorkflowUpdate(graph_json=TicketWorkflowGraph.model_validate(default_graph())),
    )

    assert lock_flags == [True]
    assert result["current_version_no"] == 2


@pytest.mark.asyncio
async def test_update_metadata_does_not_lock_or_create_graph_version(monkeypatch):
    lock_flags: list[bool] = []
    created_versions: list[dict] = []

    async def get_by_id(_db, workflow_id, _tenant_id, for_update=False):
        lock_flags.append(for_update)
        return SimpleNamespace(id=workflow_id)

    async def create_version(_db, data):
        created_versions.append(data)
        return SimpleNamespace(id=20)

    async def update_row(_db, row, data):
        row.name = data["name"]
        return row

    async def get_detail(*_args):
        return {"id": 5, "current_version_no": 1}

    monkeypatch.setattr(TicketWorkflowRepository, "get_by_id", get_by_id)
    monkeypatch.setattr(TicketWorkflowVersionRepository, "create", create_version)
    monkeypatch.setattr(TicketWorkflowRepository, "update", update_row)
    monkeypatch.setattr(TicketWorkflowService, "get_by_id", get_detail)

    result = await TicketWorkflowService.update(
        None,
        workflow_id=5,
        tenant_id=7,
        actor={},
        data=TicketWorkflowUpdate(name="只改名称"),
    )

    assert lock_flags == [False]
    assert created_versions == []
    assert result["current_version_no"] == 1


def test_custom_field_with_key_is_writable():
    field = {
        "id": 123,
        "key": "urgency",
        "source": "custom",
        "field_type": "single_select",
        "type_config": {},
    }

    assert workflow_service._is_writable_field(field) is True
