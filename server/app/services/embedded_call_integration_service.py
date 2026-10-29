"""Embedded call integration configuration and short-lived authentication."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import ENV, settings
from app.core.exceptions import BusinessError, NotFoundError, UnauthorizedError, ValidationError
from app.core.security import create_access_token
from app.models.embedded_call_integration import EmbeddedCallIntegration
from app.repositories.embedded_call_integration_repository import (
    EmbeddedCallIntegrationRepository,
)
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.embedded_call import (
    EmbedSessionRequest,
    EmbedSessionResponse,
    EmbedSignatureRequest,
    EmbedSignatureResponse,
    EmbeddedAgentBrief,
    EmbeddedCallIntegrationCreate,
    EmbeddedCallIntegrationListResponse,
    EmbeddedCallIntegrationResponse,
    EmbeddedCallIntegrationSecretResponse,
    EmbeddedCallIntegrationUpdate,
)
from app.services.permission_service import PermissionService


SIGNATURE_TTL_SECONDS = 60
SESSION_TTL_SECONDS = 300
MANAGE_PERMISSION = "call.admin.embed.manage"
USE_PERMISSION = "call.embed.use"

# Atomic one-time read for embed signatures. GETDEL needs Redis >= 6.2;
# this script works on any version and keeps a signature single-use.
_GET_AND_DELETE = """
local value = redis.call('GET', KEYS[1])
if value then redis.call('DEL', KEYS[1]) end
return value
"""


def _embed_error(code: str, message: str, status_code: int = 400) -> BusinessError:
    return BusinessError(message, status_code=status_code, code=code)


class EmbeddedCallIntegrationService:
    @staticmethod
    async def _record_failure(
        db: AsyncSession,
        row: EmbeddedCallIntegration,
        *,
        code: str,
    ) -> None:
        await EmbeddedCallIntegrationRepository.update(
            db,
            row,
            {
                "last_failure_at": datetime.now(timezone.utc),
                "last_error_code": code,
            },
        )

    @staticmethod
    def normalize_origin(value: str) -> str:
        """Return a strict scheme/host/port origin or reject unsafe input."""
        raw = value.strip().rstrip("/")
        if not raw or raw.lower() == "null" or "*" in raw:
            raise ValidationError("Origin must be an exact HTTPS origin")
        parsed = urlsplit(raw)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValidationError("Origin must use scheme://host[:port] without a path")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValidationError("Origin contains an invalid port") from exc

        scheme = parsed.scheme.lower()
        host = parsed.hostname.lower()
        local_host = host in {"localhost", "127.0.0.1", "::1"} or host.endswith(
            ".localhost"
        )
        if scheme != "https" and not (ENV != "production" and local_host):
            raise ValidationError("Production origins must use HTTPS")
        rendered_host = f"[{host}]" if ":" in host else host
        return f"{scheme}://{rendered_host}{f':{port}' if port is not None else ''}"

    @staticmethod
    def normalize_origins(values: list[str]) -> list[str]:
        normalized = list(
            dict.fromkeys(EmbeddedCallIntegrationService.normalize_origin(item) for item in values)
        )
        if not normalized:
            raise ValidationError("At least one allowed origin is required")
        if len(normalized) > 20:
            raise ValidationError("At most 20 allowed origins are supported")
        return normalized

    @staticmethod
    def _secret_digest(secret: str) -> str:
        return hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            secret.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _new_secret() -> str:
        return f"ecs_{secrets.token_urlsafe(36)}"

    @staticmethod
    def _new_integration_key() -> str:
        environment = "live" if ENV == "production" else "test"
        return f"ec_{environment}_{secrets.token_urlsafe(18).replace('-', '').replace('_', '')}"

    @staticmethod
    def _response(row: EmbeddedCallIntegration) -> EmbeddedCallIntegrationResponse:
        return EmbeddedCallIntegrationResponse.model_validate(row)

    @staticmethod
    async def list_integrations(
        db: AsyncSession, tenant_id: int
    ) -> EmbeddedCallIntegrationListResponse:
        rows = await EmbeddedCallIntegrationRepository.list_for_tenant(db, tenant_id)
        return EmbeddedCallIntegrationListResponse(
            items=[EmbeddedCallIntegrationService._response(row) for row in rows],
            total=len(rows),
        )

    @staticmethod
    async def get_integration(
        db: AsyncSession, tenant_id: int, public_id: UUID
    ) -> EmbeddedCallIntegrationResponse:
        row = await EmbeddedCallIntegrationRepository.get_by_public_id(
            db, tenant_id, public_id
        )
        if row is None:
            raise NotFoundError("Embedded call integration not found")
        return EmbeddedCallIntegrationService._response(row)

    @staticmethod
    async def create_integration(
        db: AsyncSession,
        *,
        tenant_id: int,
        actor_id: int,
        data: EmbeddedCallIntegrationCreate,
    ) -> EmbeddedCallIntegrationSecretResponse:
        secret = EmbeddedCallIntegrationService._new_secret()
        now = datetime.now(timezone.utc)
        row = await EmbeddedCallIntegrationRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "name": data.name.strip(),
                "integration_key": EmbeddedCallIntegrationService._new_integration_key(),
                "allowed_origins": EmbeddedCallIntegrationService.normalize_origins(
                    data.allowed_origins
                ),
                "is_enabled": data.is_enabled,
                "secret_digest": EmbeddedCallIntegrationService._secret_digest(secret),
                "secret_last_four": secret[-4:],
                "secret_rotated_at": now,
                "created_by_id": actor_id,
                "updated_by_id": actor_id,
            },
        )
        return EmbeddedCallIntegrationSecretResponse(
            integration=EmbeddedCallIntegrationService._response(row),
            server_secret=secret,
        )

    @staticmethod
    async def update_integration(
        db: AsyncSession,
        *,
        tenant_id: int,
        actor_id: int,
        public_id: UUID,
        data: EmbeddedCallIntegrationUpdate,
    ) -> EmbeddedCallIntegrationResponse:
        row = await EmbeddedCallIntegrationRepository.get_by_public_id(
            db, tenant_id, public_id
        )
        if row is None:
            raise NotFoundError("Embedded call integration not found")
        patch = data.model_dump(exclude_unset=True)
        if "name" in patch:
            patch["name"] = patch["name"].strip()
        if "allowed_origins" in patch:
            patch["allowed_origins"] = EmbeddedCallIntegrationService.normalize_origins(
                patch["allowed_origins"]
            )
        if patch.get("is_enabled") and not patch.get(
            "allowed_origins", row.allowed_origins
        ):
            raise ValidationError("An enabled integration needs an allowed origin")
        patch["updated_by_id"] = actor_id
        updated = await EmbeddedCallIntegrationRepository.update(db, row, patch)
        return EmbeddedCallIntegrationService._response(updated)

    @staticmethod
    async def delete_integration(
        db: AsyncSession, *, tenant_id: int, public_id: UUID
    ) -> None:
        row = await EmbeddedCallIntegrationRepository.get_by_public_id(
            db, tenant_id, public_id
        )
        if row is None:
            raise NotFoundError("Embedded call integration not found")
        await EmbeddedCallIntegrationRepository.delete(db, row)

    @staticmethod
    async def rotate_secret(
        db: AsyncSession,
        *,
        tenant_id: int,
        actor_id: int,
        public_id: UUID,
        grace_period_hours: int,
    ) -> EmbeddedCallIntegrationSecretResponse:
        row = await EmbeddedCallIntegrationRepository.get_by_public_id(
            db, tenant_id, public_id
        )
        if row is None:
            raise NotFoundError("Embedded call integration not found")
        now = datetime.now(timezone.utc)
        secret = EmbeddedCallIntegrationService._new_secret()
        updated = await EmbeddedCallIntegrationRepository.update(
            db,
            row,
            {
                "previous_secret_digest": row.secret_digest
                if grace_period_hours > 0
                else None,
                "previous_secret_last_four": row.secret_last_four
                if grace_period_hours > 0
                else None,
                "previous_secret_expires_at": now + timedelta(hours=grace_period_hours)
                if grace_period_hours > 0
                else None,
                "secret_digest": EmbeddedCallIntegrationService._secret_digest(secret),
                "secret_last_four": secret[-4:],
                "secret_rotated_at": now,
                "updated_by_id": actor_id,
            },
        )
        return EmbeddedCallIntegrationSecretResponse(
            integration=EmbeddedCallIntegrationService._response(updated),
            server_secret=secret,
        )

    @staticmethod
    async def revoke_previous_secret(
        db: AsyncSession, *, tenant_id: int, actor_id: int, public_id: UUID
    ) -> EmbeddedCallIntegrationResponse:
        row = await EmbeddedCallIntegrationRepository.get_by_public_id(
            db, tenant_id, public_id
        )
        if row is None:
            raise NotFoundError("Embedded call integration not found")
        updated = await EmbeddedCallIntegrationRepository.update(
            db,
            row,
            {
                "previous_secret_digest": None,
                "previous_secret_last_four": None,
                "previous_secret_expires_at": None,
                "updated_by_id": actor_id,
            },
        )
        return EmbeddedCallIntegrationService._response(updated)

    @staticmethod
    def _secret_matches(row: EmbeddedCallIntegration, candidate: str) -> bool:
        digest = EmbeddedCallIntegrationService._secret_digest(candidate)
        if hmac.compare_digest(digest, row.secret_digest):
            return True
        return bool(
            row.previous_secret_digest
            and row.previous_secret_expires_at
            and row.previous_secret_expires_at > datetime.now(timezone.utc)
            and hmac.compare_digest(digest, row.previous_secret_digest)
        )

    @staticmethod
    def _signature_key(signature: str) -> str:
        digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        return f"embedded-call:signature:{digest}"

    @staticmethod
    def _session_key(session_id: str) -> str:
        return f"embedded-call:session:{session_id}"

    @staticmethod
    async def issue_signature(
        db: AsyncSession,
        redis: aioredis.Redis,
        *,
        data: EmbedSignatureRequest,
        server_secret: str,
    ) -> EmbedSignatureResponse:
        row = await EmbeddedCallIntegrationRepository.get_by_integration_key(
            db, data.integration_key
        )
        if row is None:
            raise _embed_error(
                "EMBED_INTEGRATION_NOT_FOUND", "Embedded call integration not found", 404
            )
        if not row.is_enabled:
            await EmbeddedCallIntegrationService._record_failure(
                db, row, code="EMBED_INTEGRATION_DISABLED"
            )
            raise _embed_error(
                "EMBED_INTEGRATION_DISABLED", "Embedded call integration is disabled", 403
            )
        try:
            origin = EmbeddedCallIntegrationService.normalize_origin(data.origin)
        except ValidationError as exc:
            await EmbeddedCallIntegrationService._record_failure(
                db, row, code="EMBED_ORIGIN_NOT_ALLOWED"
            )
            raise _embed_error(
                "EMBED_ORIGIN_NOT_ALLOWED", "Origin is not allowed", 403
            ) from exc
        if origin not in row.allowed_origins:
            await EmbeddedCallIntegrationService._record_failure(
                db, row, code="EMBED_ORIGIN_NOT_ALLOWED"
            )
            raise _embed_error(
                "EMBED_ORIGIN_NOT_ALLOWED", "Origin is not allowed", 403
            )
        if not EmbeddedCallIntegrationService._secret_matches(row, server_secret):
            await EmbeddedCallIntegrationService._record_failure(
                db, row, code="EMBED_SECRET_INVALID"
            )
            raise _embed_error("EMBED_SECRET_INVALID", "Invalid integration secret", 401)

        employee = await EmployeeRepository.get_by_username_or_email(
            db, row.tenant_id, data.employee_identifier
        )
        if employee is None or not employee.is_active:
            await EmbeddedCallIntegrationService._record_failure(
                db, row, code="EMBED_AGENT_NOT_FOUND"
            )
            raise _embed_error("EMBED_AGENT_NOT_FOUND", "Embedded call agent not found", 404)
        principal = await PermissionService.get_current_principal(
            db, {"user_id": employee.id, "tenant_id": row.tenant_id}
        )
        if not principal.has_permission(USE_PERMISSION):
            await EmbeddedCallIntegrationService._record_failure(
                db, row, code="EMBED_PERMISSION_DENIED"
            )
            raise _embed_error(
                "EMBED_PERMISSION_DENIED", "Agent cannot use embedded calling", 403
            )

        signature = f"ecsig_{secrets.token_urlsafe(40)}"
        claims = {
            "tenant_id": row.tenant_id,
            "integration_id": row.id,
            "integration_key": row.integration_key,
            "employee_id": employee.id,
            "origin": origin,
            "nonce": data.nonce,
        }
        stored = await redis.set(
            EmbeddedCallIntegrationService._signature_key(signature),
            json.dumps(claims, separators=(",", ":")),
            ex=SIGNATURE_TTL_SECONDS,
            nx=True,
        )
        if not stored:
            raise _embed_error("EMBED_SIGNATURE_INVALID", "Unable to issue signature", 503)
        await EmbeddedCallIntegrationRepository.update(
            db,
            row,
            {"last_used_at": datetime.now(timezone.utc), "last_error_code": None},
        )
        return EmbedSignatureResponse(
            embed_signature=signature, expires_in=SIGNATURE_TTL_SECONDS
        )

    @staticmethod
    def _decode_redis_json(value: str | bytes | None) -> dict | None:
        if value is None:
            return None
        raw = value.decode("utf-8") if isinstance(value, bytes) else value
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    async def exchange_signature(
        db: AsyncSession,
        redis: aioredis.Redis,
        *,
        data: EmbedSessionRequest,
    ) -> EmbedSessionResponse:
        raw_claims = await redis.eval(
            _GET_AND_DELETE,
            1,
            EmbeddedCallIntegrationService._signature_key(data.embed_signature),
        )
        claims = EmbeddedCallIntegrationService._decode_redis_json(raw_claims)
        if claims is None:
            raise _embed_error(
                "EMBED_SIGNATURE_EXPIRED_OR_USED",
                "Embed signature is expired or already used",
                401,
            )
        tenant_id = int(claims["tenant_id"])
        employee_id = int(claims["employee_id"])
        integration_id = int(claims["integration_id"])
        row = await EmbeddedCallIntegrationRepository.get_by_id(
            db, integration_id, tenant_id
        )
        try:
            origin = EmbeddedCallIntegrationService.normalize_origin(data.origin)
        except ValidationError as exc:
            if row is not None:
                await EmbeddedCallIntegrationService._record_failure(
                    db, row, code="EMBED_SIGNATURE_INVALID"
                )
            raise _embed_error(
                "EMBED_SIGNATURE_INVALID", "Embed signature does not match", 401
            ) from exc
        if claims.get("origin") != origin or claims.get("nonce") != data.nonce:
            if row is not None:
                await EmbeddedCallIntegrationService._record_failure(
                    db, row, code="EMBED_SIGNATURE_INVALID"
                )
            raise _embed_error("EMBED_SIGNATURE_INVALID", "Embed signature does not match", 401)

        if row is None or not row.is_enabled or origin not in row.allowed_origins:
            if row is not None:
                await EmbeddedCallIntegrationService._record_failure(
                    db, row, code="EMBED_INTEGRATION_DISABLED"
                )
            raise _embed_error(
                "EMBED_INTEGRATION_DISABLED", "Embedded call integration is unavailable", 403
            )
        employee = await EmployeeRepository.get_by_id(db, employee_id)
        if employee is None or employee.tenant_id != tenant_id or not employee.is_active:
            await EmbeddedCallIntegrationService._record_failure(
                db, row, code="EMBED_AGENT_NOT_FOUND"
            )
            raise _embed_error("EMBED_AGENT_NOT_FOUND", "Embedded call agent not found", 404)
        principal = await PermissionService.get_current_principal(
            db, {"user_id": employee_id, "tenant_id": tenant_id}
        )
        if not principal.has_permission(USE_PERMISSION):
            await EmbeddedCallIntegrationService._record_failure(
                db, row, code="EMBED_PERMISSION_DENIED"
            )
            raise _embed_error(
                "EMBED_PERMISSION_DENIED", "Agent cannot use embedded calling", 403
            )

        session_id = f"emb_{secrets.token_urlsafe(24)}"
        session_claims = {
            "typ": "embedded_call_session",
            "sub": str(employee_id),
            "user_id": employee_id,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "integration_id": integration_id,
            "integration_key": row.integration_key,
            "origin": origin,
            "instance_id": data.instance_id,
        }
        await redis.set(
            EmbeddedCallIntegrationService._session_key(session_id),
            json.dumps(session_claims, separators=(",", ":")),
            ex=SESSION_TTL_SECONDS,
        )
        await EmbeddedCallIntegrationRepository.update(
            db,
            row,
            {
                "last_success_at": datetime.now(timezone.utc),
                "last_error_code": None,
            },
        )
        token = create_access_token(
            session_claims, expires_delta=timedelta(seconds=SESSION_TTL_SECONDS)
        )
        return EmbedSessionResponse(
            access_token=token,
            expires_in=SESSION_TTL_SECONDS,
            integration_key=row.integration_key,
            agent=EmbeddedAgentBrief(
                name=employee.name,
                display_name=employee.display_name,
                default_language=employee.default_language,
                permissions=principal.permissions,
            ),
        )

    @staticmethod
    async def validate_session_payload(
        db: AsyncSession, redis: aioredis.Redis, payload: dict
    ) -> None:
        """Validate that an embedded session is still present and unaltered."""
        if payload.get("typ") != "embedded_call_session":
            raise UnauthorizedError("Invalid embedded call session")
        session_id = str(payload.get("session_id") or "")
        if not session_id:
            raise UnauthorizedError("Invalid embedded call session")
        stored = EmbeddedCallIntegrationService._decode_redis_json(
            await redis.get(EmbeddedCallIntegrationService._session_key(session_id))
        )
        compared_fields = (
            "user_id",
            "tenant_id",
            "integration_id",
            "integration_key",
            "origin",
            "instance_id",
        )
        if stored is None or any(str(stored.get(key)) != str(payload.get(key)) for key in compared_fields):
            raise UnauthorizedError("Invalid or expired embedded call session")
        principal = await PermissionService.get_current_principal(db, payload)
        if not principal.has_permission(USE_PERMISSION):
            raise UnauthorizedError("Embedded call permission was revoked")
