"""
Unit tests for call summary config service
"""
from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.repositories.call_summary_config_repository import CallSummaryConfigRepository
from app.repositories.fd_field_definition_repository import FdFieldDefinitionRepository
from app.schemas.call_summary_config import CallSummaryConfigFieldCreate
from app.services.call_summary_config_service import CallSummaryConfigService


class TestCallSummaryConfigService:

    @pytest.mark.asyncio
    async def test_validate_field_rejects_non_call_summary_module(self, monkeypatch):
        async def fake_get_by_id(_db, _definition_id):
            return SimpleNamespace(
                tenant_id=1,
                domain="shared_pool",
                status="active",
                applicable_modules=["ticket"],
            )

        monkeypatch.setattr(FdFieldDefinitionRepository, "get_by_id", fake_get_by_id)

        with pytest.raises(ValidationError, match="not applicable"):
            await CallSummaryConfigService._validate_field_payload(
                object(),
                tenant_id=1,
                data=CallSummaryConfigFieldCreate(field_definition_id=10),
            )

    @pytest.mark.asyncio
    async def test_validate_rule_payload_accepts_selected_field_refs(self, monkeypatch):
        async def fake_list_fields(_db, _config_id):
            return [SimpleNamespace(field_definition_id=10, field_key=None)]

        monkeypatch.setattr(CallSummaryConfigRepository, "list_fields", fake_list_fields)

        payload = {
            "name": "VIP lock",
            "condition_logic": "and",
            "conditions": [{"field_id": 10, "operator": "eq", "value": "vip"}],
            "actions": [{"target_field_id": 10, "state": "readonly"}],
        }

        await CallSummaryConfigService._validate_rule_payload(object(), 1, payload)
        assert payload["name"] == "VIP lock"

    @pytest.mark.asyncio
    async def test_validate_rule_payload_rejects_unselected_field_refs(self, monkeypatch):
        async def fake_list_fields(_db, _config_id):
            return [SimpleNamespace(field_definition_id=10, field_key=None)]

        monkeypatch.setattr(CallSummaryConfigRepository, "list_fields", fake_list_fields)

        payload = {
            "name": "Bad ref",
            "condition_logic": "and",
            "conditions": [{"field_id": 99, "operator": "eq", "value": "vip"}],
            "actions": [{"target_field_id": 10, "state": "readonly"}],
        }

        with pytest.raises(ValidationError, match="Condition field"):
            await CallSummaryConfigService._validate_rule_payload(object(), 1, payload)

    @pytest.mark.asyncio
    async def test_validate_rule_payload_rejects_duplicate_action_targets(self, monkeypatch):
        async def fake_list_fields(_db, _config_id):
            return [SimpleNamespace(field_definition_id=10, field_key=None)]

        monkeypatch.setattr(CallSummaryConfigRepository, "list_fields", fake_list_fields)

        payload = {
            "name": "Duplicate targets",
            "condition_logic": "and",
            "conditions": [{"field_id": 10, "operator": "is_not_empty", "value": None}],
            "actions": [
                {"target_field_id": 10, "state": "readonly"},
                {"target_field_id": 10, "state": "hidden"},
            ],
        }

        with pytest.raises(ValidationError, match="cannot be repeated"):
            await CallSummaryConfigService._validate_rule_payload(object(), 1, payload)
