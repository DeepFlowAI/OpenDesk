"""
Unit tests for workspace SMS single-send: validation, idempotency, snapshots,
short-session discipline around the channel call, and delivery receipts.
"""
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.sms.base import SmsDeliveryReceipt, SmsSendResult
from app.schemas.sms import SmsSendRequest
from app.services.sms_service import (
    SmsWorkspaceService,
    _render_body_snapshot,
    _validate_variables,
)

VARIABLE_DEFS = [
    {"key": "name", "label": "客户姓名", "required": True},
    {"key": "time", "label": "预约时间", "required": False, "max_length": 20},
]


class _SessionTracker:
    """Tracks open/close of AsyncSessionLocal so tests can prove the channel
    call happens while no DB session is held."""

    def __init__(self):
        self.open_count = 0

    def new_session(self):
        tracker = self

        class _Session:
            def __init__(self):
                self.commit = AsyncMock()

            async def __aenter__(self):
                tracker.open_count += 1
                return self

            async def __aexit__(self, *exc):
                tracker.open_count -= 1
                return False

        return _Session()


def _template_row(template_status="enabled"):
    template = SimpleNamespace(
        id=10,
        name="预约回访提醒",
        type="notify",
        status=template_status,
        body="尊敬的{name}，您预约的回访时间为{time}。",
        variables=VARIABLE_DEFS,
        provider="aliyun",
        provider_template_code="SMS_123456",
    )
    signature = SimpleNamespace(name="深流客服", provider_sign_name="深流客服")
    return SimpleNamespace(id=1), template, signature


def _request(**overrides) -> SmsSendRequest:
    data = {
        "phone": "13800138000",
        "template_id": 10,
        "variables": {"name": "王先生", "time": "8月8日 14:00"},
    }
    data.update(overrides)
    return SmsSendRequest(**data)


def _patch_common(monkeypatch, tracker, *, template_row=None, existing=None, call_record=None):
    monkeypatch.setattr(
        "app.services.sms_service.AsyncSessionLocal", lambda: tracker.new_session()
    )
    monkeypatch.setattr(
        "app.services.sms_service.SmsSendRecordRepository.get_by_client_request_id",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(
        "app.services.sms_service.SmsTemplateGrantRepository.get_granted_template",
        AsyncMock(return_value=template_row),
    )
    call_lookup = AsyncMock(return_value=call_record)
    monkeypatch.setattr(
        "app.services.sms_service.CallRecordRepository.get_by_call_id", call_lookup
    )
    create = AsyncMock(
        return_value=SimpleNamespace(
            id=99, status="pending", fail_reason=None, created_at=datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)
        )
    )
    monkeypatch.setattr("app.services.sms_service.SmsSendRecordRepository.create", create)
    update_send_result = AsyncMock()
    monkeypatch.setattr(
        "app.services.sms_service.SmsSendRecordRepository.update_send_result", update_send_result
    )
    return SimpleNamespace(create=create, update_send_result=update_send_result, call_lookup=call_lookup)


class _FakeClient:
    def __init__(self, result=None, tracker=None, exc=None):
        self.result = result or SmsSendResult(success=True, biz_id="biz-1")
        self.exc = exc
        self.tracker = tracker
        self.calls = []

    async def send_sms(self, **kwargs):
        self.calls.append(kwargs)
        if self.tracker is not None:
            assert self.tracker.open_count == 0, "DB session must be closed during channel call"
        if self.exc is not None:
            raise self.exc
        return self.result


class TestValidateVariables:
    def test_required_missing(self):
        with pytest.raises(ValidationError):
            _validate_variables(VARIABLE_DEFS, {})

    def test_max_length_default_30(self):
        defs = [{"key": "memo", "label": "备注", "required": False}]
        with pytest.raises(ValidationError):
            _validate_variables(defs, {"memo": "x" * 31})
        assert _validate_variables(defs, {"memo": "x" * 30}) == {"memo": "x" * 30}

    def test_unknown_key_rejected(self):
        with pytest.raises(ValidationError):
            _validate_variables(VARIABLE_DEFS, {"name": "王", "ghost": "x"})

    def test_optional_blank_omitted_from_params(self):
        params = _validate_variables(VARIABLE_DEFS, {"name": "王先生"})
        assert params == {"name": "王先生"}

    def test_render_snapshot_keeps_unfilled_placeholder(self):
        assert _render_body_snapshot("您好{name}，{time}见", {"name": "王"}) == "您好王，{time}见"


