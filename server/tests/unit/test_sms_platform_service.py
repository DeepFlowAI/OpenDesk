"""
Unit tests for the platform SMS service (signatures, templates, grants).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.sms import (
    SmsSignatureCreate,
    SmsSignatureUpdate,
    SmsTemplateCreate,
    SmsTemplateUpdate,
)
from app.services.sms_platform_service import (
    SmsSignatureService,
    SmsTemplateGrantService,
    SmsTemplateService,
)


def _signature(**overrides):
    data = {
        "id": 1,
        "name": "客服签名",
        "provider": "aliyun",
        "provider_sign_name": "深流客服",
        "status": "enabled",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _template(**overrides):
    data = {
        "id": 10,
        "name": "预约回访提醒",
        "type": "notify",
        "signature_id": 1,
        "body": "尊敬的{name}，您预约的回访时间为{time}。",
        "variables": [
            {"key": "name", "label": "客户姓名", "required": True},
            {"key": "time", "label": "预约时间", "required": True},
        ],
        "provider": "aliyun",
        "provider_template_code": "SMS_1000001",
        "status": "enabled",
        "created_at": None,
        "updated_at": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


class TestSmsSignatureService:

    @pytest.mark.asyncio
    async def test_create_enabled_conflict_raises_409(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_enabled_by_provider_sign",
            AsyncMock(return_value=_signature(id=99)),
        )
        with pytest.raises(ConflictError):
            await SmsSignatureService.create(
                AsyncMock(),
                SmsSignatureCreate(name="新签名", provider="aliyun", provider_sign_name="深流客服"),
            )

    @pytest.mark.asyncio
    async def test_create_disabled_skips_conflict_check(self, monkeypatch):
        conflict_probe = AsyncMock(return_value=None)
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_enabled_by_provider_sign",
            conflict_probe,
        )
        created = _signature(id=2, status="disabled")
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.create",
            AsyncMock(return_value=created),
        )
        result = await SmsSignatureService.create(
            AsyncMock(),
            SmsSignatureCreate(
                name="新签名", provider="aliyun", provider_sign_name="深流客服", status="disabled"
            ),
        )
        assert result.id == 2
        conflict_probe.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_enable_with_conflict_raises_409(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_by_id",
            AsyncMock(return_value=_signature(id=1, status="disabled")),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_enabled_by_provider_sign",
            AsyncMock(return_value=_signature(id=99)),
        )
        with pytest.raises(ConflictError):
            await SmsSignatureService.update(
                AsyncMock(), 1, SmsSignatureUpdate(status="enabled")
            )

    @pytest.mark.asyncio
    async def test_update_not_found_raises_404(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_by_id",
            AsyncMock(return_value=None),
        )
        with pytest.raises(NotFoundError):
            await SmsSignatureService.update(AsyncMock(), 999, SmsSignatureUpdate(name="x"))

    @pytest.mark.asyncio
    async def test_create_invalid_status_raises_400(self):
        with pytest.raises(ValidationError):
            await SmsSignatureService.create(
                AsyncMock(),
                SmsSignatureCreate(
                    name="x", provider="aliyun", provider_sign_name="y", status="paused"
                ),
            )


class TestSmsTemplateService:

    @pytest.mark.asyncio
    async def test_create_signature_missing_raises_404(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_by_id",
            AsyncMock(return_value=None),
        )
        with pytest.raises(NotFoundError):
            await SmsTemplateService.create(
                AsyncMock(),
                SmsTemplateCreate(
                    name="t",
                    signature_id=404,
                    body="您好 {name}",
                    variables=[],
                    provider="aliyun",
                    provider_template_code="SMS_1",
                ),
            )

    @pytest.mark.asyncio
    async def test_create_enabled_with_disabled_signature_raises_400(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_by_id",
            AsyncMock(return_value=_signature(status="disabled")),
        )
        with pytest.raises(ValidationError):
            await SmsTemplateService.create(
                AsyncMock(),
                SmsTemplateCreate(
                    name="t",
                    signature_id=1,
                    body="您好 {name}",
                    variables=[],
                    provider="aliyun",
                    provider_template_code="SMS_1",
                    status="enabled",
                ),
            )

    @pytest.mark.asyncio
    async def test_create_duplicate_provider_code_raises_409(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_by_id",
            AsyncMock(return_value=_signature()),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateRepository.get_by_provider_code",
            AsyncMock(return_value=_template(id=99)),
        )
        with pytest.raises(ConflictError):
            await SmsTemplateService.create(
                AsyncMock(),
                SmsTemplateCreate(
                    name="t",
                    signature_id=1,
                    body="您好 {name}",
                    variables=[],
                    provider="aliyun",
                    provider_template_code="SMS_1000001",
                ),
            )

    @pytest.mark.asyncio
    async def test_create_duplicate_variable_keys_raises_400(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_by_id",
            AsyncMock(return_value=_signature()),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateRepository.get_by_provider_code",
            AsyncMock(return_value=None),
        )
        with pytest.raises(ValidationError):
            await SmsTemplateService.create(
                AsyncMock(),
                SmsTemplateCreate(
                    name="t",
                    signature_id=1,
                    body="您好 {name}",
                    variables=[
                        {"key": "name", "label": "姓名", "required": True},
                        {"key": "name", "label": "姓名2", "required": False},
                    ],
                    provider="aliyun",
                    provider_template_code="SMS_2",
                ),
            )

    @pytest.mark.asyncio
    async def test_create_disabled_without_channel_binding_succeeds(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_by_id",
            AsyncMock(return_value=_signature(status="disabled")),
        )
        created = _template(id=11, status="disabled")
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateRepository.get_by_provider_code",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateRepository.create",
            AsyncMock(return_value=created),
        )
        result = await SmsTemplateService.create(
            AsyncMock(),
            SmsTemplateCreate(
                name="t",
                signature_id=1,
                body="您好 {name}",
                variables=[],
                provider="aliyun",
                provider_template_code="SMS_3",
                status="disabled",
            ),
        )
        assert result["status"] == "disabled"
        assert result["signature_name"] == "客服签名"

    @pytest.mark.asyncio
    async def test_update_enable_without_ready_binding_raises_400(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateRepository.get_by_id",
            AsyncMock(return_value=_template(status="disabled")),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_by_id",
            AsyncMock(return_value=_signature(status="disabled")),
        )
        with pytest.raises(ValidationError):
            await SmsTemplateService.update(AsyncMock(), 10, SmsTemplateUpdate(status="enabled"))


class TestSmsTemplateGrantService:

    @pytest.mark.asyncio
    async def test_grant_tenant_missing_raises_404(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.TenantRepository.get_by_tenant_id",
            AsyncMock(return_value=None),
        )
        with pytest.raises(NotFoundError):
            await SmsTemplateGrantService.grant(AsyncMock(), tenant_id="missing", template_ids=[10])

    @pytest.mark.asyncio
    async def test_grant_skips_disabled_and_existing(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.TenantRepository.get_by_tenant_id",
            AsyncMock(return_value=SimpleNamespace(id=1)),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateRepository.get_by_ids",
            AsyncMock(
                return_value=[
                    _template(id=10, status="enabled"),
                    _template(id=11, status="disabled"),
                ]
            ),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateGrantRepository.list_template_ids_for_tenant",
            AsyncMock(return_value=[12]),
        )
        create_mock = AsyncMock()
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateGrantRepository.create", create_mock
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateGrantRepository.commit", AsyncMock()
        )

        result = await SmsTemplateGrantService.grant(
            AsyncMock(), tenant_id="td_1", template_ids=[10, 11, 12, 13]
        )

        # 10 enabled -> granted; 11 disabled -> skipped; 12 already granted -> skipped;
        # 13 not found -> skipped.
        assert result["granted"] == [10]
        assert sorted(result["skipped"]) == [11, 12, 13]
        create_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_revoke_only_existing(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.TenantRepository.get_by_tenant_id",
            AsyncMock(return_value=SimpleNamespace(id=1)),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateGrantRepository.delete",
            AsyncMock(side_effect=[True, False]),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateGrantRepository.commit", AsyncMock()
        )

        result = await SmsTemplateGrantService.revoke(AsyncMock(), tenant_id="td_1", template_ids=[10, 11])
        assert result["revoked"] == [10]

    @pytest.mark.asyncio
    async def test_list_granted_templates_computes_availability(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.sms_platform_service.TenantRepository.get_by_tenant_id",
            AsyncMock(return_value=SimpleNamespace(id=1)),
        )
        grants = [
            SimpleNamespace(template_id=10, created_at=None, updated_at=None),
            SimpleNamespace(template_id=11, created_at=None, updated_at=None),
        ]
        # max(grant.updated_at, template.updated_at) requires comparable values
        from datetime import datetime, timezone

        now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
        for grant in grants:
            grant.created_at = now
            grant.updated_at = now
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateGrantRepository.list_grants_for_tenant",
            AsyncMock(return_value=grants),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsTemplateRepository.get_by_ids",
            AsyncMock(
                return_value=[
                    _template(id=10, status="enabled", updated_at=now, created_at=now),
                    _template(id=11, status="disabled", updated_at=now, created_at=now),
                ]
            ),
        )
        monkeypatch.setattr(
            "app.services.sms_platform_service.SmsSignatureRepository.get_by_id",
            AsyncMock(return_value=_signature()),
        )

        result = await SmsTemplateGrantService.list_granted_templates(AsyncMock(), tenant_id="td_1")

        assert [item["availability"] for item in result["items"]] == [
            "available",
            "template_disabled",
        ]
        assert result["items"][0]["sign_name"] == "客服签名"
