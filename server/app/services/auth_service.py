"""
Auth service
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError, NotFoundError
from app.core.security import verify_password, create_access_token
from app.repositories.tenant_repository import TenantRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo, UserPreferencesUpdate
from app.services.permission_service import PermissionService


class AuthService:
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

        await EmployeeRepository.update_last_login(db, user)

        token_data = {
            "sub": str(user.id),
            "tenant_id": tenant.id,
            "roles": user.roles,
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
    async def refresh_token(db: AsyncSession, user_payload: dict) -> str:
        """Issue a fresh access token for an already-authenticated user."""
        user_id = user_payload.get("user_id") or user_payload.get("sub")
        tenant_id = user_payload.get("tenant_id")
        user = await EmployeeRepository.get_by_id(db, int(user_id))
        if not user or user.tenant_id != int(tenant_id) or not user.is_active:
            raise UnauthorizedError("Invalid or disabled account")
        token_data = {
            "sub": str(user.id),
            "tenant_id": user.tenant_id,
            "roles": user.roles,
        }
        return create_access_token(token_data)

    @staticmethod
    async def get_current_user_info(db: AsyncSession, user_payload: dict) -> UserInfo:
        """Return fresh user profile and effective permissions for the current token."""
        principal = await PermissionService.get_current_principal(db, user_payload)
        user = await EmployeeRepository.get_by_id(db, principal.user_id)
        if not user or user.tenant_id != principal.tenant_id or not user.is_active:
            raise UnauthorizedError("Invalid or disabled account")
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
        if not user or user.tenant_id != principal.tenant_id or not user.is_active:
            raise UnauthorizedError("Invalid or disabled account")

        preferences = AuthService._merge_preferences(user.preferences or {}, body.preferences)
        user = await EmployeeRepository.update(db, user, {"preferences": preferences})
        return AuthService._build_user_info(user, principal)
