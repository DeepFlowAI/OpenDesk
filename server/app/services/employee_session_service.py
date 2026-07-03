"""
Employee login session helpers.
"""
import hmac
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import SessionReplacedError, UnauthorizedError
from app.models.employee import Employee
from app.repositories.employee_repository import EmployeeRepository

logger = logging.getLogger(__name__)


class EmployeeSessionService:
    @staticmethod
    def generate_session_id() -> str:
        """Generate an opaque marker for the current employee login."""
        return uuid.uuid4().hex

    @staticmethod
    def validate_employee_session(
        employee: Employee | None,
        *,
        tenant_id: int,
        token_session_id: object | None,
    ) -> Employee:
        """Ensure a JWT still matches the employee's current login session."""
        if not employee or employee.tenant_id != tenant_id or not employee.is_active:
            raise UnauthorizedError("Invalid or disabled account")

        current_session_id = employee.current_session_id
        token_session = str(token_session_id) if token_session_id else None

        # Compatibility window for tokens minted before this column existed.
        if current_session_id is None and token_session is None:
            return employee

        if not current_session_id or not token_session:
            raise SessionReplacedError()
        if not hmac.compare_digest(current_session_id, token_session):
            raise SessionReplacedError()
        return employee

    @staticmethod
    async def validate_payload(db: AsyncSession, payload: dict) -> Employee:
        """Validate a normalized employee JWT payload against the database."""
        user_id = payload.get("user_id") or payload.get("sub")
        tenant_id = payload.get("tenant_id")
        if user_id is None or tenant_id is None:
            raise UnauthorizedError("Invalid or expired token")

        employee = await EmployeeRepository.get_by_id(db, int(user_id))
        return EmployeeSessionService.validate_employee_session(
            employee,
            tenant_id=int(tenant_id),
            token_session_id=payload.get("session_id"),
        )

    @staticmethod
    async def disconnect_current_socket(tenant_id: int, user_id: int) -> None:
        """Best-effort disconnect of the currently tracked agent Socket.IO sid."""
        if not settings.REDIS_URL:
            return
        try:
            from app.db.redis import redis_client
            from app.libs.realtime import get_realtime_transport
            from app.services.agent_status_service import AgentStatusService
            from app.socketio.chat_handlers import NAMESPACE

            r = redis_client.client
            sid = await AgentStatusService.get_connection_sid(r, tenant_id, user_id)
            if not sid:
                return
            rt = get_realtime_transport()
            await rt.disconnect(sid, namespace=NAMESPACE)
            logger.info(
                "Disconnected previous employee socket tenant_id=%s user_id=%s sid=%s",
                tenant_id,
                user_id,
                sid,
            )
        except RuntimeError:
            logger.debug(
                "Skipped previous employee socket disconnect; realtime dependencies are not initialized",
                exc_info=True,
            )
        except Exception:
            logger.exception(
                "Failed to disconnect previous employee socket tenant_id=%s user_id=%s",
                tenant_id,
                user_id,
            )
