"""
Integration tests for ticket workflow configuration API.
"""
import uuid

import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _token(tenant_id: int = 7) -> str:
    return create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": ["admin"]})


def _headers(tenant_id: int = 7) -> dict:
    return {"Authorization": f"Bearer {_token(tenant_id)}"}


def _update_priority_graph() -> dict:
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
async def test_ticket_workflow_create_seeds_default_graph(client: AsyncClient):
    response = await client.post(
        "/api/v1/ticket-workflows",
        headers=_headers(),
        json={"name": f"工单流程 {uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["current_version_no"] == 1
    assert [node["type"] for node in body["graph_json"]["nodes"]] == ["trigger", "end"]


@pytest.mark.asyncio
async def test_ticket_workflow_graph_save_bumps_version(client: AsyncClient):
    created = await client.post(
        "/api/v1/ticket-workflows",
        headers=_headers(),
        json={"name": f"工单流程 {uuid.uuid4().hex[:8]}"},
    )
    workflow_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/ticket-workflows/{workflow_id}",
        headers=_headers(),
        json={"graph_json": _update_priority_graph()},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["current_version_no"] == 2


@pytest.mark.asyncio
async def test_ticket_workflow_metadata_save_keeps_current_version(client: AsyncClient):
    created = await client.post(
        "/api/v1/ticket-workflows",
        headers=_headers(),
        json={"name": f"工单流程 {uuid.uuid4().hex[:8]}"},
    )
    workflow_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/ticket-workflows/{workflow_id}",
        headers=_headers(),
        json={"name": "仅更新基础信息", "enabled": True},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["current_version_no"] == created.json()["current_version_no"]

    versions = await client.get(
        f"/api/v1/ticket-workflows/{workflow_id}/versions",
        headers=_headers(),
    )
    assert versions.status_code == 200, versions.text
    assert [item["version_no"] for item in versions.json()["items"]] == [1]


@pytest.mark.asyncio
async def test_ticket_workflow_validate_reports_missing_branch_edge(client: AsyncClient):
    created = await client.post(
        "/api/v1/ticket-workflows",
        headers=_headers(),
        json={"name": f"工单流程 {uuid.uuid4().hex[:8]}"},
    )
    workflow_id = created.json()["id"]
    graph = {
        "version": 1,
        "nodes": [
            {"id": "trigger", "type": "trigger", "data": {"event_types": ["update"], "condition_logic": "AND", "conditions": []}},
            {
                "id": "b1",
                "type": "branch",
                "data": {
                    "branches": [
                        {"id": "a", "name": "A", "is_default": False, "condition_logic": "AND", "conditions": []},
                        {"id": "default", "name": "否则", "is_default": True, "condition_logic": "AND", "conditions": []},
                    ]
                },
            },
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger", "target": "b1", "source_handle": "next"},
            {"id": "e2", "source": "b1", "target": "end", "source_handle": "a"},
        ],
    }
    response = await client.post(
        f"/api/v1/ticket-workflows/{workflow_id}/validate",
        headers=_headers(),
        json={"graph_json": graph},
    )
    assert response.status_code == 200, response.text
    codes = {error["code"] for error in response.json()["errors"]}
    assert "missing_branch_edge" in codes


@pytest.mark.asyncio
async def test_ticket_workflow_validate_rejects_duplicate_outlet_edges(client: AsyncClient):
    created = await client.post(
        "/api/v1/ticket-workflows",
        headers=_headers(),
        json={"name": f"工单流程 {uuid.uuid4().hex[:8]}"},
    )
    workflow_id = created.json()["id"]
    graph = {
        "version": 1,
        "nodes": [
            {"id": "trigger", "type": "trigger", "data": {"event_types": ["update"], "condition_logic": "AND", "conditions": []}},
            {
                "id": "b1",
                "type": "branch",
                "data": {
                    "branches": [
                        {"id": "a", "name": "A", "is_default": False, "condition_logic": "AND", "conditions": []},
                        {"id": "default", "name": "否则", "is_default": True, "condition_logic": "AND", "conditions": []},
                    ]
                },
            },
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger", "target": "b1", "source_handle": "next"},
            {"id": "e2", "source": "trigger", "target": "end", "source_handle": "next"},
            {"id": "e3", "source": "b1", "target": "end", "source_handle": "a"},
            {"id": "e4", "source": "b1", "target": "end", "source_handle": "a"},
            {"id": "e5", "source": "b1", "target": "end", "source_handle": "default"},
        ],
    }
    response = await client.post(
        f"/api/v1/ticket-workflows/{workflow_id}/validate",
        headers=_headers(),
        json={"graph_json": graph},
    )
    assert response.status_code == 200, response.text
    errors = response.json()["errors"]
    duplicate_errors = [error for error in errors if error["code"] == "duplicate_outlet_edge"]
    assert {(error["node_id"], error["field"]) for error in duplicate_errors} == {
        ("trigger", "outlet:next"),
        ("b1", "outlet:a"),
    }
