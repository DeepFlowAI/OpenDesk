"""Unit tests for list/export query optimizations."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Date, DateTime, Index, Integer

from app.models.organization import Organization
from app.models.ticket import Ticket
from app.models.user import User
from app.repositories.organization_repository import (
    OrganizationRepository,
    _build_condition_clause as org_clause,
)
from app.repositories.ticket_repository import (
    TicketRepository,
    _build_condition_clause as ticket_clause,
)
from app.repositories.user_repository import _build_condition_clause as user_clause
from app.schemas.organization import OrganizationQueryRequest
from app.services.organization_service import OrganizationService


class _Col:
    def __init__(self, col_type):
        self.type = col_type

    def is_(self, value):
        return ("is", value)

    def isnot(self, value):
        return ("isnot", value)


def test_empty_operators_use_null_only_for_numbers_and_dates():
    for clause in (ticket_clause, user_clause, org_clause):
        assert clause(_Col(Integer()), "is_empty", None) == ("is", None)
        assert clause(_Col(Date()), "is_not_empty", None) == ("isnot", None)
        assert clause(_Col(DateTime()), "is_null", None) == ("is", None)


def test_empty_operators_keep_cast_for_text_columns():
    compiled = str(ticket_clause(Ticket.title, "is_empty", None))
    assert "IS NULL" in compiled
    assert compiled.count("CAST") == 1


@pytest.mark.asyncio
async def test_count_users_by_org_ids_skips_empty_set():
    db = SimpleNamespace(execute=AsyncMock())
    assert await OrganizationRepository.count_users_by_org_ids(db, 1, []) == {}
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_organizations_batches_user_counts(monkeypatch):
    org = SimpleNamespace(id=10)
    count_users = AsyncMock(return_value={10: 2})

    monkeypatch.setattr(OrganizationService, "_get_slot_map", AsyncMock(return_value={}))
    monkeypatch.setattr(OrganizationService, "_get_field_key_slot_map", AsyncMock(return_value={}))
    monkeypatch.setattr(
        OrganizationRepository,
        "query_paginated",
        AsyncMock(return_value=([org], 1)),
    )
    monkeypatch.setattr(OrganizationRepository, "count_users_by_org_ids", count_users)
    monkeypatch.setattr(
        OrganizationService,
        "_enrich_response",
        lambda item, _slots, user_count=0: {"id": item.id, "user_count": user_count},
    )

    result = await OrganizationService.query_organizations(
        SimpleNamespace(get=AsyncMock(return_value=None)),
        1,
        OrganizationQueryRequest(),
    )

    count_users.assert_awaited_once()
    assert result["items"][0]["user_count"] == 2


def test_user_and_org_models_keep_search_columns():
    assert hasattr(User, "public_id") and hasattr(User, "external_id")
    assert hasattr(Organization, "public_id") and hasattr(Organization, "name")
    assert hasattr(Ticket, "title") and hasattr(Ticket, "ticket_number")


def _index_names(model) -> set[str]:
    return {arg.name for arg in model.__table_args__ if isinstance(arg, Index)}


def test_list_export_indexes_declared_on_models():
    ticket_indexes = _index_names(Ticket)
    user_indexes = _index_names(User)
    org_indexes = _index_names(Organization)

    assert {
        "ix_tickets_tenant_updated_id",
        "ix_tickets_title_trgm",
        "ix_tickets_ticket_number_trgm",
    } <= ticket_indexes
    assert "ix_tickets_description_trgm" not in ticket_indexes

    assert {
        "ix_users_tenant_created_id",
        "ix_users_tenant_organization_id",
        "ix_users_public_id_trgm",
        "ix_users_name_trgm",
        "ix_users_external_id_trgm",
    } <= user_indexes

    assert {
        "ix_organizations_tenant_updated_id",
        "ix_organizations_public_id_trgm",
        "ix_organizations_name_trgm",
    } <= org_indexes
    assert "ix_organizations_tenant_created_id" not in org_indexes
    assert "ix_organizations_description_trgm" not in org_indexes


class _CaptureDb:
    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(
            scalar_one=lambda: 0,
            scalars=lambda: SimpleNamespace(all=lambda: []),
            all=lambda: [],
        )


def _compiled_sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_ticket_search_or_omits_description():
    db = _CaptureDb()
    await TicketRepository.query_paginated(
        db, 1, search="kw", include_count=False, ids_only=True
    )
    sql = _compiled_sql(db.statements[0])
    assert "tickets.title" in sql
    assert "tickets.ticket_number" in sql
    assert "description" not in sql

    db = _CaptureDb()
    await TicketRepository.aggregate_by_group_field(
        db, 1, group_field_col="status", search="kw"
    )
    sql = _compiled_sql(db.statements[0])
    assert "tickets.title" in sql
    assert "tickets.ticket_number" in sql
    assert "description" not in sql


@pytest.mark.asyncio
async def test_organization_search_or_omits_description():
    db = _CaptureDb()
    await OrganizationRepository.query_paginated(
        db, 1, search="kw", include_count=False, ids_only=True
    )
    sql = _compiled_sql(db.statements[0])
    assert "organizations.public_id" in sql
    assert "organizations.name" in sql
    assert "description" not in sql

    db = _CaptureDb()
    await OrganizationRepository.aggregate_by_group_field(
        db, 1, group_field_col="name", search="kw"
    )
    sql = _compiled_sql(db.statements[0])
    assert "organizations.public_id" in sql
    assert "organizations.name" in sql
    assert "description" not in sql
