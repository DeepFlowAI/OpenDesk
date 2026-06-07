"""
Unit tests for ticket workflow runtime execution.
"""
import logging
from types import SimpleNamespace

import pytest

from app.services import ticket_workflow_execution_service as runtime
from app.services.ticket_workflow_execution_service import TicketWorkflowExecutionService


def _workflow(graph: dict, workflow_id: int = 1, version_id: int = 10, version_no: int = 1):
    return SimpleNamespace(
        id=workflow_id,
        current_version=SimpleNamespace(
            id=version_id,
            version_no=version_no,
            graph_json=graph,
        ),
    )


def _graph() -> dict:
    return {
        "version": 1,
        "nodes": [
            {
                "id": "trigger",
                "type": "trigger",
                "data": {
                    "event_types": ["create", "update"],
                    "condition_logic": "AND",
                    "conditions": [
                        {
                            "field_key": "status",
                            "field_id": None,
                            "value_scope": "current",
                            "operator": "eq",
                            "value": "open",
                        }
                    ],
                },
            },
            {
                "id": "u1",
                "type": "update_record",
                "data": {
                    "operations": [
                        {
                            "target_field_key": "priority",
                            "target_field_id": None,
                            "action": "set",
                            "value": "high",
                        }
                    ]
                },
            },
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger", "target": "u1", "source_handle": "next"},
            {"id": "e2", "source": "u1", "target": "end", "source_handle": "next"},
        ],
    }


@pytest.mark.asyncio
async def test_apply_updates_working_ticket_when_trigger_matches(monkeypatch):
    async def list_enabled(_db, _tenant_id):
        return [_workflow(_graph())]

    async def load_fields(_db, _tenant_id):
        return {}, {
            "status": runtime.RuntimeField("key:status", "状态", "single_select", "status"),
            "priority": runtime.RuntimeField("key:priority", "优先级", "single_select", "priority"),
        }

    monkeypatch.setattr(runtime.TicketWorkflowRepository, "list_enabled_for_execution", list_enabled)
    monkeypatch.setattr(runtime, "_load_runtime_fields", load_fields)

    result = await TicketWorkflowExecutionService.apply(
        None,
        tenant_id=7,
        event_type="create",
        before_data={},
        current_data={"status": "open", "priority": "medium"},
    )

    assert result.updates == {"priority": "high"}
    assert result.field_labels == {"priority": "优先级"}


@pytest.mark.asyncio
async def test_apply_skips_when_trigger_does_not_match(monkeypatch):
    async def list_enabled(_db, _tenant_id):
        return [_workflow(_graph())]

    async def load_fields(_db, _tenant_id):
        return {}, {
            "status": runtime.RuntimeField("key:status", "状态", "single_select", "status"),
            "priority": runtime.RuntimeField("key:priority", "优先级", "single_select", "priority"),
        }

    monkeypatch.setattr(runtime.TicketWorkflowRepository, "list_enabled_for_execution", list_enabled)
    monkeypatch.setattr(runtime, "_load_runtime_fields", load_fields)

    result = await TicketWorkflowExecutionService.apply(
        None,
        tenant_id=7,
        event_type="create",
        before_data={},
        current_data={"status": "resolved", "priority": "medium"},
    )

    assert result.updates == {}


@pytest.mark.asyncio
async def test_apply_skips_invalid_workflow_and_continues(monkeypatch, caplog):
    async def list_enabled(_db, _tenant_id):
        return [
            _workflow({"version": 1, "nodes": []}, workflow_id=101, version_id=201),
            _workflow(_graph(), workflow_id=102, version_id=202),
        ]

    async def load_fields(_db, _tenant_id):
        return {}, {
            "status": runtime.RuntimeField("key:status", "状态", "single_select", "status"),
            "priority": runtime.RuntimeField("key:priority", "优先级", "single_select", "priority"),
        }

    monkeypatch.setattr(runtime.TicketWorkflowRepository, "list_enabled_for_execution", list_enabled)
    monkeypatch.setattr(runtime, "_load_runtime_fields", load_fields)
    caplog.set_level(logging.ERROR)

    result = await TicketWorkflowExecutionService.apply(
        None,
        tenant_id=7,
        event_type="create",
        before_data={},
        current_data={"status": "open", "priority": "medium"},
    )

    assert result.updates == {"priority": "high"}
    assert any(
        "Ticket workflow execution skipped tenant_id=7 workflow_id=101 version_id=201" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_apply_discards_partial_working_changes_from_failed_workflow(monkeypatch):
    bad_graph = _graph()
    bad_graph["version"] = 99
    original_execute_graph = runtime._execute_graph

    async def list_enabled(_db, _tenant_id):
        return [
            _workflow(bad_graph, workflow_id=101, version_id=201),
            _workflow(_graph(), workflow_id=102, version_id=202),
        ]

    async def load_fields(_db, _tenant_id):
        return {}, {
            "status": runtime.RuntimeField("key:status", "状态", "single_select", "status"),
            "priority": runtime.RuntimeField("key:priority", "优先级", "single_select", "priority"),
        }

    async def execute_graph(graph, event_type, before_data, working, fields_by_id, fields_by_key):
        if graph.version == 99:
            working["status"] = "open"
            raise RuntimeError("workflow crashed after a partial write")
        return await original_execute_graph(graph, event_type, before_data, working, fields_by_id, fields_by_key)

    monkeypatch.setattr(runtime.TicketWorkflowRepository, "list_enabled_for_execution", list_enabled)
    monkeypatch.setattr(runtime, "_load_runtime_fields", load_fields)
    monkeypatch.setattr(runtime, "_execute_graph", execute_graph)

    result = await TicketWorkflowExecutionService.apply(
        None,
        tenant_id=7,
        event_type="create",
        before_data={},
        current_data={"status": "resolved", "priority": "medium"},
    )

    assert result.updates == {}


@pytest.mark.asyncio
async def test_load_runtime_fields_indexes_custom_field_by_id(monkeypatch):
    async def unified_list(_db, _tenant_id, _domain, include_metadata=False):
        return {
            "items": [
                {
                    "id": 99,
                    "key": "urgency",
                    "source": "custom",
                    "name": "紧急程度",
                    "field_type": "single_select",
                    "slot_column": "str_1",
                    "status": "active",
                },
            ],
        }

    monkeypatch.setattr(runtime.FdFieldDefinitionService, "get_unified_list", unified_list)

    fields_by_id, fields_by_key = await runtime._load_runtime_fields(None, tenant_id=7)

    assert fields_by_id[99].column == "str_1"
    assert fields_by_id[99].slot_column == "str_1"
    assert "urgency" not in fields_by_key
