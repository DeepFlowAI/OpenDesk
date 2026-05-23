from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.repositories.employee_repository import EmployeeRepository
from app.repositories.satisfaction_survey_record_repository import SatisfactionSurveyRecordRepository
from app.schemas.satisfaction_survey_record import SatisfactionSubmissionPayload, SatisfactionSubmissionTypePayload
from app.services.satisfaction_survey_config_service import SatisfactionSurveyConfigService
from app.services.satisfaction_survey_record_service import SatisfactionSurveyRecordService


def _snapshot(limit_one_response_per_type: bool = False) -> dict:
    data = SatisfactionSurveyConfigService.default_payload().model_dump(mode="json")
    data["triggers"]["limit_one_response_per_type"] = limit_one_response_per_type
    return data


def _result(survey_type: str, option_name: str, submitted_at: datetime) -> dict:
    return {
        "type": survey_type,
        "rating_mode": "stars",
        "section_title": "服务满意度" if survey_type == "service" else "产品满意度",
        "option_key": f"{survey_type}-stars-4",
        "option_name": option_name,
        "labels": [],
        "remark": "",
        "resolved": True if survey_type == "service" else None,
        "submitted_at": submitted_at.isoformat(),
    }


def test_public_initiate_requires_user_initiated_trigger():
    snapshot = _snapshot()
    conversation = SimpleNamespace(status="active")

    assert (
        SatisfactionSurveyRecordService._public_initiate_disabled_reason(
            conversation,
            snapshot,
            None,
        )
        == "user_initiated_disabled"
    )

    snapshot["triggers"]["user_initiated"] = True

    assert SatisfactionSurveyRecordService._public_initiate_disabled_reason(
        conversation,
        snapshot,
        None,
    ) is None


@pytest.mark.asyncio
async def test_user_initiated_invitation_creates_visitor_record(monkeypatch):
    snapshot = _snapshot()
    snapshot["triggers"]["user_initiated"] = True
    conversation = SimpleNamespace(
        id=34,
        tenant_id=1,
        status="active",
        visitor_id=56,
        channel_id=78,
        public_id="conv_public_34",
        visitor=SimpleNamespace(name="Ada", external_id="visitor-1"),
    )
    captured: dict = {}

    async def load_conversation(*_args, **_kwargs):
        return conversation

    async def current_snapshot(*_args, **_kwargs):
        return 3, snapshot

    async def get_existing(*_args, **_kwargs):
        return None

    async def create_or_update(_db, _conversation_id, data):
        captured["record_data"] = data
        return SimpleNamespace(id=77, **data)

    monkeypatch.setattr(SatisfactionSurveyRecordService, "_load_conversation_for_visitor", load_conversation)
    monkeypatch.setattr(SatisfactionSurveyRecordService, "_current_snapshot", current_snapshot)
    monkeypatch.setattr(SatisfactionSurveyRecordRepository, "get_by_conversation", get_existing)
    monkeypatch.setattr(SatisfactionSurveyRecordRepository, "create_or_update_record", create_or_update)

    response = await SatisfactionSurveyRecordService.create_user_initiated_invitation(
        object(),
        conversation_public_id=conversation.public_id,
        visitor_context={"tenant_id": 1, "channel_id": 78, "visitor_external_id": "visitor-1"},
    )

    assert captured["record_data"]["invitation_source"] == "visitor"
    assert captured["record_data"]["invited_by_id"] == conversation.visitor_id
    assert captured["record_data"]["survey_types"] == ["service", "product"]
    assert response["can_initiate"] is True
    assert response["invitation"]["id"] == 77


