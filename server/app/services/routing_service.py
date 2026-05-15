"""
Routing service — matches session routing rules and determines which agent group
should handle a new conversation.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.channel import Channel
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup, EmployeeGroupMember
from app.models.service_hours import ServiceHours
from app.models.session_routing_rule import SessionRoutingRule
from app.repositories.channel_repository import ChannelRepository
from app.services.channel_service import ChannelService

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

        channel = await ChannelRepository.get_by_id(db, channel_id)
        if not channel or channel.tenant_id != tenant_id:
            logger.warning(
                "route_conversation: channel %s missing or wrong tenant for tenant %s",
                channel_id,
                tenant_id,
            )
            channel = None

        for rule in rules:
            if await RoutingService._rule_matches(db, tenant_id, channel, rule.conditions):
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
    async def _rule_matches(
        db: AsyncSession,
        tenant_id: int,
        channel: Channel | None,
        conditions: list | None,
    ) -> bool:
        """Evaluate session routing conditions for the inbound channel."""
        if not conditions:
            return True

        for cond in conditions:
            ct = cond.get("condition_type")
            op = cond.get("operator", "eq")
            value = cond.get("value")

            if ct == "channel":
                if channel is None:
                    return False
                kind = "sdk" if channel.access_mode == "embed" else "web"
                if op == "eq" and kind != value:
                    return False
                if op == "ne" and kind == value:
                    return False

            elif ct == "web_sdk":
                if channel is None:
                    return False
                cid_str = str(channel.id)
                if op == "eq":
                    if not isinstance(value, str) or value.strip() != cid_str:
                        return False
                elif op == "ne":
                    if not isinstance(value, str) or value.strip() == cid_str:
                        return False
                elif op == "any_eq":
                    wanted = value if isinstance(value, list) else []
                    allowed = {str(v).strip() for v in wanted}
                    if cid_str not in allowed:
                        return False
                elif op == "any_ne":
                    forbidden = value if isinstance(value, list) else []
                    blocked = {str(v).strip() for v in forbidden}
                    if cid_str in blocked:
                        return False
                else:
                    return False

            elif ct == "current_time":
                sid_str = str(value).strip() if value is not None else ""
                if isinstance(value, list) or not sid_str.isdigit():
                    return False
                sid = int(sid_str)
                row = await db.get(ServiceHours, sid)
                if not row or row.tenant_id != tenant_id:
                    return False
                in_sched = ChannelService.is_within_service_hours(row)
                if op == "in_schedule" and not in_sched:
                    return False
                if op == "not_in_schedule" and in_sched:
                    return False
            else:
                logger.debug("Unknown session routing condition_type: %s", ct)
                return False

        return True
