"""
Routing service — matches session routing rules and determines which agent group
should handle a new conversation.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.session_routing_rule import SessionRoutingRule
from app.models.employee_group import EmployeeGroup, EmployeeGroupMember
from app.models.employee import Employee

logger = logging.getLogger(__name__)


class RoutingService:

    @staticmethod
    async def route_conversation(
        db: AsyncSession,
        tenant_id: int,
        channel_id: int,
    ) -> tuple[int | None, list[int], dict[int, int]]:
        """Determine the target group for a new conversation.

        Returns (group_id, member_user_ids, max_concurrent_map).
        """
        result = await db.execute(
            select(SessionRoutingRule)
            .where(
                SessionRoutingRule.tenant_id == tenant_id,
                SessionRoutingRule.enabled.is_(True),
            )
            .order_by(SessionRoutingRule.priority.asc())
        )
        rules = list(result.scalars().all())

        target_group_id: int | None = None

        for rule in rules:
            if RoutingService._match_conditions(rule.conditions, channel_id):
                target_group_id = rule.target_group_id
                break

        if target_group_id is None and rules:
            target_group_id = rules[0].target_group_id

        if target_group_id is None:
            logger.warning("No routing rules for tenant %d, falling back to all active agents", tenant_id)
            from app.repositories.employee_repository import EmployeeRepository
            all_users = await EmployeeRepository.get_active_by_tenant(db, tenant_id)
            if not all_users:
                return None, [], {}
            member_ids = [u.id for u in all_users]
            max_map = {u.id: (u.max_concurrent or 10) for u in all_users}
            return None, member_ids, max_map

        result = await db.execute(
            select(EmployeeGroupMember)
            .options(selectinload(EmployeeGroupMember.employee))
            .where(EmployeeGroupMember.group_id == target_group_id)
        )
        members = list(result.scalars().all())
        active_members = [m for m in members if m.employee and m.employee.is_active]

        member_ids = [m.employee_id for m in active_members]
        max_map = {m.employee_id: m.employee.max_concurrent for m in active_members}

        return target_group_id, member_ids, max_map

    @staticmethod
    def _match_conditions(conditions: list, channel_id: int) -> bool:
        """Evaluate routing rule conditions against the conversation context."""
        if not conditions:
            return True

        for cond in conditions:
            field = cond.get("field")
            op = cond.get("operator", "eq")
            value = cond.get("value")

            if field == "channel_id":
                if op == "eq" and value != channel_id:
                    return False
                if op == "in" and channel_id not in (value if isinstance(value, list) else [value]):
                    return False

        return True