@pytest.mark.asyncio
async def test_session_end_invitation_creates_system_record(monkeypatch):
    snapshot = _snapshot()
    conversation = SimpleNamespace(
        id=34,
        tenant_id=1,
        status="closed",
        visitor_id=56,
        channel_id=78,
        public_id="conv_public_34",
        agent_id=7,
    )
    captured: dict = {}

    async def current_snapshot(*_args, **_kwargs):
        return 3, snapshot

    async def get_existing(*_args, **_kwargs):
        return None

    async def create_or_update(_db, _conversation_id, data, event_data):
        captured["record_data"] = data
        captured["event_data"] = event_data
        record = SimpleNamespace(id=77, **data)
        event = SimpleNamespace(id=99, record_id=record.id, **event_data)
        return record, event

    async def emit_noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(SatisfactionSurveyRecordService, "_current_snapshot", current_snapshot)
    monkeypatch.setattr(SatisfactionSurveyRecordRepository, "get_by_conversation", get_existing)
    monkeypatch.setattr(SatisfactionSurveyRecordRepository, "create_or_update_invitation", create_or_update)
    monkeypatch.setattr(SatisfactionSurveyRecordService, "emit_invitation_event", emit_noop)

    response = await SatisfactionSurveyRecordService.send_session_end_invitation(
        object(),
        conversation,
    )

    assert captured["record_data"]["invitation_source"] == "system"
    assert captured["record_data"]["invited_by_id"] is None
    assert captured["record_data"]["status"] == "invited"
    assert captured["record_data"]["survey_types"] == ["service", "product"]
    assert captured["event_data"]["metadata_"]["invitation_trigger"] == "session_end"
    assert response["record"]["id"] == 77


@pytest.mark.asyncio
async def test_session_end_invitation_skips_submitted_feedback_when_limited(monkeypatch):
    snapshot = _snapshot(limit_one_response_per_type=True)
    submitted_at = datetime(2026, 5, 21, 8, 30, tzinfo=timezone.utc)
    existing = SimpleNamespace(
        id=12,
        status="submitted",
        service_result=_result("service", "满意", submitted_at),
        product_result=None,
        submitted_at=submitted_at,
    )
    conversation = SimpleNamespace(
        id=34,
        tenant_id=1,
        status="closed",
        visitor_id=56,
        channel_id=78,
        public_id="conv_public_34",
        agent_id=7,
    )

    async def current_snapshot(*_args, **_kwargs):
        return 3, snapshot

    async def get_existing(*_args, **_kwargs):
        return existing

    async def create_or_update(*_args, **_kwargs):
        raise AssertionError("submitted feedback must not create a session-end invite")

    monkeypatch.setattr(SatisfactionSurveyRecordService, "_current_snapshot", current_snapshot)
    monkeypatch.setattr(SatisfactionSurveyRecordRepository, "get_by_conversation", get_existing)
    monkeypatch.setattr(SatisfactionSurveyRecordRepository, "create_or_update_invitation", create_or_update)

    response = await SatisfactionSurveyRecordService.send_session_end_invitation(
        object(),
        conversation,
    )

    assert response is None


def test_disabled_remark_switch_ignores_option_remark_requirement():
    snapshot = _snapshot()
    settings = snapshot["service"]
    settings["remark_enabled"] = False
    option = settings["rating_options"][0]

    assert option["remark_requirement"] == "required"

    result = SatisfactionSurveyRecordService._validate_type_submission(
        "service",
        settings,
        SatisfactionSubmissionTypePayload(
            rating_option_key=option["key"],
            remark="should not persist",
            resolved=True,
        ),
        datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc),
    )

    assert result["remark"] == ""


