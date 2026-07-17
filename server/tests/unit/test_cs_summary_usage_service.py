"""
Unit tests for session summary usage service.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ForbiddenError
from app.repositories.cs_summary_config_repository import CsSummaryConfigRepository
from app.repositories.cs_summary_usage_repository import CsSummaryUsageRepository
from app.schemas.cs_summary_usage import CsSummaryFieldValueUpdate
from app.schemas.permission import EffectivePrincipal
from app.services.cs_summary_usage_service import CsSummaryUsageService
from app.services.data_scope_service import DataScopeService


def _principal(
    user_id: int = 1,
    tenant_id: int = 1,
    data_scopes: dict[str, str] | None = None,
    group_ids: list[int] | None = None,
) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=user_id,
        tenant_id=tenant_id,
        permissions=["chat.workspace.use"],
        data_scopes=data_scopes or {},
        group_ids=group_ids or [],
    )


def _field(field_definition_id: int, field_type: str = "single_line_text"):
    return SimpleNamespace(
        id=field_definition_id,
        config_id=1,
        field_definition_id=field_definition_id,
        field_key=None,
        sort_order=0,
        is_active=True,
        field_definition=SimpleNamespace(field_type=field_type),
    )


class TestCsSummaryUsageService:

    @pytest.mark.asyncio
    async def test_get_summary_allows_conversation_owner(self, monkeypatch):
        async def fake_get_conversation(_db, conversation_id):
            return SimpleNamespace(id=conversation_id, tenant_id=1, agent_id=1, group_id=None)

        async def fake_get_or_create(_db, tenant_id):
            return SimpleNamespace(id=11, tenant_id=tenant_id)

        async def fake_get_active_fields(_db, _config_id):
            return [_field(10)]

        async def fake_get_enabled_rules(_db, _config_id):
            return []

        async def fake_get_values(_db, _tenant_id, conversation_id):
            return [
                SimpleNamespace(
                    conversation_id=conversation_id,
                    field_definition_id=10,
                    field_key=None,
                    value="done",
                )
            ]

        monkeypatch.setattr(CsSummaryUsageRepository, "get_conversation", fake_get_conversation)
        monkeypatch.setattr(CsSummaryConfigRepository, "get_or_create", fake_get_or_create)
        monkeypatch.setattr(CsSummaryUsageRepository, "get_active_fields", fake_get_active_fields)
        monkeypatch.setattr(CsSummaryUsageRepository, "get_enabled_rules", fake_get_enabled_rules)
        monkeypatch.setattr(CsSummaryUsageRepository, "get_values", fake_get_values)
        monkeypatch.setattr(DataScopeService, "get_group_peer_employee_ids", AsyncMock(return_value=[]))

        result = await CsSummaryUsageService.get_summary(
            object(),
            tenant_id=1,
            conversation_id=100,
            principal=_principal(user_id=1),
        )

        assert result["conversation_id"] == 100
        assert result["values"] == {"10": "done"}

    @pytest.mark.asyncio
    async def test_get_summary_allows_group_scoped_unassigned_conversation(self, monkeypatch):
        async def fake_get_conversation(_db, conversation_id):
            return SimpleNamespace(id=conversation_id, tenant_id=1, agent_id=None, group_id=9)

        async def fake_get_or_create(_db, tenant_id):
            return SimpleNamespace(id=11, tenant_id=tenant_id)

        async def fake_get_active_fields(_db, _config_id):
            return [_field(10)]

        async def fake_get_enabled_rules(_db, _config_id):
            return []

        async def fake_get_values(_db, _tenant_id, _conversation_id):
            return []

        monkeypatch.setattr(CsSummaryUsageRepository, "get_conversation", fake_get_conversation)
        monkeypatch.setattr(CsSummaryConfigRepository, "get_or_create", fake_get_or_create)
        monkeypatch.setattr(CsSummaryUsageRepository, "get_active_fields", fake_get_active_fields)
        monkeypatch.setattr(CsSummaryUsageRepository, "get_enabled_rules", fake_get_enabled_rules)
        monkeypatch.setattr(CsSummaryUsageRepository, "get_values", fake_get_values)
        monkeypatch.setattr(DataScopeService, "get_group_peer_employee_ids", AsyncMock(return_value=[]))

        result = await CsSummaryUsageService.get_summary(
            object(),
            tenant_id=1,
            conversation_id=100,
            principal=_principal(
                user_id=1,
                data_scopes={"session_record": "group"},
                group_ids=[9],
            ),
        )

        assert result["conversation_id"] == 100
        assert result["fields"] == [_field(10)]

    @pytest.mark.asyncio
    async def test_get_summary_rejects_non_owner_for_self_scope(self, monkeypatch):
        async def fake_get_conversation(_db, conversation_id):
            return SimpleNamespace(id=conversation_id, tenant_id=1, agent_id=2, group_id=None)

        monkeypatch.setattr(CsSummaryUsageRepository, "get_conversation", fake_get_conversation)

        with pytest.raises(ForbiddenError, match="Permission denied"):
            await CsSummaryUsageService.get_summary(
                object(),
                tenant_id=1,
                conversation_id=100,
                principal=_principal(user_id=1),
            )

    @pytest.mark.asyncio
    async def test_update_field_rejects_non_owner_before_upsert(self, monkeypatch):
        async def fake_get_conversation(_db, conversation_id):
            return SimpleNamespace(id=conversation_id, tenant_id=1, agent_id=2, group_id=None)

        async def fail_get_or_create(_db, _tenant_id):
            raise AssertionError("config should not load for non-owner")

        monkeypatch.setattr(CsSummaryUsageRepository, "get_conversation", fake_get_conversation)
        monkeypatch.setattr(CsSummaryConfigRepository, "get_or_create", fail_get_or_create)

        with pytest.raises(ForbiddenError, match="Permission denied"):
            await CsSummaryUsageService.update_field(
                object(),
                tenant_id=1,
                conversation_id=100,
                data=CsSummaryFieldValueUpdate(field_definition_id=10, value="x"),
                principal=_principal(user_id=1),
            )
