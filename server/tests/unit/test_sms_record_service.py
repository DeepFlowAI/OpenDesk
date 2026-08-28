"""Unit tests for SmsSendRecordService (service-operations send records)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import NotFoundError
from app.services.sms_service import SmsSendRecordService

MODULE = "app.services.sms_service"

TENANT = 1
NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)
PUBLIC_ID = "d72f10d3-6bbb-40cf-9e40-d5767fccf07f"


def _record(**over):
    base = dict(
        id=10,
        phone="13800138000",
        template_name="工单通知",
        template_type="notification",
        sign_name="OpenDesk",
        status="delivered",
        body_snapshot="【OpenDesk】您好",
        variables_snapshot={"name": "张"},
        fail_reason=None,
        provider="mock",
        provider_biz_id="BIZ-1",
        source="single",
        bulk_task_id=None,
        call_record_id=5,
        created_at=NOW,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture
def db():
    return AsyncMock()


class TestListForTenant:
    @pytest.mark.asyncio
    async def test_maps_rows_with_employee_and_call(self, db):
        rows = [(_record(), "Alice", "call-abc", PUBLIC_ID)]
        with patch(
            f"{MODULE}.SmsSendRecordRepository.list_for_tenant_paginated",
            new=AsyncMock(return_value=(rows, 21)),
        ) as repo:
            result = await SmsSendRecordService.list_for_tenant(
                db, tenant_id=TENANT, page=2, per_page=20, q="138", status="delivered"
            )
        assert result["total"] == 21 and result["pages"] == 2 and result["page"] == 2
        item = result["items"][0]
        assert item["employee_name"] == "Alice"
        assert item["call_id"] == "call-abc" and item["call_record_id"] == 5
        assert item["call_record_public_id"] == PUBLIC_ID
        assert "body_snapshot" not in item
        assert repo.await_args.kwargs["phone"] == "138"
        assert repo.await_args.kwargs["status"] == "delivered"

    @pytest.mark.asyncio
    async def test_invalid_status_normalized_to_none(self, db):
        with patch(
            f"{MODULE}.SmsSendRecordRepository.list_for_tenant_paginated",
            new=AsyncMock(return_value=([], 0)),
        ) as repo:
            await SmsSendRecordService.list_for_tenant(db, tenant_id=TENANT, status="bogus")
        assert repo.await_args.kwargs["status"] is None

    @pytest.mark.asyncio
    async def test_source_filter_passed_through(self, db):
        rows = [(_record(source="bulk", bulk_task_id=7), "Alice", None, None)]
        with patch(
            f"{MODULE}.SmsSendRecordRepository.list_for_tenant_paginated",
            new=AsyncMock(return_value=(rows, 1)),
        ) as repo:
            result = await SmsSendRecordService.list_for_tenant(db, tenant_id=TENANT, source="bulk")
        assert repo.await_args.kwargs["source"] == "bulk"
        item = result["items"][0]
        assert item["source"] == "bulk"
        assert item["bulk_task_id"] == 7

    @pytest.mark.asyncio
    async def test_invalid_source_normalized_to_none(self, db):
        with patch(
            f"{MODULE}.SmsSendRecordRepository.list_for_tenant_paginated",
            new=AsyncMock(return_value=([], 0)),
        ) as repo:
            await SmsSendRecordService.list_for_tenant(db, tenant_id=TENANT, source="bogus")
        assert repo.await_args.kwargs["source"] is None


class TestGetForTenant:
    @pytest.mark.asyncio
    async def test_detail_includes_snapshot_fields(self, db):
        with patch(
            f"{MODULE}.SmsSendRecordRepository.get_detail_for_tenant",
            new=AsyncMock(
                return_value=(
                    _record(fail_reason="签名未报备"),
                    "Alice",
                    "call-abc",
                    PUBLIC_ID,
                )
            ),
        ):
            result = await SmsSendRecordService.get_for_tenant(db, tenant_id=TENANT, record_id=10)
        assert result["body_snapshot"] == "【OpenDesk】您好"
        assert result["fail_reason"] == "签名未报备"
        assert result["provider_biz_id"] == "BIZ-1"
        assert result["employee_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_not_found(self, db):
        with patch(
            f"{MODULE}.SmsSendRecordRepository.get_detail_for_tenant",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await SmsSendRecordService.get_for_tenant(db, tenant_id=TENANT, record_id=999)
