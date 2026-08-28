"""Unit tests for auto outbound event binding and delivery selection."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.repositories.auto_outbound_event_repository import AutoOutboundEventRepository
from app.repositories.auto_outbound_repository import AutoOutboundRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.event_subscription_repository import EventSubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auto_outbound_event import AutoOutboundEventSubscriptionSave
from app.schemas.permission import EffectivePrincipal
from app.services.auto_outbound_event_service import AutoOutboundEventService
from app.services.event_delivery_service import EventDeliveryService


def test_binding_schema_rejects_unknown_event_type() -> None:
    with pytest.raises(PydanticValidationError):
        AutoOutboundEventSubscriptionSave(
            enabled=True,
            subscription_public_id=uuid4(),
            event_types=["auto_outbound.task.created"],
        )


def test_binding_schema_requires_endpoint_and_event_when_enabled() -> None:
    with pytest.raises(PydanticValidationError):
        AutoOutboundEventSubscriptionSave(enabled=True, event_types=[])


@pytest.mark.asyncio
async def test_save_configuration_resolves_selected_subscription(monkeypatch) -> None:
    public_id = uuid4()
    principal = EffectivePrincipal(
        user_id=10,
        tenant_id=7,
        is_super_admin=True,
        permissions=[],
    )
    task = SimpleNamespace(id=3, tenant_id=7)
    subscription = SimpleNamespace(
        id=8,
        tenant_id=7,
        public_id=public_id,
        is_active=True,
    )
    db = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())
    monkeypatch.setattr(
        AutoOutboundEventService,
        "_get_task",
        AsyncMock(return_value=task),
    )
    monkeypatch.setattr(
        AutoOutboundEventRepository,
        "get_binding",
        AsyncMock(return_value=None),
    )
    add_binding = AsyncMock()
    monkeypatch.setattr(AutoOutboundEventRepository, "add_binding", add_binding)
    monkeypatch.setattr(
        EventSubscriptionRepository,
        "get_for_tenant",
        AsyncMock(return_value=subscription),
    )
    monkeypatch.setattr(
        AutoOutboundEventService,
        "_audit_binding",
        AsyncMock(),
    )
    monkeypatch.setattr(
        AutoOutboundEventService,
        "get_configuration",
        AsyncMock(return_value={"enabled": True}),
    )

    result = await AutoOutboundEventService.save_configuration(
        db,
        principal,
        task.id,
        AutoOutboundEventSubscriptionSave(
            enabled=True,
            subscription_public_id=public_id,
            event_types=["auto_outbound.task.started"],
        ),
    )

    assert result == {"enabled": True}
    assert add_binding.await_args.args[1]["subscription_id"] == subscription.id
    db.commit.assert_awaited_once()


def test_call_event_id_is_stable_per_attempt_and_event_type() -> None:
    started = AutoOutboundEventService.event_id(
        "auto_outbound.call.started", "attempt-123"
    )

    assert started == AutoOutboundEventService.event_id(
        "auto_outbound.call.started", "attempt-123"
    )
    assert started != AutoOutboundEventService.event_id(
        "auto_outbound.call.ended", "attempt-123"
    )
    assert started != AutoOutboundEventService.event_id(
        "auto_outbound.call.started", "attempt-456"
    )


@pytest.mark.asyncio
async def test_enqueue_unselected_event_does_not_create_delivery(monkeypatch) -> None:
    binding = SimpleNamespace(event_types=["auto_outbound.task.started"])
    subscription = SimpleNamespace(is_active=True)
    monkeypatch.setattr(
        AutoOutboundEventRepository,
        "get_binding_with_subscription",
        AsyncMock(return_value=(binding, subscription)),
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(EventDeliveryService, "enqueue_resolved_in_transaction", enqueue)

    result = await AutoOutboundEventService.enqueue_if_selected(
        object(),
        tenant_id=7,
        task_id=3,
        event_type="auto_outbound.task.paused",
        event_id="evt-1",
        occurred_at=datetime.now(timezone.utc),
        subject="auto-outbound-task/3",
        payload={},
    )

    assert result == []
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_enqueue_selected_event_uses_caller_session(monkeypatch) -> None:
    public_id = uuid4()
    binding = SimpleNamespace(
        subscription_public_id=public_id,
        event_types=["auto_outbound.task.started"],
    )
    subscription = SimpleNamespace(public_id=public_id, is_active=True)
    monkeypatch.setattr(
        AutoOutboundEventRepository,
        "get_binding_with_subscription",
        AsyncMock(return_value=(binding, subscription)),
    )
    enqueue = AsyncMock(return_value=[uuid4()])
    monkeypatch.setattr(EventDeliveryService, "enqueue_resolved_in_transaction", enqueue)
    db = object()

    result = await AutoOutboundEventService.enqueue_if_selected(
        db,
        tenant_id=7,
        task_id=3,
        event_type="auto_outbound.task.started",
        event_id="evt-1",
        occurred_at=datetime.now(timezone.utc),
        subject="auto-outbound-task/3",
        payload={"task": {"id": 3}},
    )

    assert len(result) == 1
    assert enqueue.await_args.args[0] is db


@pytest.mark.asyncio
async def test_call_event_without_subscription_skips_snapshot_queries(monkeypatch) -> None:
    monkeypatch.setattr(
        AutoOutboundEventRepository,
        "get_binding_with_subscription",
        AsyncMock(return_value=None),
    )
    user_lookup = AsyncMock()
    employee_lookup = AsyncMock()
    call_lookup = AsyncMock()
    monkeypatch.setattr(UserRepository, "get_by_id", user_lookup)
    monkeypatch.setattr(EmployeeRepository, "get_by_id", employee_lookup)
    monkeypatch.setattr(
        AutoOutboundRepository,
        "list_call_record_public_ids",
        call_lookup,
    )

    result = await AutoOutboundEventService.emit_call_event(
        object(),
        task=SimpleNamespace(id=3, tenant_id=7),
        target=SimpleNamespace(),
        record=SimpleNamespace(),
        event_type="auto_outbound.call.ended",
        occurred_at=datetime.now(timezone.utc),
    )

    assert result == []
    user_lookup.assert_not_awaited()
    employee_lookup.assert_not_awaited()
    call_lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_event_uses_stable_whitelisted_snapshot(monkeypatch) -> None:
    now = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
    task = SimpleNamespace(
        id=3,
        tenant_id=7,
        name="Renewal",
        description="Call expiring customers",
        status="paused",
        execution_mode="agent",
        owner_id=9,
        template_name="Renewal template",
        fields=[
            {
                "key": "contract_level",
                "name": "Contract level",
                "field_type": "select",
                "required": True,
                "agent_editable": True,
                "enabled": True,
                "component_config": {"internal": True},
            },
            {"key": "hidden", "name": "Hidden", "enabled": False},
        ],
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        daily_time_windows=[{"start": "09:00", "end": "18:00"}],
        max_concurrency=8,
        retry_policy={"busy": {"max_retries": 1}},
        daily_per_number_limit=3,
        auto_resume_on_target_append=True,
        updated_at=now,
    )
    monkeypatch.setattr(
        AutoOutboundRepository,
        "task_stats",
        AsyncMock(
            return_value={
                3: {
                    "total_targets": 20,
                    "finished_targets": 4,
                    "call_count": 5,
                    "answered_count": 2,
                }
            }
        ),
    )
    monkeypatch.setattr(
        EmployeeRepository,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(display_name="Owner", name="", username="owner")),
    )
    subscription = SimpleNamespace(is_active=True)
    monkeypatch.setattr(
        AutoOutboundEventService,
        "_selected_subscription",
        AsyncMock(return_value=subscription),
    )
    enqueue = AsyncMock(return_value=[])
    monkeypatch.setattr(AutoOutboundEventService, "_enqueue_selected", enqueue)

    await AutoOutboundEventService.emit_task_event(
        object(),
        task=task,
        event_type="auto_outbound.task.paused",
        occurred_at=now,
        actor={"type": "system"},
        previous_status="active",
        reason="queue_finished",
    )

    data = enqueue.await_args.kwargs["payload"]
    assert data["task"]["fields"] == [
        {
            "key": "contract_level",
            "name": "Contract level",
            "field_type": "select",
            "required": True,
            "agent_editable": True,
        }
    ]
    assert data["task"]["stats"] == {
        "total_targets": 20,
        "finished_targets": 4,
        "call_count": 5,
        "answered_count": 2,
    }
    assert data["task"]["dial_strategy"]["auto_resume_on_target_append"] is True
    assert data["status_change"]["reason"] == "queue_finished"
    assert enqueue.await_args.kwargs["subject"] == "auto-outbound-task/3"


@pytest.mark.asyncio
async def test_call_snapshot_excludes_internal_call_details(monkeypatch) -> None:
    now = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
    task = SimpleNamespace(
        id=3,
        tenant_id=7,
        name="Renewal",
        execution_mode="agent",
        retry_policy={"busy": {"max_retries": 2}},
    )
    target = SimpleNamespace(
        id=4,
        phone_number="13800138000",
        user_id=5,
        status="redial_pending",
        last_call_result="busy",
        next_call_at=now,
        retry_counts={"busy": 1},
        updated_at=now,
    )
    record = SimpleNamespace(
        id=8,
        attempt_id="attempt-public",
        attempt_no=2,
        call_record_id=11,
        started_at=now,
        answered_at=None,
        ended_at=now,
        duration_ms=123,
        terminal_state="busy",
        reception_type="agent",
        agent_id=9,
        reception_result={
            "assigned": True,
            "abandoned": False,
            "dtmf": "1234",
            "provider_session": "secret",
        },
        fail_reason="raw provider failure",
    )
    monkeypatch.setattr(
        UserRepository,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(public_id="usr_public")),
    )
    monkeypatch.setattr(
        AutoOutboundRepository,
        "list_call_record_public_ids",
        AsyncMock(return_value={11: "call_public"}),
    )
    monkeypatch.setattr(
        EmployeeRepository,
        "get_by_id",
        AsyncMock(return_value=SimpleNamespace(display_name="Agent", name="", username="a")),
    )

    data = await AutoOutboundEventService.call_snapshot(
        object(), task=task, target=target, record=record
    )

    assert data["target"]["user"] == {"public_id": "usr_public"}
    assert data["target"]["remaining_retries"] == 1
    assert data["call"]["call_record_public_id"] == "call_public"
    assert data["call"]["reception"] == {"assigned": True, "abandoned": False}
    assert "fail_reason" not in data["call"]
    assert "tenant_id" not in data["task"]


@pytest.mark.asyncio
async def test_business_snapshot_sanitizes_file_fields() -> None:
    now = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
    task = SimpleNamespace(
        id=3,
        tenant_id=7,
        name="Renewal",
        template_name="Template",
        fields=[
            {
                "key": "attachment",
                "name": "Attachment",
                "field_type": "file",
                "enabled": True,
            },
            {"key": "hidden", "field_type": "single_line_text", "enabled": False},
        ],
    )
    target = SimpleNamespace(
        id=4,
        phone_number="13800138000",
        user_id=None,
        updated_at=now,
        field_values={
            "attachment": [
                {
                    "file_id": "file_public",
                    "filename": "contract.pdf",
                    "mime_type": "application/pdf",
                    "size": 42,
                    "url": "https://signed.example/secret",
                    "object_key": "tenant/secret.pdf",
                    "content": "secret",
                }
            ],
            "hidden": "must not leave",
        },
    )

    data = await AutoOutboundEventService.business_record_snapshot(
        object(),
        task=task,
        target=target,
        record=None,
        actor={"type": "system"},
        keys_name="changed_keys",
        keys=["attachment"],
        occurred_at=now,
    )

    assert data["target"]["fields"] == [
        {
            "key": "attachment",
            "name": "Attachment",
            "field_type": "file",
            "required": False,
            "agent_editable": False,
            "value": [
                {
                    "file_id": "file_public",
                    "name": "contract.pdf",
                    "mime_type": "application/pdf",
                    "size": 42,
                }
            ],
        }
    ]