class TestSendManaged:
    @pytest.mark.asyncio
    async def test_success_submits_and_closes_session_around_channel_call(self, monkeypatch):
        tracker = _SessionTracker()
        repos = _patch_common(monkeypatch, tracker, template_row=_template_row())
        client = _FakeClient(tracker=tracker)
        monkeypatch.setattr("app.services.sms_service.get_sms_client", lambda: client)

        resp = await SmsWorkspaceService.send_managed(tenant_id=1, employee_id=7, payload=_request())

        assert resp.id == 99
        assert resp.status == "submitted"
        assert resp.error_code is None
        assert client.calls[0]["sign_name"] == "深流客服"
        assert client.calls[0]["template_code"] == "SMS_123456"
        assert client.calls[0]["template_params"] == {"name": "王先生", "time": "8月8日 14:00"}
        created = repos.create.await_args.args[1]
        assert created["body_snapshot"] == "尊敬的王先生，您预约的回访时间为8月8日 14:00。"
        assert created["status"] == "pending"
        assert created["call_record_id"] is None
        repos.update_send_result.assert_awaited_once()
        kwargs = repos.update_send_result.await_args.kwargs
        assert kwargs["status"] == "submitted" and kwargs["biz_id"] == "biz-1"

    @pytest.mark.asyncio
    async def test_channel_failure_marks_failed(self, monkeypatch):
        tracker = _SessionTracker()
        repos = _patch_common(monkeypatch, tracker, template_row=_template_row())
        client = _FakeClient(
            result=SmsSendResult(success=False, error_code="isv.AMOUNT_NOT_ENOUGH", error_message="余额不足")
        )
        monkeypatch.setattr("app.services.sms_service.get_sms_client", lambda: client)

        resp = await SmsWorkspaceService.send_managed(tenant_id=1, employee_id=7, payload=_request())

        assert resp.status == "failed"
        assert resp.error_code == "isv.AMOUNT_NOT_ENOUGH"
        assert resp.fail_reason == "isv.AMOUNT_NOT_ENOUGH: 余额不足"
        kwargs = repos.update_send_result.await_args.kwargs
        assert kwargs["status"] == "failed"

    @pytest.mark.asyncio
    async def test_channel_exception_still_marks_failed(self, monkeypatch):
        tracker = _SessionTracker()
        repos = _patch_common(monkeypatch, tracker, template_row=_template_row())
        monkeypatch.setattr(
            "app.services.sms_service.get_sms_client",
            lambda: _FakeClient(exc=RuntimeError("boom")),
        )

        resp = await SmsWorkspaceService.send_managed(tenant_id=1, employee_id=7, payload=_request())

        assert resp.status == "failed"
        assert resp.error_code == "INTERNAL"
        assert repos.update_send_result.await_args.kwargs["status"] == "failed"

    @pytest.mark.asyncio
    async def test_idempotent_hit_returns_existing_without_channel_call(self, monkeypatch):
        tracker = _SessionTracker()
        existing = SimpleNamespace(
            id=55, status="submitted", fail_reason=None, created_at=None
        )
        _patch_common(monkeypatch, tracker, template_row=None, existing=existing)
        client = _FakeClient()
        monkeypatch.setattr("app.services.sms_service.get_sms_client", lambda: client)

        resp = await SmsWorkspaceService.send_managed(
            tenant_id=1, employee_id=7, payload=_request(client_request_id="req-1")
        )

        assert resp.id == 55
        assert resp.status == "submitted"
        assert client.calls == []

    @pytest.mark.asyncio
    async def test_ungranted_template_raises_404(self, monkeypatch):
        tracker = _SessionTracker()
        _patch_common(monkeypatch, tracker, template_row=None)
        with pytest.raises(NotFoundError):
            await SmsWorkspaceService.send_managed(tenant_id=1, employee_id=7, payload=_request())

    @pytest.mark.asyncio
    async def test_disabled_template_raises_400(self, monkeypatch):
        tracker = _SessionTracker()
        _patch_common(monkeypatch, tracker, template_row=_template_row(template_status="disabled"))
        with pytest.raises(ValidationError):
            await SmsWorkspaceService.send_managed(tenant_id=1, employee_id=7, payload=_request())

    @pytest.mark.asyncio
    async def test_call_id_resolved_when_present(self, monkeypatch):
        tracker = _SessionTracker()
        call_record = SimpleNamespace(id=1234)
        repos = _patch_common(
            monkeypatch, tracker, template_row=_template_row(), call_record=call_record
        )
        monkeypatch.setattr("app.services.sms_service.get_sms_client", lambda: _FakeClient())

        await SmsWorkspaceService.send_managed(
            tenant_id=1, employee_id=7, payload=_request(call_id="call-abc")
        )

        repos.call_lookup.assert_awaited_once()
        assert repos.call_lookup.await_args.args[1] == "call-abc"
        assert repos.create.await_args.args[1]["call_record_id"] == 1234


