"""
Routing service — matches session routing rules and determines which agent group
should handle a new conversation.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.models.fd_field_definition import FdFieldDefinition
from app.models.service_hours import ServiceHours
from app.models.session_routing_rule import SessionRoutingRule
from app.models.user import User
from app.enums import AgentOnlineStatus, QueueChannel, QueueType
from app.repositories.channel_repository import ChannelRepository
from app.repositories.queue_repository import QueueCandidateRepository, QueueTaskRepository
from app.services.agent_status_service import AgentStatusService
from app.services.channel_service import ChannelService
from app.services.queue_service import QueuePolicyResolver

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RouteQueueCandidate:
    queue_type: str
    queue_id: int
    group_id: int | None
    member_ids: list[int]
    max_concurrent_map: dict[int, int]
    waiting_count: int
    tail_wait_seconds: int
    gate_passed: bool
    has_available_agent: bool
    order: int


class RoutingService:

    @staticmethod
    async def route_conversation(
        db: AsyncSession,
        tenant_id: int,
        channel_id: int,
        r: aioredis.Redis | None = None,
        visitor_id: int | None = None,
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

        channel = await ChannelRepository.get_by_id(db, channel_id)
        if not channel or channel.tenant_id != tenant_id:
            logger.warning(
                "route_conversation: channel %s missing or wrong tenant for tenant %s",
                channel_id,
                tenant_id,
            )
            channel = None

        matched_rule: SessionRoutingRule | None = None
        for rule in rules:
            if await RoutingService._rule_matches(db, tenant_id, channel, rule.conditions):
                matched_rule = rule
                break

        if matched_rule is None and rules:
            matched_rule = rules[0]

        if matched_rule is not None:
            candidate = await RoutingService._select_candidate_for_rule(
                db,
                r,
                tenant_id,
                matched_rule,
                visitor_id=visitor_id,
            )
            if candidate is None:
                return None, [], {}
            return candidate.group_id, candidate.member_ids, candidate.max_concurrent_map

        if not rules:
            logger.warning("No routing rules for tenant %d, falling back to all active agents", tenant_id)
            from app.repositories.employee_repository import EmployeeRepository
            all_users = await EmployeeRepository.get_active_by_tenant(db, tenant_id)
            if not all_users:
                return None, [], {}
            member_ids = [u.id for u in all_users]
            max_map = {u.id: (u.max_concurrent or 10) for u in all_users}
            return None, member_ids, max_map

        return None, [], {}

    @staticmethod
    def _rule_queue_sources(rule: SessionRoutingRule) -> list[dict]:
        sources = list(rule.target_queue_sources or [])
        if sources:
            return sources
        if rule.target_group_id:
            return [{"source_type": "employee_group", "target_ids": [rule.target_group_id]}]
        return []

    @staticmethod
    def _coerce_target_ids(value: Any) -> list[int]:
        values = value if isinstance(value, list) else [value]
        out: list[int] = []
        for item in values:
            raw = item
            if isinstance(raw, dict):
                raw = raw.get("id") or raw.get("value") or raw.get("employee_id") or raw.get("group_id")
            if isinstance(raw, Decimal):
                raw = int(raw)
            if isinstance(raw, float):
                raw = int(raw)
            if isinstance(raw, str):
                raw = raw.strip()
                if not raw:
                    continue
            try:
                target_id = int(raw)
            except (TypeError, ValueError):
                continue
            if target_id > 0 and target_id not in out:
                out.append(target_id)
        return out

    @staticmethod
    async def _targets_from_user_field(
        db: AsyncSession,
        tenant_id: int,
        visitor_id: int | None,
        field_id: int,
    ) -> list[tuple[str, int]]:
        if visitor_id is None:
            return []
        field_result = await db.execute(
            select(FdFieldDefinition).where(
                FdFieldDefinition.tenant_id == tenant_id,
                FdFieldDefinition.id == field_id,
                FdFieldDefinition.domain == "user",
                FdFieldDefinition.status == "active",
                FdFieldDefinition.field_type.in_(["employee_select", "group_select"]),
            )
        )
        field = field_result.scalar_one_or_none()
        if not field or not field.slot_column:
            return []
        user = await db.get(User, visitor_id)
        if not user or user.tenant_id != tenant_id:
            return []
        ids = RoutingService._coerce_target_ids(getattr(user, field.slot_column, None))
        queue_type = (
            QueueType.EMPLOYEE.value
            if field.field_type == "employee_select"
            else QueueType.EMPLOYEE_GROUP.value
        )
        return [(queue_type, target_id) for target_id in ids]

    @staticmethod
    async def _source_targets(
        db: AsyncSession,
        tenant_id: int,
        visitor_id: int | None,
        source: dict,
    ) -> list[tuple[str, int]]:
        source_type = source.get("source_type")
        target_ids = RoutingService._coerce_target_ids(source.get("target_ids"))
        if source_type == "employee":
            return [(QueueType.EMPLOYEE.value, target_id) for target_id in target_ids]
        if source_type == "employee_group":
            return [(QueueType.EMPLOYEE_GROUP.value, target_id) for target_id in target_ids]
        if source_type == "user_field":
            targets: list[tuple[str, int]] = []
            for field_id in target_ids:
                targets.extend(
                    await RoutingService._targets_from_user_field(db, tenant_id, visitor_id, field_id)
                )
            return targets
        return []

    @staticmethod
    async def _queue_gate_passed(
        db: AsyncSession,
        tenant_id: int,
        queue_type: str,
        queue_id: int,
        waiting_count: int,
    ) -> bool:
        policy = await QueuePolicyResolver.resolve(
            db,
            tenant_id,
            channel=QueueChannel.ONLINE_CHAT.value,
            queue_type=queue_type,
            queue_id=queue_id,
        )
        max_waiting_count = policy.get("max_waiting_count")
        if max_waiting_count is not None and waiting_count >= int(max_waiting_count):
            return False
        max_wait_seconds = policy.get("max_wait_seconds")
        if max_wait_seconds is not None:
            tail = await QueueTaskRepository.get_tail_same_priority(
                db,
                tenant_id,
                QueueChannel.ONLINE_CHAT.value,
                queue_type,
                queue_id,
                5,
            )
            if tail:
                enqueued_at = tail.enqueued_at
                if enqueued_at.tzinfo is None:
                    enqueued_at = enqueued_at.replace(tzinfo=timezone.utc)
                wait_seconds = (datetime.now(timezone.utc) - enqueued_at).total_seconds()
                if wait_seconds >= int(max_wait_seconds):
                    return False
        return True

    @staticmethod
    async def _build_candidate(
        db: AsyncSession,
        r: aioredis.Redis | None,
        tenant_id: int,
        queue_type: str,
        queue_id: int,
        order: int,
    ) -> RouteQueueCandidate | None:
        exists = await QueueCandidateRepository.queue_exists(db, tenant_id, queue_type, queue_id)
        if not exists:
            return None

        employees = await QueueCandidateRepository.list_candidate_employees(
            db, tenant_id, queue_type, queue_id
        )
        if not employees:
            return None
        member_ids = [employee.id for employee in employees]
        max_map = {employee.id: (employee.max_concurrent or 10) for employee in employees}
        waiting_count = await QueueTaskRepository.count_waiting(
            db,
            tenant_id,
            QueueChannel.ONLINE_CHAT.value,
            queue_type,
            queue_id,
        )
        tail = await QueueTaskRepository.get_tail_waiting(
            db,
            tenant_id,
            QueueChannel.ONLINE_CHAT.value,
            queue_type,
            queue_id,
        )
        tail_wait_seconds = 0
        if tail:
            enqueued_at = tail.enqueued_at
            if enqueued_at.tzinfo is None:
                enqueued_at = enqueued_at.replace(tzinfo=timezone.utc)
            tail_wait_seconds = int((datetime.now(timezone.utc) - enqueued_at).total_seconds())

        gate_passed = await RoutingService._queue_gate_passed(
            db, tenant_id, queue_type, queue_id, waiting_count
        )

        has_available_agent = bool(member_ids)
        if r is not None:
            statuses = await AgentStatusService.get_statuses_bulk(
                r,
                tenant_id,
                [(employee_id, max_map[employee_id]) for employee_id in member_ids],
            )
            has_available_agent = any(
                (statuses.get(employee_id) or {}).get("status") == AgentOnlineStatus.ONLINE.value
                and int((statuses.get(employee_id) or {}).get("current_count", 0))
                < int((statuses.get(employee_id) or {}).get("max_concurrent", max_map[employee_id]))
                for employee_id in member_ids
            )

        return RouteQueueCandidate(
            queue_type=queue_type,
            queue_id=queue_id,
            group_id=queue_id if queue_type == QueueType.EMPLOYEE_GROUP.value else None,
            member_ids=member_ids,
            max_concurrent_map=max_map,
            waiting_count=waiting_count,
            tail_wait_seconds=tail_wait_seconds,
            gate_passed=gate_passed,
            has_available_agent=has_available_agent,
            order=order,
        )

    @staticmethod
    async def _resolve_candidates_for_rule(
        db: AsyncSession,
        r: aioredis.Redis | None,
        tenant_id: int,
        rule: SessionRoutingRule,
        visitor_id: int | None,
    ) -> list[RouteQueueCandidate]:
        candidates: list[RouteQueueCandidate] = []
        seen: set[tuple[str, int]] = set()
        order = 0
        for source in RoutingService._rule_queue_sources(rule):
            for queue_type, queue_id in await RoutingService._source_targets(
                db, tenant_id, visitor_id, source
            ):
                key = (queue_type, queue_id)
                if key in seen:
                    continue
                seen.add(key)
                candidate = await RoutingService._build_candidate(
                    db, r, tenant_id, queue_type, queue_id, order
                )
                order += 1
                if candidate:
                    candidates.append(candidate)
        return candidates

    @staticmethod
    async def _select_candidate_for_rule(
        db: AsyncSession,
        r: aioredis.Redis | None,
        tenant_id: int,
        rule: SessionRoutingRule,
        *,
        visitor_id: int | None = None,
    ) -> RouteQueueCandidate | None:
        candidates = await RoutingService._resolve_candidates_for_rule(
            db, r, tenant_id, rule, visitor_id
        )
        strategy = rule.target_strategy or "sequential_overflow"
        if strategy == "sequential_overflow":
            for candidate in candidates:
                if candidate.gate_passed and candidate.has_available_agent:
                    return candidate
            return None

        eligible = [candidate for candidate in candidates if candidate.gate_passed]
        if not eligible:
            return None
        if strategy == "shortest_tail_wait":
            return sorted(eligible, key=lambda c: (c.tail_wait_seconds, c.waiting_count, c.order))[0]
        return sorted(eligible, key=lambda c: (c.waiting_count, c.tail_wait_seconds, c.order))[0]

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
                if value not in ("websdk", "web", "sdk"):
                    return False
                is_web_sdk_channel = getattr(channel, "channel_type", "web") == "web"
                if op == "eq" and not is_web_sdk_channel:
                    return False
                if op == "ne" and is_web_sdk_channel:
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
