"""
CsSummaryUsage service — business logic for conversation minutes usage
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.cs_summary_config_field import CsSummaryConfigField
from app.repositories.cs_summary_config_repository import CsSummaryConfigRepository
from app.repositories.cs_summary_usage_repository import CsSummaryUsageRepository
from app.schemas.cs_summary_usage import CsSummaryFieldValueUpdate
from app.schemas.permission import EffectivePrincipal


class CsSummaryUsageService:

    @staticmethod
    def _value_key(field_definition_id: int | None, field_key: str | None) -> str:
        return str(field_definition_id) if field_definition_id is not None else str(field_key)

    @staticmethod
    def _is_empty(value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}

    @staticmethod
    def _matches_condition(actual: Any, operator: str, expected: Any) -> bool:
        op = (operator or "eq").lower()
        if op in ("eq", "equals", "="):
            return actual == expected
        if op in ("ne", "not_equals", "!="):
            return actual != expected
        if op in ("contains", "like"):
            if isinstance(actual, list):
                return expected in actual
            return str(expected or "") in str(actual or "")
        if op in ("not_contains", "not_like"):
            if isinstance(actual, list):
                return expected not in actual
            return str(expected or "") not in str(actual or "")
        if op in ("starts_with",):
            return str(actual or "").startswith(str(expected or ""))
        if op in ("ends_with",):
            return str(actual or "").endswith(str(expected or ""))
        if op in ("is_empty", "is_null"):
            return CsSummaryUsageService._is_empty(actual)
        if op in ("is_not_empty", "is_not_null"):
            return not CsSummaryUsageService._is_empty(actual)
        if op in ("in",):
            return actual in expected if isinstance(expected, list) else False
        if op in ("not_in",):
            return actual not in expected if isinstance(expected, list) else True
        try:
            left = Decimal(str(actual))
            right = Decimal(str(expected))
        except (InvalidOperation, ValueError):
            return False
        if op in ("gt", ">"):
            return left > right
        if op in ("gte", ">="):
            return left >= right
        if op in ("lt", "<"):
            return left < right
        if op in ("lte", "<="):
            return left <= right
        return False

    @staticmethod
    def _field_matches(field: CsSummaryConfigField, field_definition_id: int | None, field_key: str | None) -> bool:
        if field_definition_id is not None:
            return field.field_definition_id == field_definition_id
        return field.field_key == field_key

    @staticmethod
    def _find_field(
        fields: list[CsSummaryConfigField],
        field_definition_id: int | None,
        field_key: str | None,
    ) -> CsSummaryConfigField | None:
        for field in fields:
            if CsSummaryUsageService._field_matches(field, field_definition_id, field_key):
                return field
        return None

    @staticmethod
    def _assert_owner_access(conversation, principal: EffectivePrincipal | None) -> None:
        if principal is None:
            return
        if conversation.agent_id != principal.user_id:
            raise ForbiddenError("No permission to access session summary")

    @staticmethod
    def _calculate_states(fields: list[CsSummaryConfigField], rules: list, values: dict[str, Any]) -> dict[str, str]:
        states = {
            CsSummaryUsageService._value_key(field.field_definition_id, field.field_key): "optional"
            for field in fields
        }
        for rule in rules:
            conditions = rule.conditions or []
            if conditions:
                checks = []
                for condition in conditions:
                    key = CsSummaryUsageService._value_key(
                        condition.get("field_id"),
                        condition.get("field_key"),
                    )
                    checks.append(
                        CsSummaryUsageService._matches_condition(
                            values.get(key),
                            condition.get("operator", "eq"),
                            condition.get("value"),
                        )
                    )
                matched = all(checks) if rule.condition_logic != "or" else any(checks)
            else:
                matched = True
            if not matched:
                continue
            for action in rule.actions or []:
                key = CsSummaryUsageService._value_key(
                    action.get("target_field_id"),
                    action.get("target_field_key"),
                )
                if key in states and action.get("state") in {"hidden", "required", "optional", "readonly"}:
                    states[key] = action["state"]
        return states

    @staticmethod
    def _normalize_value(field: CsSummaryConfigField, value: Any) -> Any:
        definition = field.field_definition
        if value == "":
            return None
        if definition is None:
            return value
        field_type = definition.field_type
        if field_type == "number":
            if value is None:
                return None
            try:
                number = Decimal(str(value))
            except (InvalidOperation, ValueError):
                raise ValidationError("Invalid number value")
            return int(number) if number == number.to_integral_value() else float(number)
        if field_type in {"multi_select", "multi_select_tree", "file"}:
            if value is None:
                return None
            if not isinstance(value, list):
                raise ValidationError("Invalid list value")
            return value
        if field_type in {"single_line_text", "multi_line_text", "email", "phone", "url", "time", "single_select", "single_select_tree", "rich_text"}:
            if value is None:
                return None
            return str(value)
        if field_type == "date":
            if value is None:
                return None
            raw = str(value)
            try:
                datetime.fromisoformat(raw[:10])
            except ValueError:
                raise ValidationError("Invalid date value")
            return raw[:10]
        if field_type == "datetime":
            if value is None:
                return None
            raw = str(value)
            try:
                datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                raise ValidationError("Invalid datetime value")
            return raw
        return value

    @staticmethod
    async def get_summary(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        conversation = await CsSummaryUsageRepository.get_conversation(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")
        CsSummaryUsageService._assert_owner_access(conversation, principal)

        config = await CsSummaryConfigRepository.get_or_create(db, tenant_id)
        fields = await CsSummaryUsageRepository.get_active_fields(db, config.id)
        rules = await CsSummaryUsageRepository.get_enabled_rules(db, config.id)
        value_rows = await CsSummaryUsageRepository.get_values(db, tenant_id, conversation_id)
        values = {
            CsSummaryUsageService._value_key(row.field_definition_id, row.field_key): row.value
            for row in value_rows
        }
        return {
            "conversation_id": conversation_id,
            "fields": fields,
            "rules": rules,
            "values": values,
        }

    @staticmethod
    async def update_field(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        data: CsSummaryFieldValueUpdate,
        principal: EffectivePrincipal | None = None,
    ):
        conversation = await CsSummaryUsageRepository.get_conversation(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")
        CsSummaryUsageService._assert_owner_access(conversation, principal)

        config = await CsSummaryConfigRepository.get_or_create(db, tenant_id)
        fields = await CsSummaryUsageRepository.get_active_fields(db, config.id)
        target_field = CsSummaryUsageService._find_field(fields, data.field_definition_id, data.field_key)
        if target_field is None:
            raise ValidationError("Field is not enabled in session summary")

        normalized_value = CsSummaryUsageService._normalize_value(target_field, data.value)
        value_rows = await CsSummaryUsageRepository.get_values(db, tenant_id, conversation_id)
        values = {
            CsSummaryUsageService._value_key(row.field_definition_id, row.field_key): row.value
            for row in value_rows
        }
        target_key = CsSummaryUsageService._value_key(data.field_definition_id, data.field_key)
        values[target_key] = normalized_value

        rules = await CsSummaryUsageRepository.get_enabled_rules(db, config.id)
        states = CsSummaryUsageService._calculate_states(fields, rules, values)
        if states.get(target_key) == "required" and CsSummaryUsageService._is_empty(normalized_value):
            raise ValidationError("This field is required")
        if states.get(target_key) == "hidden":
            raise ValidationError("Field is hidden")

        return await CsSummaryUsageRepository.upsert_value(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            field_definition_id=data.field_definition_id,
            field_key=data.field_key,
            value=normalized_value,
        )

    @staticmethod
    async def update_fields_by_keys(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        fields_by_key: dict[str, Any],
    ) -> dict:
        conversation = await CsSummaryUsageRepository.get_conversation(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")

        if not fields_by_key:
            return {"updated": 0, "warnings": []}

        config = await CsSummaryConfigRepository.get_or_create(db, tenant_id)
        fields = await CsSummaryUsageRepository.get_active_fields(db, config.id)
        field_map: dict[str, CsSummaryConfigField] = {}
        for field in fields:
            if field.field_key:
                field_map[field.field_key] = field
            elif field.field_definition and field.field_definition.field_key:
                field_map[field.field_definition.field_key] = field

        value_rows = await CsSummaryUsageRepository.get_values(db, tenant_id, conversation_id)
        values = {
            CsSummaryUsageService._value_key(row.field_definition_id, row.field_key): row.value
            for row in value_rows
        }
        rules = await CsSummaryUsageRepository.get_enabled_rules(db, config.id)

        updated = 0
        warnings: list[str] = []
        for field_key, raw_value in fields_by_key.items():
            if not isinstance(field_key, str) or not field_key:
                warnings.append("INVALID_SESSION_SUMMARY_FIELD_KEY")
                continue

            target_field = field_map.get(field_key)
            if target_field is None:
                warnings.append(f"UNKNOWN_SESSION_SUMMARY_FIELD:{field_key}")
                continue

            try:
                normalized_value = CsSummaryUsageService._normalize_value(target_field, raw_value)
            except ValidationError:
                warnings.append(f"INVALID_SESSION_SUMMARY_VALUE:{field_key}")
                continue

            target_key = CsSummaryUsageService._value_key(
                target_field.field_definition_id,
                target_field.field_key,
            )
            next_values = {**values, target_key: normalized_value}
            states = CsSummaryUsageService._calculate_states(fields, rules, next_values)
            state = states.get(target_key)
            if state in {"hidden", "readonly"}:
                warnings.append(f"SESSION_SUMMARY_FIELD_NOT_WRITABLE:{field_key}")
                continue
            if state == "required" and CsSummaryUsageService._is_empty(normalized_value):
                warnings.append(f"SESSION_SUMMARY_FIELD_REQUIRED:{field_key}")
                continue

            await CsSummaryUsageRepository.upsert_value(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                field_definition_id=target_field.field_definition_id,
                field_key=target_field.field_key,
                value=normalized_value,
            )
            values[target_key] = normalized_value
            updated += 1

        return {"updated": updated, "warnings": warnings}
