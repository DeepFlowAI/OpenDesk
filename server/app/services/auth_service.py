"""
Auth service
"""
import logging
import math
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt

from app.configs.settings import settings
from app.core.exceptions import UnauthorizedError, NotFoundError
from app.core.security import verify_password, create_access_token
from app.repositories.tenant_repository import TenantRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.auth import LoginRequest, LoginResponse, SsoLoginRequest, UserInfo, UserPreferencesUpdate
from app.services.employee_session_service import EmployeeSessionService
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)

# Fallback TTL when the SSO JWT has no usable exp (matches issuer TOKEN_EXPIRE_SECONDS).
_SSO_JTI_CLAIM_FALLBACK_TTL_SECONDS = 120


class AuthService:
    @staticmethod
    def _sso_secret() -> str:
        return settings.TENANT_PLATFORM_SSO_SECRET or settings.TENANT_API_KEY

    @staticmethod
    def _sso_audiences() -> set[str]:
        return {
            item.strip()
            for item in settings.TENANT_PLATFORM_SSO_AUDIENCES.split(",")
            if item.strip()
        }

    @staticmethod
    def _decode_sso_token(token: str) -> dict:
        secret = AuthService._sso_secret()
        if not secret:
            raise UnauthorizedError("SSO is not configured")
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except JWTError:
            raise UnauthorizedError("Invalid or expired SSO token")
        if payload.get("iss") != "tenant-platform" or payload.get("typ") != "tenant_sso":
            raise UnauthorizedError("Invalid SSO token")
        if payload.get("aud") not in AuthService._sso_audiences():
            raise UnauthorizedError("Invalid SSO audience")
        return payload

    @staticmethod
    def _sso_jti_claim_ttl_seconds(payload: dict) -> int:
        exp = payload.get("exp")
        if exp is None:
            return _SSO_JTI_CLAIM_FALLBACK_TTL_SECONDS
        try:
            remaining = float(exp) - datetime.now(timezone.utc).timestamp()
            return max(1, math.ceil(remaining))
        except (TypeError, ValueError, OverflowError):
            return _SSO_JTI_CLAIM_FALLBACK_TTL_SECONDS

    @staticmethod
    async def _claim_sso_jti(payload: dict) -> None:
        """Atomically consume an SSO token jti so the URL bearer cannot be replayed."""
        jti = payload.get("jti")
        if not jti:
            return
        if not settings.REDIS_URL:
            return
        key = f"sso:jti:{jti}"
        ttl = AuthService._sso_jti_claim_ttl_seconds(payload)
        try:
            from app.db.redis import redis_client

            r = redis_client.client
            claimed = await r.set(key, "1", ex=ttl, nx=True)
            if not claimed:
                raise UnauthorizedError("SSO token already used")
        except UnauthorizedError:
            raise
        except RuntimeError:
            logger.debug(
                "Skipped SSO jti claim; Redis is not initialized",
                exc_info=True,
            )
        except Exception:
            logger.exception("Failed to claim SSO jti key=%s", key)

    @staticmethod
    def _merge_preferences(current: dict, patch: dict) -> dict:
        merged = {**current}
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = AuthService._merge_preferences(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _build_user_info(user, principal) -> UserInfo:
        user_info = UserInfo.model_validate(user)
        user_info.role_ids = principal.role_ids
        user_info.permissions = principal.permissions
        user_info.data_scopes = principal.data_scopes
        user_info.is_super_admin = principal.is_super_admin
        user_info.group_ids = principal.group_ids
        return user_info

    @staticmethod
    def _short_session_id(session_id: str | None) -> str:
        if not session_id:
            return "-"
        return session_id[:8]

    @staticmethod
    def _log_login_success(
        *,
        method: str,
        user,
        tenant_id: int,
        session_id: str,
        replaced_previous: bool,
        client_ip: str | None,
        user_agent: str | None,
    ) -> None:
        ip = client_ip or "-"
        ua = user_agent or "-"
        session_prefix = AuthService._short_session_id(session_id)
        username = getattr(user, "username", None) or "-"
        extra = {
            "auth_method": method,
            "user_id": str(user.id),
            "tenant_id": str(tenant_id),
            "username": str(username),
            "session_id": session_prefix,
            "replaced_previous": str(replaced_previous).lower(),
            "client_ip": ip,
            "user_agent": ua,
        }
        logger.info(
            "Login success: method=%s user_id=%s tenant_id=%s username=%s "
            "session_id=%s replaced_previous=%s client_ip=%s user_agent=%s",
            method,
            user.id,
            tenant_id,
            username,
            session_prefix,
            replaced_previous,
            ip,
            ua,
            extra=extra,
        )

    @staticmethod
    async def login(
        db: AsyncSession,
        data: LoginRequest,
        *,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> LoginResponse:
        """Authenticate user and return JWT token."""
        tenant = await TenantRepository.resolve_by_identifier(db, data.tenant)
        if not tenant or not tenant.is_active:
            raise NotFoundError("Tenant not found")

        user = await EmployeeRepository.get_by_username_or_email(db, tenant.id, data.username)
        if not user:
            raise UnauthorizedError("Invalid credentials")

        if not verify_password(data.password, user.password_hash):
            raise UnauthorizedError("Invalid credentials")

        if not user.is_active:
            raise UnauthorizedError("Account is disabled")

        replaced_previous = bool(user.current_session_id)
        await EmployeeSessionService.disconnect_current_socket(tenant.id, user.id)
        session_id = EmployeeSessionService.generate_session_id()
        user = await EmployeeRepository.update_login_session(db, user, session_id)

        token_data = {
            "sub": str(user.id),
            "tenant_id": tenant.id,
            "roles": user.roles,
            "session_id": session_id,
        }
        access_token = create_access_token(token_data)
        principal = await PermissionService.get_current_principal(
            db,
            {"user_id": user.id, "tenant_id": tenant.id},
        )
        user_info = AuthService._build_user_info(user, principal)
        AuthService._log_login_success(
            method="password",
            user=user,
            tenant_id=tenant.id,
            session_id=session_id,
            replaced_previous=replaced_previous,
            client_ip=client_ip,
            user_agent=user_agent,
        )

        return LoginResponse(
            access_token=access_token,
            user=user_info,
        )

    @staticmethod
    async def sso_login(
        db: AsyncSession,
        data: SsoLoginRequest,
        *,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> LoginResponse:
        """Exchange a Tenant Platform SSO token for a normal OpenDesk JWT."""
        payload = AuthService._decode_sso_token(data.token)
        # SSO tokens travel in the browser URL; claim jti once so they cannot be replayed.
        await AuthService._claim_sso_jti(payload)
        tenant_identifier = str(payload.get("tenant_id") or payload.get("sub") or "")
        tenant = await TenantRepository.resolve_by_identifier(db, tenant_identifier)
        if not tenant or not tenant.is_active:
            raise UnauthorizedError("Invalid or disabled tenant")

        user = await EmployeeRepository.get_sso_admin(db, tenant.id)
        if not user:
            raise UnauthorizedError("No enabled tenant admin account")

        replaced_previous = bool(user.current_session_id)
        await EmployeeSessionService.disconnect_current_socket(tenant.id, user.id)
        session_id = EmployeeSessionService.generate_session_id()
        user = await EmployeeRepository.update_login_session(db, user, session_id)
        token_data = {
            "sub": str(user.id),
            "tenant_id": tenant.id,
            "roles": user.roles,
            "session_id": session_id,
        }
        access_token = create_access_token(token_data)
        principal = await PermissionService.get_current_principal(
            db,
            {"user_id": user.id, "tenant_id": tenant.id},
        )
        user_info = AuthService._build_user_info(user, principal)
        AuthService._log_login_success(
            method="sso",
            user=user,
            tenant_id=tenant.id,
            session_id=session_id,
            replaced_previous=replaced_previous,
            client_ip=client_ip,
            user_agent=user_agent,
        )
        return LoginResponse(access_token=access_token, user=user_info)

    @staticmethod
    async def refresh_token(db: AsyncSession, user_payload: dict) -> str:
        """Issue a fresh access token for an already-authenticated user."""
        user_id = user_payload.get("user_id") or user_payload.get("sub")
        tenant_id = user_payload.get("tenant_id")
        user = await EmployeeRepository.get_by_id(db, int(user_id))
        EmployeeSessionService.validate_employee_session(
            user,
            tenant_id=int(tenant_id),
            token_session_id=user_payload.get("session_id"),
        )
        token_data = {
            "sub": str(user.id),
            "tenant_id": user.tenant_id,
            "roles": user.roles,
            "session_id": user_payload.get("session_id"),
        }
        return create_access_token(token_data)

    @staticmethod
    async def get_current_user_info(db: AsyncSession, user_payload: dict) -> UserInfo:
        """Return fresh user profile and effective permissions for the current token."""
        principal = await PermissionService.get_current_principal(db, user_payload)
        user = await EmployeeRepository.get_by_id(db, principal.user_id)
        EmployeeSessionService.validate_employee_session(
            user,
            tenant_id=principal.tenant_id,
            token_session_id=user_payload.get("session_id"),
        )
        return AuthService._build_user_info(user, principal)

    @staticmethod
    async def update_current_user_preferences(
        db: AsyncSession,
        user_payload: dict,
        body: UserPreferencesUpdate,
    ) -> UserInfo:
        """Merge account-scoped UI preferences for the current employee."""
        principal = await PermissionService.get_current_principal(db, user_payload)
        user = await EmployeeRepository.get_by_id(db, principal.user_id)
        EmployeeSessionService.validate_employee_session(
            user,
            tenant_id=principal.tenant_id,
            token_session_id=user_payload.get("session_id"),
        )

        preferences = AuthService._merge_preferences(user.preferences or {}, body.preferences)
        user = await EmployeeRepository.update(db, user, {"preferences": preferences})
        return AuthService._build_user_info(user, principal)
