"""
Welcome message rule service.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.channel import Channel
from app.models.welcome_message_rule import WelcomeMessageRule
from app.repositories.channel_repository import ChannelRepository
from app.repositories.welcome_message_rule_repository import WelcomeMessageRuleRepository
from app.schemas.welcome_message_rule import (
    WelcomeMessageCondition,
    WelcomeMessageRuleCreate,
    WelcomeMessageRuleUpdate,
)


class WelcomeMessageRuleService:
    @staticmethod
    def _rule_to_list_item(rule: WelcomeMessageRule) -> dict:
        return {
            "id": rule.id,
            "priority": rule.priority,
            "name": rule.name,
            "enabled": rule.enabled,
            "conditions": list(rule.conditions) if rule.conditions else [],
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    @staticmethod
    def _rule_to_response(rule: WelcomeMessageRule) -> dict:
        data = WelcomeMessageRuleService._rule_to_list_item(rule)
        data["content"] = rule.content
        return data

    @staticmethod
    async def _ensure_channel(db: AsyncSession, tenant_id: int, raw_id: str) -> None:
        if not raw_id.isdigit() or int(raw_id) < 1:
            raise ValidationError("Web SDK channel id must be a positive integer")
        channel = await ChannelRepository.get_by_id(db, int(raw_id))
        if not channel or channel.tenant_id != tenant_id:
            raise ValidationError("Web SDK channel not found for current tenant")

    @staticmethod
    async def _validate_conditions(
        db: AsyncSession,
        tenant_id: int,
        conditions: list[WelcomeMessageCondition],
    ) -> list[dict]:
        out: list[dict] = []
        for condition in conditions:
            data = condition.model_dump()
            if condition.condition_type == "web_sdk":
                values = condition.value if isinstance(condition.value, list) else [condition.value]
                for value in values:
                    await WelcomeMessageRuleService._ensure_channel(db, tenant_id, str(value))
            out.append(data)
        return out

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        rows, total = await WelcomeMessageRuleRepository.get_paginated(db, tenant_id, page, per_page)
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": [WelcomeMessageRuleService._rule_to_list_item(rule) for rule in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, rule_id: int, tenant_id: int) -> dict:
        rule = await WelcomeMessageRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not rule:
            raise NotFoundError("Welcome message rule not found")
        return WelcomeMessageRuleService._rule_to_response(rule)

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: WelcomeMessageRuleCreate) -> dict:
        conditions = await WelcomeMessageRuleService._validate_conditions(db, tenant_id, data.conditions)
        next_priority = await WelcomeMessageRuleRepository.max_priority(db, tenant_id) + 1
        rule = await WelcomeMessageRuleRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "priority": next_priority,
                "name": data.name,
                "enabled": data.enabled,
                "conditions": conditions,
                "content": data.content,
            },
        )
        return WelcomeMessageRuleService._rule_to_response(rule)

    @staticmethod
    async def update(
        db: AsyncSession,
        rule_id: int,
        tenant_id: int,
        data: WelcomeMessageRuleUpdate,
    ) -> dict:
        rule = await WelcomeMessageRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not rule:
            raise NotFoundError("Welcome message rule not found")
        conditions = await WelcomeMessageRuleService._validate_conditions(db, tenant_id, data.conditions)
        rule = await WelcomeMessageRuleRepository.update(
            db,
            rule,
            {
                "name": data.name,
                "enabled": data.enabled,
                "conditions": conditions,
                "content": data.content,
            },
        )
        return WelcomeMessageRuleService._rule_to_response(rule)

    @staticmethod
    async def patch_enabled(db: AsyncSession, rule_id: int, tenant_id: int, enabled: bool) -> dict:
        rule = await WelcomeMessageRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not rule:
            raise NotFoundError("Welcome message rule not found")
        rule = await WelcomeMessageRuleRepository.update(db, rule, {"enabled": enabled})
        return WelcomeMessageRuleService._rule_to_response(rule)

    @staticmethod
    async def delete(db: AsyncSession, rule_id: int, tenant_id: int) -> None:
        rule = await WelcomeMessageRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not rule:
            raise NotFoundError("Welcome message rule not found")
        await WelcomeMessageRuleRepository.delete(db, rule)

    @staticmethod
    async def reorder(db: AsyncSession, tenant_id: int, ordered_ids: list[int]) -> None:
        existing = await WelcomeMessageRuleRepository.list_all_ids_ordered(db, tenant_id)
        if set(ordered_ids) != set(existing) or len(ordered_ids) != len(existing):
            raise ValidationError("ordered_ids must match all welcome message rules for this tenant")
        id_to_priority = {rule_id: index for index, rule_id in enumerate(ordered_ids, start=1)}
        await WelcomeMessageRuleRepository.set_priorities(db, tenant_id, id_to_priority)

    @staticmethod
    def _condition_matches(condition: dict, channel: Channel) -> bool:
        condition_type = condition.get("condition_type")
        operator = condition.get("operator")
        value = condition.get("value")

        if condition_type == "channel":
            actual = "websdk" if channel.channel_type in ("web", "websdk", "sdk") else channel.channel_type
            matched = actual == value
            return matched if operator == "eq" else not matched

        if condition_type == "web_sdk":
            actual = str(channel.id)
            if operator == "eq":
                return actual == str(value)
            if operator == "ne":
                return actual != str(value)
            values = [str(item) for item in value] if isinstance(value, list) else [str(value)]
            matched = actual in values
            return matched if operator == "any_eq" else not matched

        return False

    @staticmethod
    def _rule_matches(rule: WelcomeMessageRule, channel: Channel) -> bool:
        conditions = list(rule.conditions) if rule.conditions else []
        if not conditions:
            return True
        return all(WelcomeMessageRuleService._condition_matches(condition, channel) for condition in conditions)

    @staticmethod
    async def match_public_welcome_message(db: AsyncSession, channel: Channel) -> dict | None:
        rules = await WelcomeMessageRuleRepository.list_enabled_ordered(db, channel.tenant_id)
        for rule in rules:
            if WelcomeMessageRuleService._rule_matches(rule, channel):
                return {"id": rule.id, "name": rule.name, "content": rule.content}
        return None
