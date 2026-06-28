"""
Conversation announcement rule service.
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.channel import Channel
from app.models.conversation_announcement_rule import ConversationAnnouncementRule
from app.repositories.channel_repository import ChannelRepository
from app.repositories.conversation_announcement_rule_repository import ConversationAnnouncementRuleRepository
from app.schemas.conversation_announcement_rule import (
    AnnouncementTimeStatus,
    ConversationAnnouncementRuleCreate,
    ConversationAnnouncementRuleUpdate,
)
from app.schemas.welcome_message_rule import WelcomeMessageCondition


class ConversationAnnouncementRuleService:
    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _time_status(rule: ConversationAnnouncementRule, now: datetime | None = None) -> AnnouncementTimeStatus:
        if rule.time_range_type == "permanent":
            return "permanent"
        current = now or datetime.now(timezone.utc)
        start_at = ConversationAnnouncementRuleService._aware(rule.start_at)
        end_at = ConversationAnnouncementRuleService._aware(rule.end_at)
        if start_at and current < start_at:
            return "not_started"
        if end_at and current > end_at:
            return "expired"
        return "active"

    @staticmethod
    def _rule_to_list_item(rule: ConversationAnnouncementRule) -> dict:
        return {
            "id": rule.id,
            "priority": rule.priority,
            "name": rule.name,
            "enabled": rule.enabled,
            "time_range_type": rule.time_range_type,
            "start_at": rule.start_at,
            "end_at": rule.end_at,
            "conditions": list(rule.conditions) if rule.conditions else [],
            "auto_popup": rule.auto_popup,
            "background_color": rule.background_color,
            "time_status": ConversationAnnouncementRuleService._time_status(rule),
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    @staticmethod
    def _rule_to_response(rule: ConversationAnnouncementRule) -> dict:
        data = ConversationAnnouncementRuleService._rule_to_list_item(rule)
        data["summary_html"] = rule.summary_html
        data["detail_html"] = rule.detail_html
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
                    await ConversationAnnouncementRuleService._ensure_channel(db, tenant_id, str(value))
            out.append(data)
        return out

    @staticmethod
    def _payload(data: ConversationAnnouncementRuleCreate | ConversationAnnouncementRuleUpdate) -> dict:
        return data.model_dump(exclude={"conditions"})

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 50,
    ) -> dict:
        rows, total = await ConversationAnnouncementRuleRepository.get_paginated(db, tenant_id, page, per_page)
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": [ConversationAnnouncementRuleService._rule_to_list_item(rule) for rule in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, rule_id: int, tenant_id: int) -> dict:
        rule = await ConversationAnnouncementRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not rule:
            raise NotFoundError("Announcement rule not found")
        return ConversationAnnouncementRuleService._rule_to_response(rule)

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: ConversationAnnouncementRuleCreate) -> dict:
        conditions = await ConversationAnnouncementRuleService._validate_conditions(db, tenant_id, data.conditions)
        next_priority = await ConversationAnnouncementRuleRepository.max_priority(db, tenant_id) + 1
        payload = ConversationAnnouncementRuleService._payload(data)
        payload.update({
            "tenant_id": tenant_id,
            "priority": next_priority,
            "conditions": conditions,
        })
        rule = await ConversationAnnouncementRuleRepository.create(db, payload)
        return ConversationAnnouncementRuleService._rule_to_response(rule)

    @staticmethod
    async def update(
        db: AsyncSession,
        rule_id: int,
        tenant_id: int,
        data: ConversationAnnouncementRuleUpdate,
    ) -> dict:
        rule = await ConversationAnnouncementRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not rule:
            raise NotFoundError("Announcement rule not found")
        conditions = await ConversationAnnouncementRuleService._validate_conditions(db, tenant_id, data.conditions)
        payload = ConversationAnnouncementRuleService._payload(data)
        payload["conditions"] = conditions
        rule = await ConversationAnnouncementRuleRepository.update(db, rule, payload)
        return ConversationAnnouncementRuleService._rule_to_response(rule)

    @staticmethod
    async def patch_enabled(db: AsyncSession, rule_id: int, tenant_id: int, enabled: bool) -> dict:
        rule = await ConversationAnnouncementRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not rule:
            raise NotFoundError("Announcement rule not found")
        rule = await ConversationAnnouncementRuleRepository.update(db, rule, {"enabled": enabled})
        return ConversationAnnouncementRuleService._rule_to_response(rule)

    @staticmethod
    async def delete(db: AsyncSession, rule_id: int, tenant_id: int) -> None:
        rule = await ConversationAnnouncementRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not rule:
            raise NotFoundError("Announcement rule not found")
        await ConversationAnnouncementRuleRepository.delete(db, rule)

    @staticmethod
    async def reorder(db: AsyncSession, tenant_id: int, ordered_ids: list[int]) -> None:
        existing = await ConversationAnnouncementRuleRepository.list_all_ids_ordered(db, tenant_id)
        if set(ordered_ids) != set(existing) or len(ordered_ids) != len(existing):
            raise ValidationError("ordered_ids must match all announcement rules for this tenant")
        id_to_priority = {rule_id: index for index, rule_id in enumerate(ordered_ids, start=1)}
        await ConversationAnnouncementRuleRepository.set_priorities(db, tenant_id, id_to_priority)

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
    def _rule_matches(rule: ConversationAnnouncementRule, channel: Channel) -> bool:
        conditions = list(rule.conditions) if rule.conditions else []
        if not conditions:
            return True
        return all(ConversationAnnouncementRuleService._condition_matches(condition, channel) for condition in conditions)

    @staticmethod
    async def match_public_announcement(db: AsyncSession, channel: Channel) -> dict | None:
        rules = await ConversationAnnouncementRuleRepository.list_enabled_ordered(db, channel.tenant_id)
        now = datetime.now(timezone.utc)
        for rule in rules:
            if ConversationAnnouncementRuleService._time_status(rule, now) not in ("permanent", "active"):
                continue
            if ConversationAnnouncementRuleService._rule_matches(rule, channel):
                return {
                    "id": rule.id,
                    "name": rule.name,
                    "summary_html": rule.summary_html,
                    "detail_html": rule.detail_html,
                    "auto_popup": rule.auto_popup,
                    "background_color": rule.background_color,
                }
        return None
