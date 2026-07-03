"""
Auth service
"""
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
    async def login(db: AsyncSession, data: LoginRequest) -> LoginResponse:
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

        return LoginResponse(
            access_token=access_token,
            user=user_info,
        )

    @staticmethod
    async def sso_login(db: AsyncSession, data: SsoLoginRequest) -> LoginResponse:
        """Exchange a Tenant Platform SSO token for a normal OpenDesk JWT."""
        payload = AuthService._decode_sso_token(data.token)
        tenant_identifier = str(payload.get("tenant_id") or payload.get("sub") or "")
        tenant = await TenantRepository.resolve_by_identifier(db, tenant_identifier)
        if not tenant or not tenant.is_active:
            raise UnauthorizedError("Invalid or disabled tenant")

        user = await EmployeeRepository.get_sso_admin(db, tenant.id)
        if not user:
            raise UnauthorizedError("No enabled tenant admin account")

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
