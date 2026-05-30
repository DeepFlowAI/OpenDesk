"""
Unit tests for call summary usage service.
"""
from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.call_summary_config_repository import CallSummaryConfigRepository
from app.repositories.call_summary_usage_repository import CallSummaryUsageRepository
from app.schemas.call_summary_usage import CallSummaryFieldValueUpdate
from app.services.call_summary_usage_service import CallSummaryUsageService


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


def _rule(*, conditions=None, actions=None, condition_logic: str = "and"):
    return SimpleNamespace(
        id=1,
        config_id=1,
        name="rule",
        condition_logic=condition_logic,
        conditions=conditions or [],
        actions=actions or [],
        is_enabled=True,
        sort_order=0,
    )


class TestCallSummaryUsageService:

    @pytest.mark.asyncio
    async def test_get_summary_returns_fields_rules_and_values(self, monkeypatch):
        async def fake_get_call_record(_db, call_record_id):
            return SimpleNamespace(id=call_record_id, tenant_id=1)

        async def fake_get_or_create(_db, tenant_id):
            return SimpleNamespace(id=11, tenant_id=tenant_id)

        async def fake_get_active_fields(_db, _config_id):
            return [_field(10)]

        async def fake_get_enabled_rules(_db, _config_id):
            return [_rule()]

        async def fake_get_values(_db, _tenant_id, call_record_id):
            return [
                SimpleNamespace(
                    call_record_id=call_record_id,
                    field_definition_id=10,
                    field_key=None,
                    value="done",
                )
            ]

        monkeypatch.setattr(CallSummaryUsageRepository, "get_call_record", fake_get_call_record)
        monkeypatch.setattr(CallSummaryConfigRepository, "get_or_create", fake_get_or_create)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_active_fields", fake_get_active_fields)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_enabled_rules", fake_get_enabled_rules)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_values", fake_get_values)

        result = await CallSummaryUsageService.get_summary(object(), tenant_id=1, call_record_id=100)

        assert result["call_record_id"] == 100
        assert result["fields"][0].field_definition_id == 10
        assert result["rules"][0].name == "rule"
        assert result["values"] == {"10": "done"}

    @pytest.mark.asyncio
    async def test_get_summary_rejects_cross_tenant_call_record(self, monkeypatch):
        async def fake_get_call_record(_db, call_record_id):
            return SimpleNamespace(id=call_record_id, tenant_id=2)

        monkeypatch.setattr(CallSummaryUsageRepository, "get_call_record", fake_get_call_record)

        with pytest.raises(NotFoundError, match="Call record not found"):
            await CallSummaryUsageService.get_summary(object(), tenant_id=1, call_record_id=100)

    @pytest.mark.asyncio
    async def test_update_field_normalizes_number_and_upserts(self, monkeypatch):
        captured = {}

        async def fake_get_call_record(_db, call_record_id):
            return SimpleNamespace(id=call_record_id, tenant_id=1)

        async def fake_get_or_create(_db, tenant_id):
            return SimpleNamespace(id=11, tenant_id=tenant_id)

        async def fake_get_active_fields(_db, _config_id):
            return [_field(10, "number")]

        async def fake_get_values(_db, _tenant_id, _call_record_id):
            return []

        async def fake_get_enabled_rules(_db, _config_id):
            return []

        async def fake_upsert_value(_db, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id=1, **kwargs)

        monkeypatch.setattr(CallSummaryUsageRepository, "get_call_record", fake_get_call_record)
        monkeypatch.setattr(CallSummaryConfigRepository, "get_or_create", fake_get_or_create)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_active_fields", fake_get_active_fields)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_values", fake_get_values)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_enabled_rules", fake_get_enabled_rules)
        monkeypatch.setattr(CallSummaryUsageRepository, "upsert_value", fake_upsert_value)

        result = await CallSummaryUsageService.update_field(
            object(),
            tenant_id=1,
            call_record_id=100,
            data=CallSummaryFieldValueUpdate(field_definition_id=10, value="42.5"),
        )

        assert result.value == 42.5
        assert captured["call_record_id"] == 100
        assert captured["field_definition_id"] == 10

    @pytest.mark.asyncio
    async def test_update_field_rejects_unenabled_field(self, monkeypatch):
        async def fake_get_call_record(_db, call_record_id):
            return SimpleNamespace(id=call_record_id, tenant_id=1)

        async def fake_get_or_create(_db, tenant_id):
            return SimpleNamespace(id=11, tenant_id=tenant_id)

        async def fake_get_active_fields(_db, _config_id):
            return [_field(10)]

        monkeypatch.setattr(CallSummaryUsageRepository, "get_call_record", fake_get_call_record)
        monkeypatch.setattr(CallSummaryConfigRepository, "get_or_create", fake_get_or_create)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_active_fields", fake_get_active_fields)

        with pytest.raises(ValidationError, match="not enabled"):
            await CallSummaryUsageService.update_field(
                object(),
                tenant_id=1,
                call_record_id=100,
                data=CallSummaryFieldValueUpdate(field_definition_id=99, value="x"),
            )

    @pytest.mark.asyncio
    async def test_update_field_rejects_required_empty_value(self, monkeypatch):
        async def fake_get_call_record(_db, call_record_id):
            return SimpleNamespace(id=call_record_id, tenant_id=1)

        async def fake_get_or_create(_db, tenant_id):
            return SimpleNamespace(id=11, tenant_id=tenant_id)

        async def fake_get_active_fields(_db, _config_id):
            return [_field(10)]

        async def fake_get_values(_db, _tenant_id, _call_record_id):
            return []

        async def fake_get_enabled_rules(_db, _config_id):
            return [_rule(actions=[{"target_field_id": 10, "state": "required"}])]

        monkeypatch.setattr(CallSummaryUsageRepository, "get_call_record", fake_get_call_record)
        monkeypatch.setattr(CallSummaryConfigRepository, "get_or_create", fake_get_or_create)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_active_fields", fake_get_active_fields)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_values", fake_get_values)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_enabled_rules", fake_get_enabled_rules)

        with pytest.raises(ValidationError, match="required"):
            await CallSummaryUsageService.update_field(
                object(),
                tenant_id=1,
                call_record_id=100,
                data=CallSummaryFieldValueUpdate(field_definition_id=10, value=""),
            )

    @pytest.mark.asyncio
    async def test_update_field_rejects_hidden_field(self, monkeypatch):
        async def fake_get_call_record(_db, call_record_id):
            return SimpleNamespace(id=call_record_id, tenant_id=1)

        async def fake_get_or_create(_db, tenant_id):
            return SimpleNamespace(id=11, tenant_id=tenant_id)

        async def fake_get_active_fields(_db, _config_id):
            return [_field(10)]

        async def fake_get_values(_db, _tenant_id, _call_record_id):
            return []

        async def fake_get_enabled_rules(_db, _config_id):
            return [_rule(actions=[{"target_field_id": 10, "state": "hidden"}])]

        monkeypatch.setattr(CallSummaryUsageRepository, "get_call_record", fake_get_call_record)
        monkeypatch.setattr(CallSummaryConfigRepository, "get_or_create", fake_get_or_create)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_active_fields", fake_get_active_fields)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_values", fake_get_values)
        monkeypatch.setattr(CallSummaryUsageRepository, "get_enabled_rules", fake_get_enabled_rules)

        with pytest.raises(ValidationError, match="hidden"):
            await CallSummaryUsageService.update_field(
                object(),
                tenant_id=1,
                call_record_id=100,
                data=CallSummaryFieldValueUpdate(field_definition_id=10, value="x"),
            )
