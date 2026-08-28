"""Unit tests for embedded call integration security and authentication."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.schemas.embedded_call import EmbedSessionRequest, EmbedSignatureRequest
from app.schemas.permission import EffectivePrincipal
from app.services.embedded_call_integration_service import (
    EmbeddedCallIntegrationService,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(
        self, key: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> bool:
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)


def integration(secret: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=41,
        tenant_id=7,
        integration_key="ec_test_public",
        is_enabled=True,
        allowed_origins=["https://crm.example.com"],
        secret_digest=EmbeddedCallIntegrationService._secret_digest(secret),
        previous_secret_digest=None,
        previous_secret_expires_at=None,
    )


def employee() -> SimpleNamespace:
    return SimpleNamespace(
        id=19,
        tenant_id=7,
        is_active=True,
        name="Ada",
        display_name="Ada Lovelace",
        default_language="en",
    )


def principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=19,
        tenant_id=7,
        permissions=["call.workspace.use", "call.embed.use"],
    )


class TestEmbeddedCallIntegrationService:
    def test_normalize_origin_with_exact_https_returns_canonical_origin(self) -> None:
        assert (
            EmbeddedCallIntegrationService.normalize_origin(" HTTPS://CRM.Example.com:443 ")
            == "https://crm.example.com:443"
        )

    def test_normalize_origin_strips_trailing_slash_from_copied_url(self) -> None:
        assert (
            EmbeddedCallIntegrationService.normalize_origin("https://www.zhihu.com/")
            == "https://www.zhihu.com"
        )
        assert (
            EmbeddedCallIntegrationService.normalize_origin("https://crm.example.com:8443///")
            == "https://crm.example.com:8443"
        )

    @pytest.mark.parametrize(
        "value",
        [
            "https://crm.example.com/path",
            "https://*.example.com",
            "null",
            "https://user:pass@crm.example.com",
            "http://crm.example.com",
        ],
    )
    def test_normalize_origin_with_unsafe_value_raises_validation_error(
        self, value: str
    ) -> None:
        with pytest.raises(ValidationError):
            EmbeddedCallIntegrationService.normalize_origin(value)

    @pytest.mark.asyncio
    async def test_delete_integration_removes_existing_row(self) -> None:
        row = integration("example-signing-credential")
        delete = AsyncMock()
        with (
            patch(
                "app.services.embedded_call_integration_service."
                "EmbeddedCallIntegrationRepository.get_by_public_id",
                AsyncMock(return_value=row),
            ),
            patch(
                "app.services.embedded_call_integration_service."
                "EmbeddedCallIntegrationRepository.delete",
                delete,
            ),
        ):
            await EmbeddedCallIntegrationService.delete_integration(
                AsyncMock(), tenant_id=7, public_id=uuid4()
            )
        delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_integration_not_found_raises(self) -> None:
        with patch(
            "app.services.embedded_call_integration_service."
            "EmbeddedCallIntegrationRepository.get_by_public_id",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await EmbeddedCallIntegrationService.delete_integration(
                    AsyncMock(), tenant_id=7, public_id=uuid4()
                )

    def test_previous_secret_matches_only_during_grace_period(self) -> None:
        previous = "ecs_previous"
        row = integration("ecs_current")
        row.previous_secret_digest = EmbeddedCallIntegrationService._secret_digest(previous)
        row.previous_secret_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        assert EmbeddedCallIntegrationService._secret_matches(row, previous) is True
        row.previous_secret_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert EmbeddedCallIntegrationService._secret_matches(row, previous) is False

    @pytest.mark.asyncio
    async def test_signature_request_with_unsafe_origin_records_stable_failure(self) -> None:
        row = integration("example-signing-credential")
        update = AsyncMock(return_value=row)
        with (
            patch(
                "app.services.embedded_call_integration_service."
                "EmbeddedCallIntegrationRepository.get_by_integration_key",
                AsyncMock(return_value=row),
            ),
            patch(
                "app.services.embedded_call_integration_service."
                "EmbeddedCallIntegrationRepository.update",
                update,
            ),
        ):
            with pytest.raises(BusinessError) as exc_info:
                await EmbeddedCallIntegrationService.issue_signature(
                    AsyncMock(),
                    FakeRedis(),
                    data=EmbedSignatureRequest(
                        integration_key=row.integration_key,
                        employee_identifier="ada",
                        origin="https://crm.example.com/path",
                        nonce="nonce_1234567890123456",
                    ),
                    server_secret="example-signing-credential",
                )

        assert exc_info.value.code == "EMBED_ORIGIN_NOT_ALLOWED"
        assert update.await_args.args[2]["last_error_code"] == "EMBED_ORIGIN_NOT_ALLOWED"

    @pytest.mark.asyncio
    async def test_signature_exchange_is_single_use_and_returns_session(self) -> None:
        db = AsyncMock()
        redis = FakeRedis()
        credential = "example-signing-credential"
        row = integration(credential)
        emp = employee()
        signature_request = EmbedSignatureRequest(
            integration_key=row.integration_key,
            employee_identifier="ada",
            origin="https://crm.example.com",
            nonce="nonce_1234567890123456",
        )

        with (
            patch(
                "app.services.embedded_call_integration_service."
                "EmbeddedCallIntegrationRepository.get_by_integration_key",
                AsyncMock(return_value=row),
            ),
            patch(
                "app.services.embedded_call_integration_service."
                "EmbeddedCallIntegrationRepository.get_by_id",
                AsyncMock(return_value=row),
            ),
            patch(
                "app.services.embedded_call_integration_service."
                "EmbeddedCallIntegrationRepository.update",
                AsyncMock(return_value=row),
            ),
            patch(
                "app.services.embedded_call_integration_service."
                "EmployeeRepository.get_by_username_or_email",
                AsyncMock(return_value=emp),
            ),
            patch(
                "app.services.embedded_call_integration_service.EmployeeRepository.get_by_id",
                AsyncMock(return_value=emp),
            ),
            patch(
                "app.services.embedded_call_integration_service."
                "PermissionService.get_current_principal",
                AsyncMock(return_value=principal()),
            ),
        ):
            issued = await EmbeddedCallIntegrationService.issue_signature(
                db, redis, data=signature_request, server_secret=credential
            )
            exchange_request = EmbedSessionRequest(
                embed_signature=issued.embed_signature,
                origin=signature_request.origin,
                nonce=signature_request.nonce,
                instance_id="instance_123456",
            )
            session = await EmbeddedCallIntegrationService.exchange_signature(
                db, redis, data=exchange_request
            )
            assert session.integration_key == row.integration_key
            assert session.agent.name == "Ada"
            assert session.access_token

            with pytest.raises(BusinessError) as replay:
                await EmbeddedCallIntegrationService.exchange_signature(
                    db, redis, data=exchange_request
                )
            assert replay.value.code == "EMBED_SIGNATURE_EXPIRED_OR_USED"
