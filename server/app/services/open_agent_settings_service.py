"""
OpenAgent settings service.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.core.secret_store import decrypt_secret, encrypt_secret
from app.libs.open_agent import create_open_agent_client
from app.libs.open_agent.base import BaseOpenAgentClient, OpenAgentClientError
from app.repositories.open_agent_settings_repository import OpenAgentSettingsRepository
from app.schemas.open_agent_settings import (
    OpenAgentFAQ,
    OpenAgentAgentListResponse,
    OpenAgentAgentSummary,
    OpenAgentConnectionTestRequest,
    OpenAgentConnectionTestResponse,
    OpenAgentSettingsResponse,
    OpenAgentSettingsUpdate,
    OpenAgentWelcomeMessage,
)


class OpenAgentSettingsService:

    @staticmethod
    async def get_settings(db: AsyncSession, tenant_id: int) -> OpenAgentSettingsResponse:
        """Get OpenAgent settings for a tenant without exposing the API key."""
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item:
            return OpenAgentSettingsResponse()
        return OpenAgentSettingsResponse(
            base_url=item.base_url,
            has_api_key=bool(item.api_key_ciphertext),
            updated_at=item.updated_at,
        )

    @staticmethod
    async def update_settings(
        db: AsyncSession,
        tenant_id: int,
        data: OpenAgentSettingsUpdate,
    ) -> OpenAgentSettingsResponse:
        """Upsert OpenAgent settings for a tenant."""
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        api_key = data.api_key

        if not item and not api_key:
            raise ValidationError("API key is required for first OpenAgent binding")

        update_data = {"base_url": data.base_url}
        if api_key:
            update_data["api_key_ciphertext"] = encrypt_secret(api_key)

        if item:
            item = await OpenAgentSettingsRepository.update(db, item, update_data)
        else:
            create_data = {"tenant_id": tenant_id, **update_data}
            item = await OpenAgentSettingsRepository.create(db, create_data)

        return OpenAgentSettingsResponse(
            base_url=item.base_url,
            has_api_key=bool(item.api_key_ciphertext),
            updated_at=item.updated_at,
        )

    @staticmethod
    async def test_connection(
        db: AsyncSession,
        tenant_id: int,
        data: OpenAgentConnectionTestRequest,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentConnectionTestResponse:
        """Test OpenAgent connectivity using provided or stored credentials."""
        api_key = data.api_key or await OpenAgentSettingsService._load_saved_api_key(db, tenant_id)
        if not api_key:
            raise ValidationError("API key is required before testing OpenAgent connection")

        client = open_agent_client or create_open_agent_client()
        result = await client.test_connection(data.base_url, api_key)
        if not result.ok:
            raise ValidationError(result.message)
        return OpenAgentConnectionTestResponse(ok=True, message=result.message)

    @staticmethod
    async def get_credentials(db: AsyncSession, tenant_id: int) -> tuple[str, str] | None:
        """Return decrypted OpenAgent credentials for future server-side callers."""
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item:
            return None
        return item.base_url, decrypt_secret(item.api_key_ciphertext)

    @staticmethod
    async def list_active_agents(
        db: AsyncSession,
        tenant_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentAgentListResponse:
        """List active OpenAgent agents using saved tenant credentials."""
        credentials = await OpenAgentSettingsService.get_credentials(db, tenant_id)
        if not credentials:
            raise ValidationError("OpenAgent settings are required before listing agents")

        base_url, api_key = credentials
        if not api_key:
            raise ValidationError("OpenAgent API key is required before listing agents")

        client = open_agent_client or create_open_agent_client()
        try:
            result = await client.list_agents(
                base_url,
                api_key,
                status_filter="active",
                page=1,
                per_page=100,
            )
        except OpenAgentClientError as exc:
            raise ValidationError(str(exc)) from exc

        return OpenAgentAgentListResponse(
            items=[
                OpenAgentAgentSummary(
                    id=item.id,
                    name=item.name,
                    description=item.description,
                    status=item.status,
                )
                for item in result.items
                if item.status == "active"
            ],
            total=result.total,
            page=result.page,
            per_page=result.per_page,
            pages=result.pages,
        )

    @staticmethod
    async def get_agent_welcome_message(
        db: AsyncSession,
        tenant_id: int,
        agent_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentWelcomeMessage | None:
        """Return an enabled OpenAgent welcome message for visitor-facing use."""
        credentials = await OpenAgentSettingsService.get_credentials(db, tenant_id)
        if not credentials:
            return None

        base_url, api_key = credentials
        if not api_key:
            return None

        client = open_agent_client or create_open_agent_client()
        try:
            agent = await client.get_agent(base_url, api_key, agent_id)
        except OpenAgentClientError:
            return None

        if agent.status != "active" or not agent.welcome_message:
            return None

        try:
            welcome_message = OpenAgentWelcomeMessage.model_validate(agent.welcome_message)
        except PydanticValidationError:
            return None

        if not welcome_message.enabled or not welcome_message.blocks:
            return None

        if agent.faq:
            try:
                faq = OpenAgentFAQ.model_validate(agent.faq)
            except PydanticValidationError:
                faq = None
            if faq and faq.enabled and faq.categories:
                welcome_message.faq = faq
        return welcome_message

    @staticmethod
    async def _load_saved_api_key(db: AsyncSession, tenant_id: int) -> str | None:
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item:
            return None
        return decrypt_secret(item.api_key_ciphertext)
