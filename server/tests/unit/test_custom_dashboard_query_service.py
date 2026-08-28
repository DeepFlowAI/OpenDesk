"""Unit tests for ticket data-scope and query capability enforcement."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ValidationError
from app.models.ticket import Ticket
from app.repositories.dashboard_ticket_query_repository import DashboardTicketQueryRepository
from app.schemas.permission import EffectivePrincipal
from app.services.custom_dashboard_query_service import (
    CustomDashboardQueryService,
    DashboardField,
    _coerce_value,
)
from app.services.data_scope_service import DataScopeService


def _principal(scope: str = "self") -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=9,
        tenant_id=7,
        permissions=["ticket.workspace.view", "report.dashboard.view"],
        data_scopes={"ticket": scope},
        group_ids=[3],
    )


def test_tenant_date_end_uses_end_of_local_day():
    field = DashboardField(
        ref="system:created_at",
        name="created_at",
        field_type="datetime",
        column=Ticket.created_at,
    )

    value = _coerce_value(field, "2026-08-26", "lte", "Asia/Shanghai")

    assert value.isoformat() == "2026-08-26T15:59:59.999999+00:00"


@pytest.mark.asyncio
async def test_count_always_passes_ticket_scope_clause(monkeypatch):
    captured_clauses: list = []
    monkeypatch.setattr(
        DashboardTicketQueryRepository,
        "list_field_definitions",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        DataScopeService,
        "get_group_peer_employee_ids",
        AsyncMock(return_value=[]),
    )

    async def count(_db, tenant_id, clauses):
        assert tenant_id == 7
        captured_clauses.extend(clauses)
        return 4

    monkeypatch.setattr(DashboardTicketQueryRepository, "count", count)

    result = await CustomDashboardQueryService.execute(
        AsyncMock(),
        _principal("self"),
        method="count",
        params={"where": {"system:status": {"eq": "open"}}},
        filter_config=[],
        filter_values={},
        timezone_name="Asia/Shanghai",
    )

    assert result == 4
    assert len(captured_clauses) == 2
    assert "tickets.agent_id" in str(captured_clauses[0])


@pytest.mark.asyncio
async def test_count_rejects_candidate_range_over_limit(monkeypatch):
    monkeypatch.setattr(
        DashboardTicketQueryRepository,
        "list_field_definitions",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        DataScopeService,
        "get_group_peer_employee_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        DashboardTicketQueryRepository,
        "count",
        AsyncMock(return_value=200_001),
    )

    with pytest.raises(ValidationError, match="candidate range"):
        await CustomDashboardQueryService.execute(
            AsyncMock(),
            _principal("all"),
            method="count",
            params={},
            filter_config=[],
            filter_values={},
            timezone_name="UTC",
        )


@pytest.mark.asyncio
async def test_group_by_maps_inactive_option_label(monkeypatch):
    definition = SimpleNamespace(
        field_key="customer_level",
        slot_column="str_1",
        name="客户等级",
        field_type="single_select",
        status="active",
        type_config={},
        options=[SimpleNamespace(value="vip", label="VIP", is_active=False)],
    )
    monkeypatch.setattr(
        DashboardTicketQueryRepository,
        "list_field_definitions",
        AsyncMock(return_value=[definition]),
    )
    monkeypatch.setattr(
        DataScopeService,
        "get_group_peer_employee_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        DashboardTicketQueryRepository,
        "candidate_count",
        AsyncMock(return_value=10),
    )
    monkeypatch.setattr(
        DashboardTicketQueryRepository,
        "group_by",
        AsyncMock(return_value=[{"key": "vip", "value": 3}]),
    )

    result = await CustomDashboardQueryService.execute(
        AsyncMock(),
        _principal("all"),
        method="group_by",
        params={"group_field": "custom:customer_level"},
        filter_config=[],
        filter_values={},
        timezone_name="UTC",
    )

    assert result == [{"key": "vip", "value": 3, "label": "VIP（已停用）"}]
