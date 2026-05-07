"""
Inbound routing rule service
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.service_hours import ServiceHours
from app.repositories.inbound_routing_rule_repository import InboundRoutingRuleRepository
from app.repositories.voice_flow_repository import VoiceFlowRepository
from app.schemas.inbound_routing_rule import (
    InboundRoutingRuleCreate,
    InboundRoutingRuleUpdate,
    RoutingCondition,
)


class InboundRoutingRuleService:

    @staticmethod
    async def _validate_conditions(db: AsyncSession, tenant_id: int, conditions: list[RoutingCondition]) -> list[dict]:
        out: list[dict] = []
        for c in conditions:
            d = c.model_dump()
            if c.condition_type == "call_time":
                sid = int(c.value)
                q = select(ServiceHours).where(
                    ServiceHours.id == sid, ServiceHours.tenant_id == tenant_id
                )
                row = (await db.execute(q)).scalar_one_or_none()
                if not row:
                    raise ValidationError(f"Service hours {sid} not found")
            out.append(d)
        return out

    @staticmethod
    async def _ensure_target_flow(db: AsyncSession, tenant_id: int, flow_id: int) -> None:
        ok = await VoiceFlowRepository.is_usable_target(db, flow_id, tenant_id)
        if not ok:
            raise ValidationError("Target voice flow is invalid, disabled, or deleted")

    @staticmethod
    def _rule_to_response(rule, flow_name: str | None) -> dict:
        return {
            "id": rule.id,
            "priority": rule.priority,
            "name": rule.name,
            "enabled": rule.enabled,
            "conditions": list(rule.conditions) if rule.conditions else [],
            "target_voice_flow_id": rule.target_voice_flow_id,
            "target_flow_name": flow_name or "",
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    @staticmethod
    def _list_item(rule, flow_name: str | None) -> dict:
        return {
            "id": rule.id,
            "priority": rule.priority,
            "name": rule.name,
            "enabled": rule.enabled,
            "target_voice_flow_id": rule.target_voice_flow_id,
            "target_flow_name": flow_name or "",
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    @staticmethod
    async def get_paginated(
        db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 50
    ) -> dict:
        rows, total = await InboundRoutingRuleRepository.get_paginated(
            db, tenant_id, page, per_page
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        items = [
            InboundRoutingRuleService._list_item(rule, fn) for rule, fn in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, rule_id: int, tenant_id: int) -> dict:
        row = await InboundRoutingRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not row:
            raise NotFoundError("Routing rule not found")
        rule, fn = row
        return InboundRoutingRuleService._rule_to_response(rule, fn)

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: InboundRoutingRuleCreate) -> dict:
        await InboundRoutingRuleService._ensure_target_flow(db, tenant_id, data.target_voice_flow_id)
        conds = await InboundRoutingRuleService._validate_conditions(
            db, tenant_id, data.conditions
        )
        nxt = await InboundRoutingRuleRepository.max_priority(db, tenant_id) + 1
        payload = {
            "tenant_id": tenant_id,
            "priority": nxt,
            "name": data.name,
            "enabled": data.enabled,
            "conditions": conds,
            "target_voice_flow_id": data.target_voice_flow_id,
        }
        rule = await InboundRoutingRuleRepository.create(db, payload)
        return await InboundRoutingRuleService.get_by_id(db, rule.id, tenant_id)

    @staticmethod
    async def update(
        db: AsyncSession, rule_id: int, tenant_id: int, data: InboundRoutingRuleUpdate
    ) -> dict:
        row = await InboundRoutingRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not row:
            raise NotFoundError("Routing rule not found")
        rule, _ = row
        await InboundRoutingRuleService._ensure_target_flow(db, tenant_id, data.target_voice_flow_id)
        conds = await InboundRoutingRuleService._validate_conditions(
            db, tenant_id, data.conditions
        )
        await InboundRoutingRuleRepository.update(
            db,
            rule,
            {
                "name": data.name,
                "enabled": data.enabled,
                "conditions": conds,
                "target_voice_flow_id": data.target_voice_flow_id,
            },
        )
        return await InboundRoutingRuleService.get_by_id(db, rule_id, tenant_id)

    @staticmethod
    async def patch_enabled(
        db: AsyncSession, rule_id: int, tenant_id: int, enabled: bool
    ) -> dict:
        row = await InboundRoutingRuleRepository.get_raw_by_id(db, rule_id, tenant_id)
        if not row:
            raise NotFoundError("Routing rule not found")
        await InboundRoutingRuleRepository.update(db, row, {"enabled": enabled})
        return await InboundRoutingRuleService.get_by_id(db, rule_id, tenant_id)

    @staticmethod
    async def delete(db: AsyncSession, rule_id: int, tenant_id: int) -> None:
        row = await InboundRoutingRuleRepository.get_raw_by_id(db, rule_id, tenant_id)
        if not row:
            raise NotFoundError("Routing rule not found")
        await InboundRoutingRuleRepository.delete(db, row)

    @staticmethod
    async def reorder(db: AsyncSession, tenant_id: int, ordered_ids: list[int]) -> None:
        existing = await InboundRoutingRuleRepository.list_all_ids_ordered(db, tenant_id)
        if set(ordered_ids) != set(existing) or len(ordered_ids) != len(existing):
            raise ValidationError("ordered_ids must match all routing rules for this tenant")
        id_to_priority = {rid: i for i, rid in enumerate(ordered_ids, start=1)}
        await InboundRoutingRuleRepository.set_priorities(db, tenant_id, id_to_priority)
