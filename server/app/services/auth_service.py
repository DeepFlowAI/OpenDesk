"""
Auth service
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError, NotFoundError
from app.core.security import verify_password, create_access_token
from app.repositories.tenant_repository import TenantRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo


class AuthService:

    @staticmethod
    async def login(db: AsyncSession, data: LoginRequest) -> LoginResponse:
        """Authenticate user and return JWT token."""
        tenant = await TenantRepository.get_by_tenant_id(db, data.tenant)
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

        return LoginResponse(
            access_token=access_token,
            user=UserInfo.model_validate(user),
        )
