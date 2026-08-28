"""
Unit tests for CcAgentStatusService.list_consultable_agents.

The workspace-agent lookup and the batched status read are mocked; only the
service-layer composition is exercised (self-exclusion is delegated to the
repository, status mapping with an offline default, and name resolution).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.agent_status_repository import AgentStatusRepository
from app.repositories.sip_extension_repository import SipExtensionRepository
from app.services.cc_agent_status_service import CcAgentStatusService


def _employee(emp_id: int, **overrides):
    base = dict(
        id=emp_id,
        display_name=None,
        name=f"Agent {emp_id}",
        username=f"agent{emp_id}",
        avatar=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _db_stub(devices=(), memberships=()):
    """db stub answering the device + group-membership batch queries.

    ``devices``: iterable of SimpleNamespace(employee_id, device_type).
    ``memberships``: iterable of (employee_id, group_name) tuples.
    """
    device_rows = SimpleNamespace(all=lambda: list(devices))
    device_result = SimpleNamespace(scalars=lambda: device_rows)
    membership_result = SimpleNamespace(all=lambda: list(memberships))
    db = SimpleNamespace()
    db.execute = AsyncMock(side_effect=[device_result, membership_result])
    return db


@pytest.mark.asyncio
async def test_list_consultable_agents_maps_status_and_defaults_offline(monkeypatch):
    employees = [_employee(2, avatar="a2.png"), _employee(3)]
    monkeypatch.setattr(
        SipExtensionRepository,
        "list_workspace_agents",
        AsyncMock(return_value=employees),
    )
    # Only agent 2 has a status row; agent 3 must default to offline.
    monkeypatch.setattr(
        AgentStatusRepository,
        "list_for_employees",
        AsyncMock(
            return_value=[SimpleNamespace(employee_id=2, status="after_call_work")]
        ),
    )

    result = await CcAgentStatusService.list_consultable_agents(
        db=_db_stub(), tenant_id=7, actor_employee_id=1, keyword=None
    )

    assert result == [
        {
            "employee_id": 2,
            "name": "Agent 2",
            "avatar": "a2.png",
            "status": "after_call_work",
            "group_names": [],
        },
        {
            "employee_id": 3,
            "name": "Agent 3",
            "avatar": None,
            "status": "offline",
            "group_names": [],
        },
    ]


@pytest.mark.asyncio
async def test_list_consultable_agents_excludes_self_via_repository(monkeypatch):
    captured: dict = {}

    async def fake_list_workspace_agents(db, tenant_id, keyword, exclude_employee_id):
        captured["exclude_employee_id"] = exclude_employee_id
        captured["keyword"] = keyword
        return []

    monkeypatch.setattr(
        SipExtensionRepository, "list_workspace_agents", fake_list_workspace_agents
    )
    monkeypatch.setattr(
        AgentStatusRepository, "list_for_employees", AsyncMock(return_value=[])
    )

    await CcAgentStatusService.list_consultable_agents(
        db=None, tenant_id=7, actor_employee_id=42, keyword="li"
    )

    assert captured["exclude_employee_id"] == 42
    assert captured["keyword"] == "li"


@pytest.mark.asyncio
async def test_list_consultable_agents_downgrades_disconnected_to_offline(monkeypatch):
    """A colleague whose browser is gone shows offline even if the DB still
    records their last-chosen 'ready' — otherwise they'd be a dead target."""

    monkeypatch.setattr(
        SipExtensionRepository,
        "list_workspace_agents",
        AsyncMock(return_value=[_employee(2), _employee(3)]),
    )
    monkeypatch.setattr(
        AgentStatusRepository,
        "list_for_employees",
        AsyncMock(
            return_value=[
                SimpleNamespace(employee_id=2, status="ready"),
                SimpleNamespace(employee_id=3, status="ready"),
            ]
        ),
    )
    # Agent 2 is still connected; agent 3 has disconnected.
    from app.services.agent_status_service import AgentStatusService

    async def fake_is_connected(_r, _tenant_id, employee_id):
        return employee_id == 2

    monkeypatch.setattr(
        AgentStatusService, "is_connected", staticmethod(fake_is_connected)
    )

    result = await CcAgentStatusService.list_consultable_agents(
        db=_db_stub(), tenant_id=7, actor_employee_id=1, keyword=None, r=object()
    )

    by_id = {a["employee_id"]: a["status"] for a in result}
    assert by_id == {2: "ready", 3: "offline"}


@pytest.mark.asyncio
async def test_list_consultable_agents_keeps_sip_phone_status_without_socket(monkeypatch):
    """SIP-phone agents ring on the handset, not the browser — a missing
    Socket.IO connection must NOT downgrade them to offline, or colleagues
    can never pick them as a consult/transfer target."""

    monkeypatch.setattr(
        SipExtensionRepository,
        "list_workspace_agents",
        AsyncMock(return_value=[_employee(2), _employee(3)]),
    )
    monkeypatch.setattr(
        AgentStatusRepository,
        "list_for_employees",
        AsyncMock(
            return_value=[
                SimpleNamespace(employee_id=2, status="ready"),
                SimpleNamespace(employee_id=3, status="ready"),
            ]
        ),
    )
    from app.services.agent_status_service import AgentStatusService

    # Nobody has a browser connection.
    monkeypatch.setattr(
        AgentStatusService, "is_connected", staticmethod(AsyncMock(return_value=False))
    )

    db = _db_stub(
        devices=[SimpleNamespace(employee_id=3, device_type="sip_phone")],
    )
    result = await CcAgentStatusService.list_consultable_agents(
        db=db, tenant_id=7, actor_employee_id=1, keyword=None, r=object()
    )

    by_id = {a["employee_id"]: a["status"] for a in result}
    # Agent 2 (web phone) downgrades; agent 3 (SIP handset) keeps ready.
    assert by_id == {2: "offline", 3: "ready"}


@pytest.mark.asyncio
async def test_list_consultable_agents_includes_group_names(monkeypatch):
    monkeypatch.setattr(
        SipExtensionRepository,
        "list_workspace_agents",
        AsyncMock(return_value=[_employee(2), _employee(3)]),
    )
    monkeypatch.setattr(
        AgentStatusRepository,
        "list_for_employees",
        AsyncMock(return_value=[]),
    )

    db = _db_stub(memberships=[(2, "售后一组"), (2, "VIP 队列"), (3, "售后一组")])
    result = await CcAgentStatusService.list_consultable_agents(
        db=db, tenant_id=7, actor_employee_id=1, keyword=None
    )

    groups_by_id = {a["employee_id"]: a["group_names"] for a in result}
    assert groups_by_id == {2: ["VIP 队列", "售后一组"], 3: ["售后一组"]}


@pytest.mark.asyncio
async def test_list_consultable_agents_prefers_display_name(monkeypatch):
    monkeypatch.setattr(
        SipExtensionRepository,
        "list_workspace_agents",
        AsyncMock(return_value=[_employee(5, display_name="小李", name="Li")]),
    )
    monkeypatch.setattr(
        AgentStatusRepository,
        "list_for_employees",
        AsyncMock(return_value=[SimpleNamespace(employee_id=5, status="ready")]),
    )

    result = await CcAgentStatusService.list_consultable_agents(
        db=_db_stub(), tenant_id=7, actor_employee_id=1, keyword=None
    )

    assert result[0]["name"] == "小李"
    assert result[0]["status"] == "ready"
