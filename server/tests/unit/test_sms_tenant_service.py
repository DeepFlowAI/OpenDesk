"""
Unit tests for tenant-side SMS template service (admin console views).
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NotFoundError
from app.services.sms_service import SmsTenantTemplateService


def _row(template_status="enabled", grant_updated=None, template_updated=None):
    grant = SimpleNamespace(
        template_id=10,
        updated_at=grant_updated or datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc),
    )
    template = SimpleNamespace(
        id=10,
        name="预约回访提醒",
        type="notify",
        status=template_status,
        body="尊敬的{name}。",
        variables=[{"key": "name", "label": "客户姓名", "required": True}],
        updated_at=template_updated or datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc),
    )
    signature = SimpleNamespace(name="深流客服")
    return grant, template, signature


class TestSmsTenantTemplateService:

    @pytest.mark.asyncio
    async def test_list_maps_status_and_effective_updated_at(self, monkeypatch):
        newer = datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)
        rows = [_row(template_updated=newer), _row(template_status="disabled")]
        monkeypatch.setattr(
            "app.services.sms_service.SmsTemplateGrantRepository.list_granted_detail_for_tenant_paginated",
            AsyncMock(return_value=(rows, 2)),
        )

        result = await SmsTenantTemplateService.list_for_tenant(
            AsyncMock(), tenant_id=1, page=1, per_page=20, q=None
        )

        assert result["total"] == 2
        assert result["items"][0]["status"] == "available"
        assert result["items"][0]["updated_at"] == newer  # max(grant, template)
        assert result["items"][1]["status"] == "unavailable"
        assert result["items"][0]["sign_name"] == "深流客服"

    @pytest.mark.asyncio
    async def test_get_for_tenant_returns_body(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_service.SmsTemplateGrantRepository.get_granted_template",
            AsyncMock(return_value=_row()),
        )
        result = await SmsTenantTemplateService.get_for_tenant(
            AsyncMock(), tenant_id=1, template_id=10
        )
        assert result["body"] == "尊敬的{name}。"
        assert result["status"] == "available"

    @pytest.mark.asyncio
    async def test_get_for_tenant_not_granted_raises_404(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_service.SmsTemplateGrantRepository.get_granted_template",
            AsyncMock(return_value=None),
        )
        with pytest.raises(NotFoundError):
            await SmsTenantTemplateService.get_for_tenant(AsyncMock(), tenant_id=1, template_id=999)
