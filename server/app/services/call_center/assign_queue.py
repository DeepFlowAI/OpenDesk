"""
Runtime selection for voice-flow assign_queue nodes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import QueueChannel, QueueType
from app.models.fd_field_definition import FdFieldDefinition
from app.models.user import User
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.queue_repository import (
    QueueCandidateRepository,
    QueueTaskRepository,
)
from app.services.queue_resource_provider import QueueResourceProviderFactory
from app.services.queue_service import QueuePolicyResolver


ASSIGN_QUEUE_STATUSES = {
    "queue_limit_reached",
    "no_available_queue",
    "queue_timeout",
    "agent_no_answer",
}
USER_FIELD_TARGET_TYPE = "user_field"


@dataclass(slots=True)
class AssignQueueCandidate:
    queue_type: str
    queue_id: int
    order: int
    waiting_count: int
    tail_wait_seconds: int
    available_agent_count: int
    gate_passed: bool
    limit_reason: str | None = None

    @property
    def has_available_agent(self) -> bool:
        return self.available_agent_count > 0


@dataclass(slots=True)
class AssignQueueSelection:
    candidate: AssignQueueCandidate | None
    candidates: list[AssignQueueCandidate]
    failure_status: str | None = None
    limit_reason: str | None = None


class AssignQueueSelector:
    @staticmethod
    def normalize_targets(data: dict[str, Any]) -> list[dict[str, int | str]]:
        targets = data.get("queue_targets")
        if isinstance(targets, list) and targets:
            raw_targets = targets
        else:
            group_id = data.get("employee_group_id")
            raw_targets = (
                [{"queue_type": QueueType.EMPLOYEE_GROUP.value, "queue_id": group_id}]
                if group_id
                else []
            )

        normalized: list[dict[str, int | str]] = []
        seen: set[tuple[str, int]] = set()
        for target in raw_targets:
            if not isinstance(target, dict):
                continue
            queue_type = str(target.get("queue_type") or "")
            if queue_type not in {
                USER_FIELD_TARGET_TYPE,
                QueueType.EMPLOYEE_GROUP.value,
                QueueType.EMPLOYEE.value,
            }:
                continue
            try:
                queue_id = int(target.get("queue_id") or 0)
            except (TypeError, ValueError):
                continue
            if queue_id <= 0:
                continue
            key = (queue_type, queue_id)
            if key in seen:
                continue
            seen.add(key)
            normalized.append({"queue_type": queue_type, "queue_id": queue_id})
        return normalized

    @staticmethod
    async def resolve_targets(
        db: AsyncSession,
        tenant_id: int,
        data: dict[str, Any],
        *,
        call_id: str | None = None,
    ) -> list[dict[str, int | str]]:
        resolved: list[dict[str, int | str]] = []
        seen: set[tuple[str, int]] = set()
        for target in AssignQueueSelector.normalize_targets(data):
            queue_type = str(target["queue_type"])
            queue_id = int(target["queue_id"])
            if queue_type == USER_FIELD_TARGET_TYPE:
                targets = await AssignQueueSelector._targets_from_user_field(
                    db,
                    tenant_id,
                    call_id=call_id,
                    field_id=queue_id,
                )
            else:
                targets = [{"queue_type": queue_type, "queue_id": queue_id}]

            for item in targets:
                item_type = str(item["queue_type"])
                item_id = int(item["queue_id"])
                key = (item_type, item_id)
                if key in seen:
                    continue
                seen.add(key)
                resolved.append({"queue_type": item_type, "queue_id": item_id})
        return resolved

    @staticmethod
    async def select(
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        data: dict[str, Any],
        *,
        call_id: str | None = None,
    ) -> AssignQueueSelection:
        candidates: list[AssignQueueCandidate] = []
        targets = await AssignQueueSelector.resolve_targets(db, tenant_id, data, call_id=call_id)
        for order, target in enumerate(targets):
            candidate = await AssignQueueSelector._build_candidate(
                db,
                r,
                tenant_id,
                queue_type=str(target["queue_type"]),
                queue_id=int(target["queue_id"]),
                order=order,
            )
            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            return AssignQueueSelection(
                candidate=None,
                candidates=[],
                failure_status="no_available_queue",
            )

        strategy = data.get("target_strategy") or "sequential_overflow"
        eligible = [candidate for candidate in candidates if candidate.gate_passed]
        if not eligible:
            limit_reasons = {
                candidate.limit_reason for candidate in candidates if candidate.limit_reason
            }
            if limit_reasons:
                return AssignQueueSelection(
                    candidate=None,
                    candidates=candidates,
                    failure_status="queue_limit_reached",
                    limit_reason=(
                        next(iter(limit_reasons))
                        if len(limit_reasons) == 1
                        else "mixed_limit"
                    ),
                )
            return AssignQueueSelection(
                candidate=None,
                candidates=candidates,
                failure_status="no_available_queue",
            )

        if strategy == "sequential_overflow":
            for candidate in eligible:
                if candidate.has_available_agent:
                    return AssignQueueSelection(candidate=candidate, candidates=candidates)
            return AssignQueueSelection(candidate=eligible[0], candidates=candidates)

        if strategy == "shortest_tail_wait":
            selected = sorted(
                eligible,
                key=lambda c: (
                    c.tail_wait_seconds,
                    c.waiting_count,
                    -c.available_agent_count,
                    c.order,
                ),
            )[0]
            return AssignQueueSelection(candidate=selected, candidates=candidates)

        selected = sorted(
            eligible,
            key=lambda c: (
                c.waiting_count,
                -c.available_agent_count,
                c.tail_wait_seconds,
                c.order,
            ),
        )[0]
        return AssignQueueSelection(candidate=selected, candidates=candidates)

    @staticmethod
    async def _build_candidate(
        db: AsyncSession,
        r: aioredis.Redis,
        tenant_id: int,
        *,
        queue_type: str,
        queue_id: int,
        order: int,
    ) -> AssignQueueCandidate | None:
        exists = await QueueCandidateRepository.queue_exists(db, tenant_id, queue_type, queue_id)
        if not exists:
            return None

        employees = await QueueCandidateRepository.list_candidate_employees(
            db,
            tenant_id,
            queue_type,
            queue_id,
        )
        if not employees:
            return None

        waiting_count = await QueueTaskRepository.count_waiting(
            db,
            tenant_id,
            QueueChannel.CALL_CENTER.value,
            queue_type,
            queue_id,
        )
        tail = await QueueTaskRepository.get_tail_waiting(
            db,
            tenant_id,
            QueueChannel.CALL_CENTER.value,
            queue_type,
            queue_id,
        )
        tail_wait_seconds = 0
        if tail:
            enqueued_at = tail.enqueued_at
            if enqueued_at.tzinfo is None:
                enqueued_at = enqueued_at.replace(tzinfo=timezone.utc)
            tail_wait_seconds = int((datetime.now(timezone.utc) - enqueued_at).total_seconds())

        limit_reason = await AssignQueueSelector._limit_reason(
            db,
            tenant_id,
            queue_type=queue_type,
            queue_id=queue_id,
            waiting_count=waiting_count,
        )

        available_agent_count = 0
        provider = QueueResourceProviderFactory.create(QueueChannel.CALL_CENTER.value)
        try:
            runtime_candidates = await provider.list_candidates(
                db,
                r,
                tenant_id,
                queue_type,
                queue_id,
            )
            available_agent_count = len([candidate for candidate in runtime_candidates if candidate.available])
        except Exception:  # noqa: BLE001
            available_agent_count = 0

        return AssignQueueCandidate(
            queue_type=queue_type,
            queue_id=queue_id,
            order=order,
            waiting_count=waiting_count,
            tail_wait_seconds=tail_wait_seconds,
            available_agent_count=available_agent_count,
            gate_passed=limit_reason is None,
            limit_reason=limit_reason,
        )

    @staticmethod
    def _coerce_target_ids(value: Any) -> list[int]:
        values = value if isinstance(value, list) else [value]
        out: list[int] = []
        for item in values:
            raw = item
            if isinstance(raw, dict):
                raw = (
                    raw.get("id")
                    or raw.get("value")
                    or raw.get("employee_id")
                    or raw.get("group_id")
                )
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
        *,
        call_id: str | None,
        field_id: int,
    ) -> list[dict[str, int | str]]:
        if not call_id:
            return []
        call_record = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
        if not call_record or not call_record.user_id:
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

        user = await db.get(User, call_record.user_id)
        if not user or user.tenant_id != tenant_id:
            return []

        queue_type = (
            QueueType.EMPLOYEE.value
            if field.field_type == "employee_select"
            else QueueType.EMPLOYEE_GROUP.value
        )
        return [
            {"queue_type": queue_type, "queue_id": target_id}
            for target_id in AssignQueueSelector._coerce_target_ids(
                getattr(user, field.slot_column, None)
            )
        ]

    @staticmethod
    async def _limit_reason(
        db: AsyncSession,
        tenant_id: int,
        *,
        queue_type: str,
        queue_id: int,
        waiting_count: int,
    ) -> str | None:
        policy = await QueuePolicyResolver.resolve(
            db,
            tenant_id,
            channel=QueueChannel.CALL_CENTER.value,
            queue_type=queue_type,
            queue_id=queue_id,
        )
        max_waiting_count = policy.get("max_waiting_count")
        if max_waiting_count is not None and waiting_count >= int(max_waiting_count):
            return "max_waiting_count"

        max_wait_seconds = policy.get("max_wait_seconds")
        if max_wait_seconds is not None:
            tail = await QueueTaskRepository.get_tail_same_priority(
                db,
                tenant_id,
                QueueChannel.CALL_CENTER.value,
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
                    return "max_wait_seconds"
        return None
