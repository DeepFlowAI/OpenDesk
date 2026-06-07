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
    SessionRoutingQueueSource,
)


class SessionRoutingRuleService:
    STRATEGY_LABELS = {
        "sequential_overflow": "顺序溢出",
        "least_waiting_count": "最少排队队列",
        "shortest_tail_wait": "最短排队时间队列",
    }

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
    def _rule_queue_sources(rule) -> list[dict]:
        sources = list(rule.target_queue_sources or [])
        if sources:
            return sources
        if rule.target_group_id:
            return [{"source_type": "employee_group", "target_ids": [rule.target_group_id]}]
        return []

    @staticmethod
    def _compat_target_group_id(sources: list[dict]) -> int | None:
        for source in sources:
            if source.get("source_type") != "employee_group":
                continue
            target_ids = source.get("target_ids")
            if isinstance(target_ids, list) and target_ids:
                return int(target_ids[0])
        return None

    @staticmethod
    async def _validate_queue_sources(
        db: AsyncSession,
        tenant_id: int,
        sources: list[SessionRoutingQueueSource],
        legacy_target_group_id: int | None,
    ) -> list[dict]:
        if not sources and legacy_target_group_id is not None:
            sources = [
                SessionRoutingQueueSource(
                    source_type="employee_group",
                    target_ids=[legacy_target_group_id],
                )
            ]
        if not sources:
            raise ValidationError("At least one queue source is required")

        employee_ids: list[int] = []
        group_ids: list[int] = []
        field_ids: list[int] = []
        for source in sources:
            if source.source_type == "employee":
                employee_ids.extend(source.target_ids)
            elif source.source_type == "employee_group":
                group_ids.extend(source.target_ids)
            elif source.source_type == "user_field":
                field_ids.extend(source.target_ids)

        employee_map = await SessionRoutingRuleRepository.get_active_employee_name_map(
            db, tenant_id, employee_ids
        )
        missing_employee_ids = sorted(set(employee_ids) - set(employee_map))
        if missing_employee_ids:
            raise ValidationError(f"Target employee {missing_employee_ids[0]} not found")

        group_map = await SessionRoutingRuleRepository.get_group_name_map(db, tenant_id, group_ids)
        missing_group_ids = sorted(set(group_ids) - set(group_map))
        if missing_group_ids:
            raise ValidationError(f"Target employee group {missing_group_ids[0]} not found")

        field_map = await SessionRoutingRuleRepository.get_user_queue_field_map(
            db, tenant_id, field_ids
        )
        missing_field_ids = sorted(set(field_ids) - set(field_map))
        if missing_field_ids:
            raise ValidationError(f"Target user field {missing_field_ids[0]} is not available for queue routing")

        return [source.model_dump() for source in sources]

    @staticmethod
    async def _target_summary(db: AsyncSession, tenant_id: int, strategy: str, sources: list[dict]) -> str:
        strategy_label = SessionRoutingRuleService.STRATEGY_LABELS.get(strategy, strategy)
        employee_ids: list[int] = []
        group_ids: list[int] = []
        field_ids: list[int] = []
        for source in sources:
            target_ids = source.get("target_ids") if isinstance(source, dict) else None
            ids = [int(item) for item in target_ids] if isinstance(target_ids, list) else []
            if source.get("source_type") == "employee":
                employee_ids.extend(ids)
            elif source.get("source_type") == "employee_group":
                group_ids.extend(ids)
            elif source.get("source_type") == "user_field":
                field_ids.extend(ids)

        employee_map = await SessionRoutingRuleRepository.get_active_employee_name_map(
            db, tenant_id, employee_ids
        )
        group_map = await SessionRoutingRuleRepository.get_group_name_map(db, tenant_id, group_ids)
        field_map = await SessionRoutingRuleRepository.get_user_queue_field_map(db, tenant_id, field_ids)

        labels: list[str] = []
        has_employee = False
        has_group = False
        for source in sources:
            source_type = source.get("source_type")
            target_ids = source.get("target_ids") if isinstance(source, dict) else None
            ids = [int(item) for item in target_ids] if isinstance(target_ids, list) else []
            if source_type == "employee":
                has_employee = True
                labels.extend(employee_map.get(target_id, f"员工 #{target_id}") for target_id in ids)
            elif source_type == "employee_group":
                has_group = True
                labels.extend(group_map.get(target_id, f"员工组 #{target_id}") for target_id in ids)
            elif source_type == "user_field":
                for target_id in ids:
                    field_name, field_type = field_map.get(target_id, (f"用户字段 #{target_id}", ""))
                    if field_type == "employee_select":
                        has_employee = True
                    elif field_type == "group_select":
                        has_group = True
                    labels.append(f"用户字段：{field_name}")

        visible = labels[:2]
        suffix = "" if len(labels) <= 2 else f" 等 {len(labels)} 个目标"
        tag_bits = []
        if has_employee:
            tag_bits.append("员工")
        if has_group:
            tag_bits.append("员工组")
        tags = f"（{'/'.join(tag_bits)}）" if tag_bits else ""
        detail = " → ".join(visible) + suffix if visible else "暂无队列来源"
        return f"{strategy_label}{tags}：{detail}"

    @staticmethod
    async def _rule_to_response(db: AsyncSession, tenant_id: int, rule, group_name: str | None) -> dict:
        sources = SessionRoutingRuleService._rule_queue_sources(rule)
        strategy = rule.target_strategy or "sequential_overflow"
        return {
            "id": rule.id,
            "priority": rule.priority,
            "name": rule.name,
            "enabled": rule.enabled,
            "conditions": list(rule.conditions) if rule.conditions else [],
            "target_group_id": rule.target_group_id,
            "target_group_name": group_name or "",
            "target_strategy": strategy,
            "target_queue_sources": sources,
            "target_summary": await SessionRoutingRuleService._target_summary(db, tenant_id, strategy, sources),
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    @staticmethod
    async def _list_item(db: AsyncSession, tenant_id: int, rule, group_name: str | None) -> dict:
        sources = SessionRoutingRuleService._rule_queue_sources(rule)
        strategy = rule.target_strategy or "sequential_overflow"
        return {
            "id": rule.id,
            "priority": rule.priority,
            "name": rule.name,
            "enabled": rule.enabled,
            "target_group_id": rule.target_group_id,
            "target_group_name": group_name or "",
            "target_strategy": strategy,
            "target_queue_sources": sources,
            "target_summary": await SessionRoutingRuleService._target_summary(db, tenant_id, strategy, sources),
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
            await SessionRoutingRuleService._list_item(db, tenant_id, rule, gn)
            for rule, gn in rows
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
        return await SessionRoutingRuleService._rule_to_response(db, tenant_id, rule, gn)

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, data: SessionRoutingRuleCreate) -> dict:
        conds = await SessionRoutingRuleService._validate_conditions(
            db, tenant_id, data.conditions
        )
        sources = await SessionRoutingRuleService._validate_queue_sources(
            db, tenant_id, data.target_queue_sources, data.target_group_id
        )
        target_group_id = SessionRoutingRuleService._compat_target_group_id(sources)
        nxt = await SessionRoutingRuleRepository.max_priority(db, tenant_id) + 1
        payload = {
            "tenant_id": tenant_id,
            "priority": nxt,
            "name": data.name,
            "enabled": data.enabled,
            "conditions": conds,
            "target_group_id": target_group_id,
            "target_strategy": data.target_strategy,
            "target_queue_sources": sources,
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
        conds = await SessionRoutingRuleService._validate_conditions(
            db, tenant_id, data.conditions
        )
        sources = await SessionRoutingRuleService._validate_queue_sources(
            db, tenant_id, data.target_queue_sources, data.target_group_id
        )
        target_group_id = SessionRoutingRuleService._compat_target_group_id(sources)
        await SessionRoutingRuleRepository.update(
            db,
            rule,
            {
                "name": data.name,
                "enabled": data.enabled,
                "conditions": conds,
                "target_group_id": target_group_id,
                "target_strategy": data.target_strategy,
                "target_queue_sources": sources,
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
