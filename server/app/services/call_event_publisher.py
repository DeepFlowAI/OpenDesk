"""Publish call facts to tenant call event subscription rules.

Events are written as delivery snapshots inside the same transaction as the
call fact that produced them. Building or enqueueing an event runs inside a
savepoint, so a publishing failure never rolls back the call fact itself.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Awaitable, Callable
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_event import CallEvent
from app.models.call_recording import CallRecording
from app.models.employee import Employee
from app.repositories.call_event_subscription_repository import (
    CallEventSubscriptionRepository,
)
from app.repositories.call_recording_repository import CallRecordingRepository
from app.repositories.user_repository import UserRepository
from app.services.call_event_rule_cache import CallEventRuleCache
from app.services.event_delivery_service import EventDeliveryService

if TYPE_CHECKING:
    from app.models.call_record import CallRecord

logger = logging.getLogger(__name__)

CALL_EVENT_SOURCE = "opendesk://call-center"
CALL_EVENT_API_VERSION = "v1"
RECORDING_LINK_TTL_SECONDS = 3600

TRAJECTORY_EVENT_MAP: dict[str, str] = {
    "call_created": "call.created",
    "customer_connected": "call.customer.connected",
    "queue_entered": "call.queue.entered",
    "reception_started": "call.agent.connected",
    "reception_ended": "call.agent.disconnected",
    "human_service_ended": "call.agent.disconnected",
    "transfer_completed": "call.transfer.completed",
    "recording_completed": "call.recording.completed",
    "recording_partial": "call.recording.completed",
    "recording_failed": "call.recording.failed",
}

# Events that may happen at most once per call use the call as identity.
_ONCE_PER_CALL = frozenset({"call.created", "call.customer.connected"})
_RECORDING_EVENTS = frozenset({"call.recording.completed", "call.recording.failed"})

_RECORDING_PHASES = {"llm": "bot", "bridged": "human", "agent": "human"}


def public_recording_phase(phase: str | None) -> str:
    """Map media-platform recording phases to the stable public values."""
    return _RECORDING_PHASES.get(phase or "", "other")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _int_or_none(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return int(value) if value.isdigit() else None


@dataclass(frozen=True)
class _BuiltEvent:
    identity: str
    occurred_at: datetime
    sequence: int | None
    body: dict


def _employee_brief(employee: Employee | None) -> dict | None:
    if employee is None:
        return None
    return {
        "username": employee.username,
        "name": employee.display_name or employee.nickname or employee.name or employee.username,
    }


async def _employee(db: AsyncSession, tenant_id: int, employee_id: int | None) -> Employee | None:
    if employee_id is None:
        return None
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != tenant_id:
        return None
    return employee


class CallEventPublisher:
    @staticmethod
    def event_id(event_type: str, identity: str) -> str:
        """Derive a stable event ID so retries and duplicate facts collapse."""
        return str(uuid5(NAMESPACE_URL, f"{CALL_EVENT_SOURCE}/{event_type}/{identity}"))

    @staticmethod
    async def publish_trajectory_event(
        db: AsyncSession, record: "CallRecord", event: CallEvent, *, event_type: str
    ) -> None:
        """Publish the external event mapped from a newly appended trajectory fact."""
        external_type = TRAJECTORY_EVENT_MAP.get(event_type)
        if external_type is None:
            return

        async def build() -> _BuiltEvent | None:
            if external_type in _RECORDING_EVENTS:
                recording = await CallEventPublisher._recording_for_event(db, record, event)
                if recording is None:
                    return None
                identity = str(recording.public_id)
                body = await CallEventPublisher._recording_body(
                    recording, failed=external_type == "call.recording.failed"
                )
            else:
                identity = (
                    str(record.public_id)
                    if external_type in _ONCE_PER_CALL
                    else event.event_id
                )
                body = await CallEventPublisher._trajectory_body(
                    db, record, event, external_type
                )
            return _BuiltEvent(identity, event.occurred_at, event.sequence_no, body)

        await CallEventPublisher._publish(db, record, external_type, build)

    @staticmethod
    async def publish_call_ended(db: AsyncSession, record: "CallRecord") -> None:
        """Publish after the ``call_ended`` fact, the latest trajectory event."""

        async def build() -> _BuiltEvent:
            return _BuiltEvent(
                str(record.public_id),
                record.ended_at or datetime.now(timezone.utc),
                await CallEventPublisher._latest_sequence(db, record.id),
                {"ended_at": _iso(record.ended_at)},
            )

        await CallEventPublisher._publish(db, record, "call.ended", build)

    @staticmethod
    async def publish_satisfaction_completed(
        db: AsyncSession, record: "CallRecord", execution, first_answer
    ) -> None:
        async def build() -> _BuiltEvent:
            return _BuiltEvent(
                str(record.public_id),
                execution.ended_at or datetime.now(timezone.utc),
                await CallEventPublisher._latest_sequence(db, record.id),
                {
                    "status": execution.status,
                    "result": (
                        {
                            "option_id": first_answer.option_id,
                            "option_label": first_answer.option_label_snapshot,
                        }
                        if first_answer is not None
                        else None
                    ),
                    "trigger_source": execution.trigger_source,
                    "completed_at": _iso(execution.ended_at),
                },
            )

        await CallEventPublisher._publish(
            db, record, "call.satisfaction.completed", build
        )

    @staticmethod
    async def _latest_sequence(db: AsyncSession, call_record_id: int) -> int | None:
        return (
            await db.execute(
                select(func.max(CallEvent.sequence_no)).where(
                    CallEvent.call_record_id == call_record_id
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _publish(
        db: AsyncSession,
        record: "CallRecord",
        event_type: str,
        build: Callable[[], Awaitable[_BuiltEvent | None]],
    ) -> None:
        """Match rules and enqueue; never raises into the call fact transaction."""
        tenant_id = getattr(record, "tenant_id", None)
        try:
            version, rules = await CallEventRuleCache.lookup(tenant_id)
            if rules is not None and not CallEventPublisher._match(
                rules, event_type, record
            ):
                return
            async with db.begin_nested():
                if rules is None:
                    rules = await CallEventRuleCache.load(db, tenant_id, version)
                rule_ids = CallEventPublisher._match(rules, event_type, record)
                if not rule_ids:
                    return
                subscriptions = await CallEventSubscriptionRepository.list_deliverable_subscriptions(
                    db, tenant_id=tenant_id, rule_ids=rule_ids
                )
                if not subscriptions:
                    return
                built = await build()
                if built is None:
                    return
                payload = {
                    "sequence": built.sequence,
                    "call": await CallEventPublisher._call_body(
                        db, record, final=event_type == "call.ended"
                    ),
                    "event": built.body,
                }
                await EventDeliveryService.enqueue_resolved_in_transaction(
                    db,
                    tenant_id=tenant_id,
                    subscriptions=subscriptions,
                    source_module=CALL_EVENT_SOURCE,
                    event_type=event_type,
                    event_id=CallEventPublisher.event_id(event_type, built.identity),
                    occurred_at=built.occurred_at,
                    payload=payload,
                    api_version=CALL_EVENT_API_VERSION,
                    subject=f"call/{record.public_id}",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "call event publish failed tenant_id=%s call_public_id=%s "
                "event_type=%s error_type=%s",
                tenant_id,
                getattr(record, "public_id", None),
                event_type,
                type(exc).__name__,
            )

    @staticmethod
    def _match(rules, event_type: str, record: "CallRecord") -> list[int]:
        return [
            rule.id
            for rule in rules
            if rule.matches(
                event_type=event_type,
                direction=record.direction,
                call_source=record.call_source,
            )
        ]

    @staticmethod
    async def _call_body(db: AsyncSession, record: "CallRecord", *, final: bool) -> dict:
        tenant_id = record.tenant_id
        user = None
        if record.user_id is not None:
            user_row = await UserRepository.get_by_id(db, record.user_id)
            if user_row is not None and user_row.tenant_id == tenant_id:
                user = {"public_id": str(user_row.public_id)}
        initiator = await _employee(db, tenant_id, record.initiator_agent_id)
        last_serving = await _employee(db, tenant_id, record.last_serving_agent_id)
        last_queue = None
        if record.last_queue_type and record.last_queue_id is not None:
            from app.services.call_record_service import _queue_record_brief

            brief = await _queue_record_brief(
                db, tenant_id, record.last_queue_type, record.last_queue_id
            )
            last_queue = {
                "type": record.last_queue_type,
                "name": brief["name"] if brief else None,
            }
        body = {
            "public_id": str(record.public_id),
            "direction": record.direction,
            "source": record.call_source,
            "lifecycle_status": record.lifecycle_status,
            "customer_number": record.customer_number,
            "service_number": record.service_number,
            "user": user,
            "initiator_agent": _employee_brief(initiator)
            or (
                {"username": None, "name": record.initiator_agent_name_snapshot}
                if record.initiator_agent_name_snapshot
                else None
            ),
            "last_serving_agent": _employee_brief(last_serving),
            "last_queue": last_queue,
            "started_at": _iso(record.started_at),
            "customer_connected_at": _iso(record.customer_connected_at),
            "ended_at": _iso(record.ended_at),
            "external_context": record.external_context,
        }
        if final:
            body.update(
                {
                    "finalization_status": record.finalization_status,
                    "call_result": record.call_result,
                    "hangup_party": record.hangup_party,
                    "hangup_reason_code": record.hangup_reason_code,
                    "actual_reception_type": record.actual_reception_type,
                    "total_duration_ms": record.total_duration_ms,
                    "customer_ring_duration_ms": record.customer_ring_duration_ms,
                    "agent_wait_duration_ms": record.agent_wait_duration_ms,
                    "customer_agent_talk_duration_ms": record.customer_agent_talk_duration_ms,
                    "recording_status": record.recording_status,
                    "custom_business_info": record.custom_business_info,
                }
            )
        return body

    @staticmethod
    async def _trajectory_body(
        db: AsyncSession, record: "CallRecord", event: CallEvent, event_type: str
    ) -> dict:
        tenant_id = record.tenant_id
        if event_type == "call.created":
            return {"created_at": _iso(event.occurred_at)}
        if event_type == "call.customer.connected":
            return {"connected_at": _iso(event.occurred_at)}
        if event_type == "call.queue.entered":
            return {
                "queue": {
                    "type": event.queue_type,
                    "name": event.queue_name_snapshot or event.target_name_snapshot,
                },
                "entered_at": _iso(event.occurred_at),
            }
        if event_type in {"call.agent.connected", "call.agent.disconnected"}:
            agent_id = (
                _int_or_none(event.target_id)
                if event.target_type == "employee"
                else _int_or_none(event.actor_id)
            )
            if agent_id is None:
                agent_id = _int_or_none(event.actor_id)
            body = {"agent": _employee_brief(await _employee(db, tenant_id, agent_id))}
            if event_type == "call.agent.connected":
                body["connected_at"] = _iso(event.occurred_at)
            else:
                body["disconnected_at"] = _iso(event.occurred_at)
                body["duration_ms"] = event.duration_ms
            return body
        if event_type == "call.transfer.completed":
            return await CallEventPublisher._transfer_body(db, tenant_id, event)
        return {}

    @staticmethod
    async def _transfer_body(db: AsyncSession, tenant_id: int, event: CallEvent) -> dict:
        from_agent = _employee_brief(
            await _employee(db, tenant_id, _int_or_none(event.actor_id))
        )
        target_agent = None
        if event.target_type == "employee":
            target_agent = _employee_brief(
                await _employee(db, tenant_id, _int_or_none(event.target_id))
            )
        if event.target_type == "external_number":
            transfer_type = "external"
            target = {"type": "external"}
        elif event.queue_type or event.target_type in {"queue", "employee_group"}:
            transfer_type = "queue"
            target = {
                "type": "queue",
                "queue": {
                    "type": event.queue_type or event.target_type,
                    "name": event.queue_name_snapshot
                    or (None if event.target_type == "employee" else event.target_name_snapshot),
                },
                "agent": target_agent,
            }
        else:
            transfer_type = "agent"
            target = {"type": "agent", "agent": target_agent}
        return {
            "transfer_type": transfer_type,
            "from_agent": from_agent,
            "target": target,
            "completed_at": _iso(event.occurred_at),
        }

    @staticmethod
    async def _recording_for_event(
        db: AsyncSession, record: "CallRecord", event: CallEvent
    ) -> CallRecording | None:
        recording_id = (event.details or {}).get("recording_id")
        if not recording_id:
            return None
        recording = await CallRecordingRepository.get_by_recording_id(
            db, record.tenant_id, str(recording_id)
        )
        if (
            recording is None
            or recording.call_record_id != record.id
            or recording.public_id is None
        ):
            return None
        return recording

    @staticmethod
    async def _recording_body(recording: CallRecording, *, failed: bool) -> dict:
        download_url = None
        expires_at = None
        if not failed and recording.storage_key:
            from app.libs.storage.factory import create_storage_client

            issued_at = datetime.now(timezone.utc)
            download_url = await create_storage_client().get_temporary_url(
                recording.storage_key, expires_seconds=RECORDING_LINK_TTL_SECONDS
            )
            expires_at = _iso(issued_at + timedelta(seconds=RECORDING_LINK_TTL_SECONDS))
        return {
            "recording": {
                "public_id": str(recording.public_id),
                "phase": public_recording_phase(recording.phase),
                "status": recording.status,
                "started_at": _iso(recording.started_at),
                "ended_at": _iso(recording.ended_at),
                "duration_ms": recording.duration_ms,
                "download_url": download_url,
                "download_url_expires_at": expires_at,
                "failure_reason": "recording_failed" if failed else None,
            }
        }