@pytest.mark.asyncio
async def test_resending_invitation_preserves_existing_feedback_when_repeat_allowed(monkeypatch):
    snapshot = _snapshot(limit_one_response_per_type=False)
    submitted_at = datetime(2026, 5, 21, 8, 30, tzinfo=timezone.utc)
    old_service_result = _result("service", "满意", submitted_at)
    old_product_result = _result("product", "好用", submitted_at)
    existing = SimpleNamespace(
        id=12,
        status="submitted",
        service_result=old_service_result,
        product_result=old_product_result,
        submitted_at=submitted_at,
    )
    conversation = SimpleNamespace(
        id=34,
        tenant_id=1,
        agent_id=7,
        status="active",
        visitor_id=56,
        channel_id=78,
        public_id="conv_public_34",
    )
    captured: dict = {}

    async def load_conversation(*_args, **_kwargs):
        return conversation

    async def current_snapshot(*_args, **_kwargs):
        return 3, snapshot

    async def get_existing(*_args, **_kwargs):
        return existing

    async def get_actor(*_args, **_kwargs):
        return SimpleNamespace(display_name="Agent Lee", name="agent")

    async def create_or_update(_db, _conversation_id, data, event_data):
        captured["record_data"] = data
        record = SimpleNamespace(id=existing.id, **data)
        event = SimpleNamespace(id=99, record_id=record.id, **event_data)
        return record, event

    async def emit_noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(SatisfactionSurveyRecordService, "_load_conversation_for_agent", load_conversation)
    monkeypatch.setattr(SatisfactionSurveyRecordService, "_current_snapshot", current_snapshot)
    monkeypatch.setattr(SatisfactionSurveyRecordRepository, "get_by_conversation", get_existing)
    monkeypatch.setattr(EmployeeRepository, "get_by_id", get_actor)
    monkeypatch.setattr(SatisfactionSurveyRecordRepository, "create_or_update_invitation", create_or_update)
    monkeypatch.setattr(SatisfactionSurveyRecordService, "emit_invitation_event", emit_noop)

    await SatisfactionSurveyRecordService.send_agent_invitation(
        object(),
        conversation_id=conversation.id,
        tenant_id=conversation.tenant_id,
        user={"user_id": conversation.agent_id, "tenant_id": conversation.tenant_id, "roles": ["agent"]},
        force=True,
    )

    assert captured["record_data"]["status"] == "invited"
    assert captured["record_data"]["service_result"] == old_service_result
    assert captured["record_data"]["product_result"] == old_product_result
    assert captured["record_data"]["submitted_at"] == submitted_at


@pytest.mark.asyncio
async def test_submission_replaces_previous_feedback_as_one_survey_response(monkeypatch):
    snapshot = _snapshot(limit_one_response_per_type=False)
    snapshot["product"]["enabled"] = False
    submitted_at = datetime(2026, 5, 21, 8, 30, tzinfo=timezone.utc)
    old_product_result = _result("product", "好用", submitted_at)
    record = SimpleNamespace(
        id=12,
        tenant_id=1,
        conversation_id=34,
        config_version=3,
        config_snapshot=snapshot,
        invitation_source="agent",
        invited_by_id=7,
        invited_by_name="Agent Lee",
        invited_at=submitted_at,
        status="invited",
        survey_types=["service"],
        service_result=None,
        product_result=old_product_result,
        submitted_at=submitted_at,
    )
    conversation = SimpleNamespace(
        id=34,
        public_id="conv_public_34",
        visitor_id=56,
        visitor=SimpleNamespace(name="Visitor"),
    )
    captured: dict = {}

    async def load_conversation(*_args, **_kwargs):
        return conversation

    async def get_existing(*_args, **_kwargs):
        return record

    async def save_submission(_db, existing_record, data, event_data):
        captured["submission_data"] = data
        updated = SimpleNamespace(**vars(existing_record))
        for key, value in data.items():
            setattr(updated, key, value)
        event = SimpleNamespace(id=100, record_id=updated.id, **event_data)
        return updated, event

    async def emit_noop(*_args, **_kwargs):
        return None

    option = snapshot["service"]["rating_options"][3]
    payload = SatisfactionSubmissionPayload(
        service=SatisfactionSubmissionTypePayload(
            rating_option_key=option["key"],
            resolved=True,
        )
    )

    monkeypatch.setattr(SatisfactionSurveyRecordService, "_load_conversation_for_visitor", load_conversation)
    monkeypatch.setattr(SatisfactionSurveyRecordRepository, "get_by_conversation", get_existing)
    monkeypatch.setattr(SatisfactionSurveyRecordRepository, "save_submission", save_submission)
    monkeypatch.setattr(SatisfactionSurveyRecordService, "emit_submission_event", emit_noop)

    await SatisfactionSurveyRecordService.submit_public_feedback(
        object(),
        conversation_public_id=conversation.public_id,
        visitor_context={"tenant_id": 1, "channel_id": 78, "visitor_external_id": "visitor"},
        payload=payload,
    )

    assert captured["submission_data"]["service_result"]["option_key"] == option["key"]
    assert captured["submission_data"]["product_result"] is None
