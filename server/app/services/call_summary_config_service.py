"""
CallSummaryConfig service - business logic for call summary configuration
"""
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.repositories.call_summary_config_repository import CallSummaryConfigRepository
from app.repositories.fd_field_definition_repository import FdFieldDefinitionRepository
from app.schemas.call_summary_config import (
    CallSummaryConfigFieldCreate,
    CallSummaryConfigFieldUpdate,
    CallSummaryInteractionRuleCreate,
    CallSummaryInteractionRuleUpdate,
    CallSummaryFieldSortRequest,
    CallSummaryRuleSortRequest,
)

CALL_SUMMARY_MODULE = "call_summary"
SHARED_POOL_DOMAIN = "shared_pool"
ALLOWED_CONDITION_LOGICS = {"and", "or"}
ALLOWED_ACTION_STATES = {"hidden", "required", "optional", "readonly"}
NO_VALUE_OPERATORS = {"is_empty", "is_not_empty"}


class CallSummaryConfigService:

    @staticmethod
    async def get_or_create_config(db: AsyncSession, tenant_id: int):
        return await CallSummaryConfigRepository.get_or_create(db, tenant_id)

    @staticmethod
    async def _get_config_id(db: AsyncSession, tenant_id: int) -> int:
        """Get the config id for the tenant, creating it if absent."""
        config = await CallSummaryConfigRepository.get_or_create(db, tenant_id)
        return config.id

    # -- Field management --

    @staticmethod
    async def list_fields(db: AsyncSession, tenant_id: int):
        config = await CallSummaryConfigRepository.get_or_create(db, tenant_id)
        items = await CallSummaryConfigRepository.list_fields(db, config.id)
        return {"items": items, "total": len(items)}

    @staticmethod
    async def _validate_field_payload(
        db: AsyncSession,
        tenant_id: int,
        data: CallSummaryConfigFieldCreate,
    ) -> None:
        if not data.field_definition_id and not data.field_key:
            raise ValidationError("Either field_definition_id or field_key is required")

        if data.field_definition_id is None:
            # System fields for call summary have not been frozen yet. Keep the
            # column reserved, but reject arbitrary keys until constants exist.
            raise ValidationError("System fields are not available for call summary yet")

        definition = await FdFieldDefinitionRepository.get_by_id(db, data.field_definition_id)
        if not definition or definition.tenant_id != tenant_id:
            raise NotFoundError("Field definition not found")
        if definition.domain != SHARED_POOL_DOMAIN:
            raise ValidationError("Only shared pool fields can be added")
        if definition.status != "active":
            raise ValidationError("Only active fields can be added")
        modules = definition.applicable_modules or []
        if CALL_SUMMARY_MODULE not in modules:
            raise ValidationError("Field is not applicable to call summary")

    @staticmethod
    async def add_field(db: AsyncSession, tenant_id: int, data: CallSummaryConfigFieldCreate):
        await CallSummaryConfigService._validate_field_payload(db, tenant_id, data)
        config = await CallSummaryConfigRepository.get_or_create(db, tenant_id)
        existing = await CallSummaryConfigRepository.find_field(
            db,
            config.id,
            data.field_definition_id,
            data.field_key,
        )
        if existing:
            raise ConflictError("Field already exists in call summary config")
        return await CallSummaryConfigRepository.add_field(
            db, config.id, data.model_dump(exclude_unset=True),
        )

    @staticmethod
    async def update_field(
        db: AsyncSession, tenant_id: int, field_id: int, data: CallSummaryConfigFieldUpdate,
    ):
        config_id = await CallSummaryConfigService._get_config_id(db, tenant_id)
        field = await CallSummaryConfigRepository.get_field_by_id(db, field_id)
        if not field or field.config_id != config_id:
            raise NotFoundError("Config field not found")
        return await CallSummaryConfigRepository.update_field(
            db, field, data.model_dump(exclude_unset=True),
        )

    @staticmethod
    async def delete_field(db: AsyncSession, tenant_id: int, field_id: int) -> None:
        config_id = await CallSummaryConfigService._get_config_id(db, tenant_id)
        field = await CallSummaryConfigRepository.get_field_by_id(db, field_id)
        if not field or field.config_id != config_id:
            raise NotFoundError("Config field not found")
        await CallSummaryConfigRepository.delete_field(db, field)

    @staticmethod
    async def sort_fields(db: AsyncSession, tenant_id: int, data: CallSummaryFieldSortRequest) -> None:
        config_id = await CallSummaryConfigService._get_config_id(db, tenant_id)
        await CallSummaryConfigRepository.bulk_update_field_sort(
            db, config_id, [item.model_dump() for item in data.items],
        )

    # -- Interaction Rule management --

    @staticmethod
    async def list_rules(db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 100):
        config = await CallSummaryConfigRepository.get_or_create(db, tenant_id)
        items, total = await CallSummaryConfigRepository.list_rules(db, config.id, page, per_page)
        pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": pages}

    @staticmethod
    async def get_rule(db: AsyncSession, tenant_id: int, rule_id: int):
        config_id = await CallSummaryConfigService._get_config_id(db, tenant_id)
        rule = await CallSummaryConfigRepository.get_rule_by_id(db, rule_id)
        if not rule or rule.config_id != config_id:
            raise NotFoundError("Interaction rule not found")
        return rule

    @staticmethod
    def _field_ref(row: dict[str, Any], *, id_key: str, key_key: str) -> tuple[int | None, str | None]:
        raw_id = row.get(id_key)
        if raw_id is None and id_key == "field_id":
            raw_id = row.get("field_definition_id")
        if raw_id is None and id_key == "target_field_id":
            raw_id = row.get("target_field_definition_id")

        field_id = int(raw_id) if raw_id not in (None, "") else None
        field_key = row.get(key_key)
        if field_key == "":
            field_key = None
        return field_id, field_key

    @staticmethod
    def _value_is_empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        if isinstance(value, (list, tuple, set)):
            return len(value) == 0
        return False

    @staticmethod
    async def _validate_rule_payload(db: AsyncSession, config_id: int, payload: dict[str, Any]) -> None:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValidationError("Rule name is required")
        payload["name"] = name

        if payload.get("condition_logic") not in ALLOWED_CONDITION_LOGICS:
            raise ValidationError("Invalid condition logic")

        conditions = payload.get("conditions") or []
        actions = payload.get("actions") or []
        if not conditions:
            raise ValidationError("At least one condition is required")
        if not actions:
            raise ValidationError("At least one action is required")

        fields = await CallSummaryConfigRepository.list_fields(db, config_id)
        allowed_definition_ids = {f.field_definition_id for f in fields if f.field_definition_id is not None}
        allowed_keys = {f.field_key for f in fields if f.field_key}

        for condition in conditions:
            if not isinstance(condition, dict):
                raise ValidationError("Invalid condition")
            field_id, field_key = CallSummaryConfigService._field_ref(
                condition, id_key="field_id", key_key="field_key",
            )
            if field_id not in allowed_definition_ids and field_key not in allowed_keys:
                raise ValidationError("Condition field is not selected in call summary config")
            operator = str(condition.get("operator") or "").strip()
            if not operator:
                raise ValidationError("Condition operator is required")
            if operator not in NO_VALUE_OPERATORS and CallSummaryConfigService._value_is_empty(condition.get("value")):
                raise ValidationError("Condition value is required")

        seen_targets: set[tuple[str, int | str]] = set()
        for action in actions:
            if not isinstance(action, dict):
                raise ValidationError("Invalid action")
            target_id, target_key = CallSummaryConfigService._field_ref(
                action, id_key="target_field_id", key_key="target_field_key",
            )
            if target_id not in allowed_definition_ids and target_key not in allowed_keys:
                raise ValidationError("Action target field is not selected in call summary config")
            state = str(action.get("state") or "").strip()
            if state not in ALLOWED_ACTION_STATES:
                raise ValidationError("Invalid action state")
            target_marker: tuple[str, int | str]
            if target_id is not None:
                target_marker = ("id", target_id)
            else:
                target_marker = ("key", target_key or "")
            if target_marker in seen_targets:
                raise ValidationError("Action target field cannot be repeated")
            seen_targets.add(target_marker)

    @staticmethod
    async def create_rule(db: AsyncSession, tenant_id: int, data: CallSummaryInteractionRuleCreate):
        config = await CallSummaryConfigRepository.get_or_create(db, tenant_id)
        payload = data.model_dump()
        await CallSummaryConfigService._validate_rule_payload(db, config.id, payload)
        return await CallSummaryConfigRepository.create_rule(db, config.id, payload)

    @staticmethod
    async def update_rule(
        db: AsyncSession, tenant_id: int, rule_id: int, data: CallSummaryInteractionRuleUpdate,
    ):
        config_id = await CallSummaryConfigService._get_config_id(db, tenant_id)
        rule = await CallSummaryConfigRepository.get_rule_by_id(db, rule_id)
        if not rule or rule.config_id != config_id:
            raise NotFoundError("Interaction rule not found")

        update_data = data.model_dump(exclude_unset=True)
        candidate = {
            "name": update_data.get("name", rule.name),
            "condition_logic": update_data.get("condition_logic", rule.condition_logic),
            "conditions": update_data.get("conditions", rule.conditions),
            "actions": update_data.get("actions", rule.actions),
            "is_enabled": update_data.get("is_enabled", rule.is_enabled),
            "sort_order": update_data.get("sort_order", rule.sort_order),
        }
        await CallSummaryConfigService._validate_rule_payload(db, config_id, candidate)
        return await CallSummaryConfigRepository.update_rule(db, rule, update_data)

    @staticmethod
    async def delete_rule(db: AsyncSession, tenant_id: int, rule_id: int) -> None:
        config_id = await CallSummaryConfigService._get_config_id(db, tenant_id)
        rule = await CallSummaryConfigRepository.get_rule_by_id(db, rule_id)
        if not rule or rule.config_id != config_id:
            raise NotFoundError("Interaction rule not found")
        await CallSummaryConfigRepository.delete_rule(db, rule)

    @staticmethod
    async def sort_rules(db: AsyncSession, tenant_id: int, data: CallSummaryRuleSortRequest) -> None:
        config_id = await CallSummaryConfigService._get_config_id(db, tenant_id)
        await CallSummaryConfigRepository.bulk_update_rule_sort(
            db, config_id, [item.model_dump() for item in data.items],
        )
