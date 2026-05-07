"""
Session routing rule service
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.employee_group import EmployeeGroup
from app.models.service_hours import ServiceHours
from app.repositories.session_routing_rule_repository import SessionRoutingRuleRepository
from app.schemas.session_routing_rule import (
    SessionRoutingRuleCreate,
    SessionRoutingRuleUpdate,
    SessionRoutingCondition,
)


class SessionRoutingRuleService:

    @staticmethod
    async def _validate_conditions(
        db: AsyncSession, tenant_id: int, conditions: list[SessionRoutingCondition]
    ) -> list[dict]:
        out: list[dict] = []
        for c in conditions:
            d = c.model_dump()
            if c.condition_type == "current_time":
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
    async def _ensure_target_group(db: AsyncSession, tenant_id: int, group_id: int) -> None:
        q = select(EmployeeGroup).where(
            EmployeeGroup.id == group_id, EmployeeGroup.tenant_id == tenant_id
        )
        row = (await db.execute(q)).scalar_one_or_none()
        if not row:
            raise ValidationError("Target employee group not found or does not belong to this tenant")

    @staticmethod
    def _rule_to_response(rule, group_name: str | None) -> dict:
        return {
            "id": rule.id,
            "priority": rule.priority,
            "name": rule.name,
            "enabled": rule.enabled,
            "conditions": list(rule.conditions) if rule.conditions else [],
            "target_group_id": rule.target_group_id,
            "target_group_name": group_name or "",
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    @staticmethod
    def _list_item(rule, group_name: str | None) -> dict:
        return {
            "id": rule.id,
            "priority": rule.priority,
            "name": rule.name,
            "enabled": rule.enabled,
            "target_group_id": rule.target_group_id,
            "target_group_name": group_name or "",
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    @staticmethod
    async def get_paginated(
        db: AsyncSession, tenant_id: int, page: int = 1, per_page: int = 50
    ) -> dict:
        rows, total = await SessionRoutingRuleRepository.get_paginated(
            db, tenant_id, page, per_page
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        items = [
            SessionRoutingRuleService._list_item(rule, gn) for rule, gn in rows
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
        row = await SessionRoutingRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not row:
            raise NotFoundError("Session routing rule not found")
        rule, gn = row
        return SessionRoutingRuleService._rule_to_response(rule, gn)

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: SessionRoutingRuleCreate) -> dict:
        await SessionRoutingRuleService._ensure_target_group(db, tenant_id, data.target_group_id)
        conds = await SessionRoutingRuleService._validate_conditions(
            db, tenant_id, data.conditions
        )
        nxt = await SessionRoutingRuleRepository.max_priority(db, tenant_id) + 1
        payload = {
            "tenant_id": tenant_id,
            "priority": nxt,
            "name": data.name,
            "enabled": data.enabled,
            "conditions": conds,
            "target_group_id": data.target_group_id,
        }
        rule = await SessionRoutingRuleRepository.create(db, payload)
        return await SessionRoutingRuleService.get_by_id(db, rule.id, tenant_id)

    @staticmethod
    async def update(
        db: AsyncSession, rule_id: int, tenant_id: int, data: SessionRoutingRuleUpdate
    ) -> dict:
        row = await SessionRoutingRuleRepository.get_by_id(db, rule_id, tenant_id)
        if not row:
            raise NotFoundError("Session routing rule not found")
        rule, _ = row
        await SessionRoutingRuleService._ensure_target_group(db, tenant_id, data.target_group_id)
        conds = await SessionRoutingRuleService._validate_conditions(
            db, tenant_id, data.conditions
        )
        await SessionRoutingRuleRepository.update(
            db,
            rule,
            {
                "name": data.name,
                "enabled": data.enabled,
                "conditions": conds,
                "target_group_id": data.target_group_id,
            },
        )
        return await SessionRoutingRuleService.get_by_id(db, rule_id, tenant_id)

    @staticmethod
    async def patch_enabled(
        db: AsyncSession, rule_id: int, tenant_id: int, enabled: bool
    ) -> dict:
        row = await SessionRoutingRuleRepository.get_raw_by_id(db, rule_id, tenant_id)
        if not row:
            raise NotFoundError("Session routing rule not found")
        await SessionRoutingRuleRepository.update(db, row, {"enabled": enabled})
        return await SessionRoutingRuleService.get_by_id(db, rule_id, tenant_id)

    @staticmethod
    async def delete(db: AsyncSession, rule_id: int, tenant_id: int) -> None:
        row = await SessionRoutingRuleRepository.get_raw_by_id(db, rule_id, tenant_id)
        if not row:
            raise NotFoundError("Session routing rule not found")
        await SessionRoutingRuleRepository.delete(db, row)

    @staticmethod
    async def reorder(db: AsyncSession, tenant_id: int, ordered_ids: list[int]) -> None:
        existing = await SessionRoutingRuleRepository.list_all_ids_ordered(db, tenant_id)
        if set(ordered_ids) != set(existing) or len(ordered_ids) != len(existing):
            raise ValidationError("ordered_ids must match all session routing rules for this tenant")
        id_to_priority = {rid: i for i, rid in enumerate(ordered_ids, start=1)}
        await SessionRoutingRuleRepository.set_priorities(db, tenant_id, id_to_priority)