class TestDeliveryReceipts:
    @pytest.mark.asyncio
    async def test_receipts_update_records_and_skip_bad_items(self, monkeypatch):
        tracker = _SessionTracker()
        monkeypatch.setattr(
            "app.services.sms_service.AsyncSessionLocal", lambda: tracker.new_session()
        )

        class _ReceiptClient:
            def parse_delivery_receipt(self, item):
                if item.get("bad"):
                    raise ValueError("bad item")
                return SmsDeliveryReceipt(
                    biz_id=item["biz_id"],
                    success=item["success"],
                    error_code=item.get("err_code"),
                    error_message=item.get("err_msg"),
                )

        monkeypatch.setattr("app.services.sms_service.get_sms_client", lambda: _ReceiptClient())
        update = AsyncMock(side_effect=[1, 1])
        monkeypatch.setattr(
            "app.services.sms_service.SmsSendRecordRepository.update_delivery_by_biz_id", update
        )
        bulk_update = AsyncMock(side_effect=[[1], []])
        monkeypatch.setattr(
            "app.services.sms_service.SmsBulkTargetRepository.update_delivery_by_biz_id", bulk_update
        )
        complete = AsyncMock(return_value=True)
        monkeypatch.setattr(
            "app.services.sms_service.SmsBulkTaskRepository.complete_if_finished", complete
        )

        payload = [
            {"biz_id": "b1", "success": True},
            {"biz_id": "b2", "success": False, "err_code": "DELIVER_FAIL", "err_msg": "空号"},
            {"bad": True},
            {"biz_id": "", "success": True},
        ]
        processed = await SmsWorkspaceService.handle_delivery_receipts(
            provider="aliyun", payload=payload
        )

        assert processed == 2
        assert update.await_count == 2
        first, second = update.await_args_list
        assert first.kwargs["delivered"] is True
        assert second.kwargs["delivered"] is False
        assert second.kwargs["fail_reason"] == "DELIVER_FAIL: 空号"
        # Bulk linkage: each parsed receipt also advances matching targets.
        assert bulk_update.await_count == 2
        assert bulk_update.await_args_list[0].kwargs["biz_id"] == "b1"
        assert bulk_update.await_args_list[1].kwargs["fail_reason"] == "DELIVER_FAIL: 空号"
        complete.assert_awaited_once()  # only b1 reported an affected task

    @pytest.mark.asyncio
    async def test_receipts_from_other_environment_are_ignored(self, monkeypatch, caplog):
        # Mirrored callbacks deliver every receipt to every environment; a
        # receipt whose biz_id lives in another environment matches no row.
        tracker = _SessionTracker()
        monkeypatch.setattr(
            "app.services.sms_service.AsyncSessionLocal", lambda: tracker.new_session()
        )

        class _ReceiptClient:
            def parse_delivery_receipt(self, item):
                return SmsDeliveryReceipt(
                    biz_id=item["biz_id"],
                    success=item["success"],
                    error_code=item.get("err_code"),
                    error_message=item.get("err_msg"),
                )

        monkeypatch.setattr("app.services.sms_service.get_sms_client", lambda: _ReceiptClient())
        update = AsyncMock(return_value=0)
        monkeypatch.setattr(
            "app.services.sms_service.SmsSendRecordRepository.update_delivery_by_biz_id", update
        )
        bulk_update = AsyncMock(return_value=[])
        monkeypatch.setattr(
            "app.services.sms_service.SmsBulkTargetRepository.update_delivery_by_biz_id", bulk_update
        )
        complete = AsyncMock()
        monkeypatch.setattr(
            "app.services.sms_service.SmsBulkTaskRepository.complete_if_finished", complete
        )

        with caplog.at_level(logging.INFO, logger="app.services.sms_service"):
            processed = await SmsWorkspaceService.handle_delivery_receipts(
                provider="aliyun", payload=[{"biz_id": "other-env", "success": True}]
            )

        assert processed == 0
        assert update.await_count == 1
        assert bulk_update.await_count == 1
        complete.assert_not_awaited()
        assert "other-env" in caplog.text
