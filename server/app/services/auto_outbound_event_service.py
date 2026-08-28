"""Task binding rules and event delivery boundary for auto outbound webhooks."""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.auto_outbound import (
    AutoOutboundCallRecord,
    AutoOutboundTarget,
    AutoOutboundTask,
)
from app.models.event_subscription import EventSubscription
from app.repositories.auto_outbound_event_repository import AutoOutboundEventRepository
from app.repositories.auto_outbound_repository import AutoOutboundRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.event_subscription_repository import EventSubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auto_outbound_event import (
    AUTO_OUTBOUND_EVENT_TYPE_SET,
    AutoOutboundBusinessRecordEventPayload,
    AutoOutboundCallEventPayload,
    AutoOutboundEventSubscriptionSave,
    AutoOutboundTaskEventPayload,
)
from app.schemas.permission import EffectivePrincipal
from app.services.event_delivery_service import EventDeliveryService

SUBSCRIPTION_MANAGE_PERMISSION = "engagement.auto_outbound_task.subscription.manage"
AUTO_OUTBOUND_EVENT_SOURCE = "opendesk://engagement/auto-outbound"
AUTO_OUTBOUND_EVENT_API_VERSION = "v1"


class AutoOutboundEventService:
    TASK_UPDATED_FIELDS = frozenset(
        {
            "name", "description", "owner_id", "fields", "execution_mode",
            "voice_flow_id", "voice_flow_name", "transfer_queue_id",
            "voicespeed_agent_id", "voicespeed_agent_name", "intent_result_field_key",
            "queue_id", "pacing_mode", "dial_ratio", "dial_intensity",
            "abandon_rate_limit", "abandon_prompt", "wrapup_seconds", "start_date",
            "end_date", "daily_time_windows", "caller_number_id", "max_concurrency",
            "retry_policy", "daily_per_number_limit", "auto_resume_on_target_append",
        }
    )

    @staticmethod
    def event_id(event_type: str, identity: str) -> str:
        """Derive a stable business event ID from its idempotency boundary."""
        return str(
            uuid5(
                NAMESPACE_URL,
                f"{AUTO_OUTBOUND_EVENT_SOURCE}/{event_type}/{identity}",
            )
        )

    @staticmethod
    def assert_can_manage(principal: EffectivePrincipal) -> None:
        if not principal.has_permission(SUBSCRIPTION_MANAGE_PERMISSION):
            raise ForbiddenError("Permission denied")

    @staticmethod
    async def _get_task(
        db: AsyncSession, principal: EffectivePrincipal, task_id: int
    ) -> AutoOutboundTask:
        task = await AutoOutboundRepository.get_task(db, task_id)
        if task is None or task.tenant_id != principal.tenant_id:
            raise NotFoundError("Auto outbound task not found")
        return task

    @staticmethod
    async def get_configuration(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
    ) -> dict:
        AutoOutboundEventService.assert_can_manage(principal)
        task = await AutoOutboundEventService._get_task(db, principal, task_id)
        binding = await AutoOutboundEventRepository.get_binding(
            db, tenant_id=principal.tenant_id, task_id=task_id
        )
        options = await AutoOutboundEventRepository.list_options(
            db,
            tenant_id=principal.tenant_id,
            current_public_id=binding.subscription_public_id if binding else None,
        )
        option_by_id = {item.public_id: item for item in options}
        selected = option_by_id.get(binding.subscription_public_id) if binding else None
        return {
            "task_id": task.id,
            "task_name": task.name,
            "enabled": binding is not None,
            "binding": (
                {
                    "subscription_public_id": binding.subscription_public_id,
                    "subscription_name": selected.name if selected else "",
                    "subscription_is_active": bool(selected and selected.is_active),
                    "event_types": list(binding.event_types or []),
                }
                if binding
                else None
            ),
            "options": [
                {
                    "public_id": item.public_id,
                    "name": item.name,
                    "is_active": item.is_active,
                }
                for item in options
            ],
            "can_manage_global": principal.is_super_admin,
        }

    @staticmethod
    async def save_configuration(
        db: AsyncSession,
        principal: EffectivePrincipal,
        task_id: int,
        data: AutoOutboundEventSubscriptionSave,
    ) -> dict:
        AutoOutboundEventService.assert_can_manage(principal)
        task = await AutoOutboundEventService._get_task(db, principal, task_id)
        binding = await AutoOutboundEventRepository.get_binding(
            db, tenant_id=principal.tenant_id, task_id=task_id
        )

        if not data.enabled:
            if binding is not None:
                previous_public_id = binding.subscription_public_id
                await AutoOutboundEventRepository.delete_binding(db, binding)
                await AutoOutboundEventService._audit_binding(
                    db,
                    principal=principal,
                    task=task,
                    action="disable",
                    subscription_public_id=previous_public_id,
                    event_count=0,
                )
                await db.commit()
            return await AutoOutboundEventService.get_configuration(db, principal, task_id)

        assert data.subscription_public_id is not None
        subscription = await EventSubscriptionRepository.get_for_tenant(
            db,
            tenant_id=principal.tenant_id,
            public_id=data.subscription_public_id,
        )
        if subscription is None:
            raise NotFoundError("Event subscription is unavailable")
        same_disabled_binding = bool(
            binding
            and binding.subscription_public_id == subscription.public_id
            and not subscription.is_active
        )
        if not subscription.is_active and not same_disabled_binding:
            raise ValidationError("Event subscription is disabled")

        event_types = list(data.event_types)
        if not set(event_types).issubset(AUTO_OUTBOUND_EVENT_TYPE_SET):
            raise ValidationError("Unsupported auto outbound event type")
        action = "enable" if binding is None else "update"
        if binding is None:
            await AutoOutboundEventRepository.add_binding(
                db,
                {
                    "tenant_id": principal.tenant_id,
                    "task_id": task.id,
                    "subscription_id": subscription.id,
                    "subscription_public_id": subscription.public_id,
                    "event_types": event_types,
                    "created_by_employee_id": principal.user_id,
                    "updated_by_employee_id": principal.user_id,
                },
            )
        else:
            binding.subscription_id = subscription.id
            binding.subscription_public_id = subscription.public_id
            binding.event_types = event_types
            binding.updated_by_employee_id = principal.user_id
            await db.flush()
        await AutoOutboundEventService._audit_binding(
            db,
            principal=principal,
            task=task,
            action=action,
            subscription_public_id=subscription.public_id,
            event_count=len(event_types),
        )
        await db.commit()
        return await AutoOutboundEventService.get_configuration(db, principal, task_id)

    @staticmethod
    async def _audit_binding(
        db: AsyncSession,
        *,
        principal: EffectivePrincipal,
        task: AutoOutboundTask,
        action: str,
        subscription_public_id: UUID | None,
        event_count: int,
    ) -> None:
        await AutoOutboundEventRepository.add_audit(
            db,
            {
                "tenant_id": principal.tenant_id,
                "task_id": task.id,
                "task_public_id": task.id,
                "subscription_public_id": subscription_public_id,
                "action": action,
                "actor_employee_id": principal.user_id,
                "metadata_json": {"event_count": event_count},
            },
        )

    @staticmethod
    async def enqueue_if_selected(
        db: AsyncSession,
        *,
        tenant_id: int,
        task_id: int,
        event_type: str,
        event_id: str,
        occurred_at: datetime,
        subject: str,
        payload: dict,
    ) -> list[UUID]:
        """Write the immutable delivery snapshot inside the caller's transaction."""
        if event_type not in AUTO_OUTBOUND_EVENT_TYPE_SET:
            raise ValidationError("Unsupported auto outbound event type")
        subscription = await AutoOutboundEventService._selected_subscription(
            db,
            tenant_id=tenant_id,
            task_id=task_id,
            event_type=event_type,
        )
        if subscription is None:
            return []
        return await AutoOutboundEventService._enqueue_selected(
            db,
            tenant_id=tenant_id,
            subscription=subscription,
            event_type=event_type,
            event_id=event_id,
            occurred_at=occurred_at,
            subject=subject,
            payload=payload,
        )

    @staticmethod
    async def _selected_subscription(
        db: AsyncSession,
        *,
        tenant_id: int,
        task_id: int,
        event_type: str,
    ) -> EventSubscription | None:
        if event_type not in AUTO_OUTBOUND_EVENT_TYPE_SET:
            raise ValidationError("Unsupported auto outbound event type")
        resolved = await AutoOutboundEventRepository.get_binding_with_subscription(
            db, tenant_id=tenant_id, task_id=task_id
        )
        if resolved is None:
            return None
        binding, subscription = resolved
        if event_type not in set(binding.event_types or []) or not subscription.is_active:
            return None
        return subscription

    @staticmethod
    async def _enqueue_selected(
        db: AsyncSession,
        *,
        tenant_id: int,
        subscription: EventSubscription,
        event_type: str,
        event_id: str,
        occurred_at: datetime,
        subject: str,
        payload: dict,
    ) -> list[UUID]:
        return await EventDeliveryService.enqueue_resolved_in_transaction(
            db,
            tenant_id=tenant_id,
            subscriptions=[subscription],
            source_module=AUTO_OUTBOUND_EVENT_SOURCE,
            event_type=event_type,
            event_id=event_id,
            occurred_at=occurred_at,
            payload=payload,
            api_version=AUTO_OUTBOUND_EVENT_API_VERSION,
            subject=subject,
        )

    @staticmethod
    def changed_task_fields(task: AutoOutboundTask, payload: dict) -> list[str]:
        return sorted(
            key
            for key, value in payload.items()
            if key in AutoOutboundEventService.TASK_UPDATED_FIELDS
            and AutoOutboundEventService._json_value(getattr(task, key, None))
            != AutoOutboundEventService._json_value(value)
        )

    @staticmethod
    def _json_value(value):
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(key): AutoOutboundEventService._json_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [AutoOutboundEventService._json_value(item) for item in value]
        return value

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    async def _user_snapshot(db: AsyncSession, user_id: int | None) -> dict | None:
        if user_id is None:
            return None
        user = await UserRepository.get_by_id(db, user_id)
        if user is None:
            return None
        return {"public_id": user.public_id}

    @staticmethod
    async def _employee_snapshot(
        db: AsyncSession, employee_id: int | None
    ) -> dict | None:
        if employee_id is None:
            return None
        employee = await EmployeeRepository.get_by_id(db, employee_id)
        if employee is None:
            return None
        return {"name": employee.display_name or employee.name or employee.username}

    @staticmethod
    async def _call_record_public_id(
        db: AsyncSession, tenant_id: int, call_record_id: int | None
    ) -> str | None:
        if call_record_id is None:
            return None
        public_ids = await AutoOutboundRepository.list_call_record_public_ids(
            db, tenant_id, [call_record_id]
        )
        return public_ids.get(call_record_id)

    @staticmethod
    def _safe_reception_result(value: dict | None) -> dict | None:
        if not isinstance(value, dict):
            return None
        allowed = {"assigned", "transferred", "handoff", "abandoned"}
        result = {
            key: bool(value[key])
            for key in allowed
            if key in value and isinstance(value[key], bool)
        }
        return result or None

    @staticmethod
    def _remaining_retries(task: AutoOutboundTask, target: AutoOutboundTarget) -> int:
        terminal = target.last_call_result
        policy = task.retry_policy or {}
        item = policy.get(terminal) if terminal else None
        if not isinstance(item, dict):
            return 0
        maximum = int(item.get("max_retries", 0) or 0)
        used = int((target.retry_counts or {}).get(terminal, 0) or 0)
        return max(0, maximum - used)

    @staticmethod
    async def call_snapshot(
        db: AsyncSession,
        *,
        task: AutoOutboundTask,
        target: AutoOutboundTarget,
        record: AutoOutboundCallRecord,
    ) -> dict:
        return {
            "task": {
                "id": task.id,
                "name": task.name,
                "execution_mode": task.execution_mode,
            },
            "target": {
                "id": target.id,
                "phone_number": target.phone_number,
                "user": await AutoOutboundEventService._user_snapshot(
                    db, target.user_id
                ),
                "status": target.status,
                "last_call_result": target.last_call_result,
                "next_call_at": AutoOutboundEventService._iso(target.next_call_at),
                "remaining_retries": AutoOutboundEventService._remaining_retries(
                    task, target
                ),
                "updated_at": AutoOutboundEventService._iso(
                    getattr(target, "updated_at", None)
                ),
            },
            "call": {
                "id": record.id,
                "attempt_id": record.attempt_id,
                "attempt_no": record.attempt_no,
                "call_record_public_id": (
                    await AutoOutboundEventService._call_record_public_id(
                        db, task.tenant_id, record.call_record_id
                    )
                ),
                "started_at": AutoOutboundEventService._iso(record.started_at),
                "answered_at": AutoOutboundEventService._iso(record.answered_at),
                "ended_at": AutoOutboundEventService._iso(record.ended_at),
                "duration_ms": int(record.duration_ms or 0),
                "terminal_state": record.terminal_state,
                "reception_type": record.reception_type,
                "agent": await AutoOutboundEventService._employee_snapshot(
                    db, record.agent_id
                ),
                "reception": AutoOutboundEventService._safe_reception_result(
                    record.reception_result
                ),
            },
        }

    @staticmethod
    async def emit_call_event(
        db: AsyncSession,
        *,
        task: AutoOutboundTask,
        target: AutoOutboundTarget,
        record: AutoOutboundCallRecord,
        event_type: str,
        occurred_at: datetime,
    ) -> list[UUID]:
        subscription = await AutoOutboundEventService._selected_subscription(
            db,
            tenant_id=task.tenant_id,
            task_id=task.id,
            event_type=event_type,
        )
        if subscription is None:
            return []
        payload = AutoOutboundCallEventPayload.model_validate(
            await AutoOutboundEventService.call_snapshot(
                db, task=task, target=target, record=record
            )
        ).model_dump(mode="json", exclude_unset=True)
        return await AutoOutboundEventService._enqueue_selected(
            db,
            tenant_id=task.tenant_id,
            subscription=subscription,
            event_type=event_type,
            event_id=AutoOutboundEventService.event_id(
                event_type,
                record.attempt_id or f"record:{record.id}",
            ),
            occurred_at=occurred_at,
            subject=f"auto-outbound-record/{record.id}",
            payload=payload,
        )

    @staticmethod
    def _safe_file_value(value) -> list[dict]:
        items = value if isinstance(value, list) else []
        result = []
        for item in items:
            if not isinstance(item, dict) or not item.get("file_id"):
                continue
            try:
                size = int(item.get("size") or 0)
            except (TypeError, ValueError):
                size = 0
            result.append(
                {
                    "file_id": str(item["file_id"]),
                    "name": str(item.get("name") or item.get("filename") or ""),
                    "mime_type": str(item.get("mime_type") or ""),
                    "size": size,
                }
            )
        return result

    @staticmethod
    async def business_record_snapshot(
        db: AsyncSession,
        *,
        task: AutoOutboundTask,
        target: AutoOutboundTarget,
        record: AutoOutboundCallRecord | None,
        actor: dict,
        keys_name: str,
        keys: list[str],
        occurred_at: datetime,
    ) -> dict:
        values = target.field_values or {}
        fields = []
        definitions = AutoOutboundEventService._field_definitions(task.fields)
        for definition in definitions:
            key = definition["key"]
            value = values.get(key)
            if definition["field_type"] == "file":
                value = AutoOutboundEventService._safe_file_value(value)
            else:
                value = AutoOutboundEventService._json_value(value)
            fields.append({**definition, "value": value})
        return {
            "task": {
                "id": task.id,
                "name": task.name,
                "template_name": task.template_name,
            },
            "target": {
                "id": target.id,
                "phone_number": target.phone_number,
                "user": await AutoOutboundEventService._user_snapshot(
                    db, target.user_id
                ),
                "fields": fields,
                "updated_at": AutoOutboundEventService._iso(
                    getattr(target, "updated_at", None)
                ),
            },
            "call": (
                {
                    "id": record.id,
                    "call_record_public_id": (
                        await AutoOutboundEventService._call_record_public_id(
                            db, task.tenant_id, record.call_record_id
                        )
                    ),
                }
                if record is not None
                else None
            ),
            "actor": actor,
            keys_name: sorted(set(keys) & {item["key"] for item in definitions}),
            "occurred_at": AutoOutboundEventService._iso(occurred_at),
        }

    @staticmethod
    async def emit_business_record_event(
        db: AsyncSession,
        *,
        task: AutoOutboundTask,
        target: AutoOutboundTarget,
        record: AutoOutboundCallRecord | None,
        event_type: str,
        occurred_at: datetime,
        actor: dict | None = None,
        principal: EffectivePrincipal | None = None,
        keys_name: str,
        keys: list[str],
    ) -> list[UUID]:
        subscription = await AutoOutboundEventService._selected_subscription(
            db,
            tenant_id=task.tenant_id,
            task_id=task.id,
            event_type=event_type,
        )
        if subscription is None:
            return []
        resolved_actor = actor or await AutoOutboundEventService.actor_snapshot(
            db, principal
        )
        payload = AutoOutboundBusinessRecordEventPayload.model_validate(
            await AutoOutboundEventService.business_record_snapshot(
                db,
                task=task,
                target=target,
                record=record,
                actor=resolved_actor,
                keys_name=keys_name,
                keys=keys,
                occurred_at=occurred_at,
            )
        ).model_dump(mode="json", exclude_unset=True)
        version_source = record if record is not None else target
        version = AutoOutboundEventService._iso(
            getattr(version_source, "updated_at", None)
        ) or AutoOutboundEventService._iso(occurred_at)
        entity = f"record:{record.id}" if record is not None else f"target:{target.id}"
        return await AutoOutboundEventService._enqueue_selected(
            db,
            tenant_id=task.tenant_id,
            subscription=subscription,
            event_type=event_type,
            event_id=AutoOutboundEventService.event_id(
                event_type,
                f"{entity}:{version}",
            ),
            occurred_at=occurred_at,
            subject=f"auto-outbound-target/{target.id}",
            payload=payload,
        )

    @staticmethod
    def _field_definitions(fields: list | None) -> list[dict]:
        result = []
        for field in fields or []:
            if not isinstance(field, dict) or not field.get("enabled", True):
                continue
            key = str(field.get("key") or "").strip()
            if not key:
                continue
            result.append(
                {
                    "key": key,
                    "name": str(field.get("name") or key),
                    "field_type": str(field.get("field_type") or "single_line_text"),
                    "required": bool(field.get("required")),
                    "agent_editable": bool(field.get("agent_editable")),
                }
            )
        return result

    @staticmethod
    async def actor_snapshot(db: AsyncSession, principal: EffectivePrincipal | None) -> dict:
        if principal is None:
            return {"type": "system"}
        api_key_name = getattr(principal, "api_key_name", None)
        if api_key_name:
            return {"type": "api_key", "name": str(api_key_name)}
        employee = (
            await EmployeeRepository.get_by_id(db, principal.user_id)
            if principal.user_id is not None
            else None
        )
        name = None
        if employee is not None:
            name = employee.display_name or employee.name or employee.username
        return {"type": "employee", "name": name}

    @staticmethod
    async def task_snapshot(db: AsyncSession, task: AutoOutboundTask) -> dict:
        stats = (
            await AutoOutboundRepository.task_stats(db, task.tenant_id, [task.id])
        ).get(task.id, {})
        owner = (
            await EmployeeRepository.get_by_id(db, task.owner_id)
            if task.owner_id is not None
            else None
        )
        return {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "status": task.status,
            "execution_mode": task.execution_mode,
            "owner": (
                {"name": owner.display_name or owner.name or owner.username}
                if owner is not None
                else None
            ),
            "template_name": task.template_name,
            "fields": AutoOutboundEventService._field_definitions(task.fields),
            "schedule": {
                "start_date": task.start_date.isoformat(),
                "end_date": task.end_date.isoformat(),
                "daily_time_windows": task.daily_time_windows or [],
            },
            "dial_strategy": {
                "max_concurrency": task.max_concurrency,
                "retry_policy": task.retry_policy or {},
                "daily_per_number_limit": task.daily_per_number_limit,
                "auto_resume_on_target_append": bool(
                    getattr(task, "auto_resume_on_target_append", False)
                ),
            },
            "stats": {
                "total_targets": int(stats.get("total_targets", 0) or 0),
                "finished_targets": int(stats.get("finished_targets", 0) or 0),
                "call_count": int(stats.get("call_count", 0) or 0),
                "answered_count": int(stats.get("answered_count", 0) or 0),
            },
            "updated_at": AutoOutboundEventService._iso(task.updated_at),
        }

    @staticmethod
    async def emit_task_event(
        db: AsyncSession,
        *,
        task: AutoOutboundTask,
        event_type: str,
        occurred_at: datetime,
        actor: dict | None = None,
        principal: EffectivePrincipal | None = None,
        previous_status: str | None = None,
        reason: str | None = None,
        changed_fields: list[str] | None = None,
    ) -> list[UUID]:
        subscription = await AutoOutboundEventService._selected_subscription(
            db,
            tenant_id=task.tenant_id,
            task_id=task.id,
            event_type=event_type,
        )
        if subscription is None:
            return []
        payload_data = {
            "task": await AutoOutboundEventService.task_snapshot(db, task),
            "actor": actor
            or await AutoOutboundEventService.actor_snapshot(db, principal),
        }
        if changed_fields is not None:
            payload_data["changed_fields"] = changed_fields
        if previous_status is not None:
            payload_data["status_change"] = {
                "previous_status": previous_status,
                "current_status": task.status,
                "reason": reason,
                "changed_at": occurred_at.astimezone(timezone.utc).isoformat(),
            }
        payload = AutoOutboundTaskEventPayload.model_validate(
            payload_data
        ).model_dump(mode="json", exclude_unset=True)
        version = AutoOutboundEventService._iso(
            getattr(task, "updated_at", None)
        ) or AutoOutboundEventService._iso(occurred_at)
        return await AutoOutboundEventService._enqueue_selected(
            db,
            tenant_id=task.tenant_id,
            subscription=subscription,
            event_type=event_type,
            event_id=AutoOutboundEventService.event_id(
                event_type,
                f"task:{task.id}:{version}",
            ),
            occurred_at=occurred_at,
            subject=f"auto-outbound-task/{task.id}",
            payload=payload,
        )
