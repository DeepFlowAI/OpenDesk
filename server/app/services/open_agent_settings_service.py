"""
OpenAgent settings service.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ForbiddenError, ValidationError
from app.core.secret_store import decrypt_secret, encrypt_secret
from app.db.session import AsyncSessionLocal
from app.libs.open_agent import create_open_agent_client
from app.libs.open_agent.base import BaseOpenAgentClient, OpenAgentClientError
from app.libs.voice_speed import create_voice_speed_client
from app.libs.voice_speed.base import BaseVoiceSpeedClient, VoiceSpeedClientError
from app.repositories.open_agent_settings_repository import OpenAgentSettingsRepository
from app.schemas.open_agent_settings import (
    OpenAgentAIDisclaimer,
    OpenAgentAttachmentHandoffStatus,
    OpenAgentFAQ,
    OpenAgentAgentListResponse,
    OpenAgentAgentSummary,
    OpenAgentConnectionTestRequest,
    OpenAgentConnectionTestResponse,
    OpenAgentSettingsResponse,
    OpenAgentSettingsUpdate,
    OpenAgentVisitorRuntimeConfig,
    OpenAgentWelcomeMessage,
    VoiceSpeedAgentListResponse,
    VoiceSpeedAgentSummary,
    VoiceSpeedConnectionTestRequest,
    VoiceSpeedConnectionTestResponse,
    VoiceSpeedSettingsResponse,
    VoiceSpeedSettingsUpdate,
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

        if (not item or not item.api_key_ciphertext) and not api_key:
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
        return await OpenAgentSettingsService._test_connection_with_api_key(
            data.base_url,
            api_key,
            open_agent_client=open_agent_client,
        )

    @staticmethod
    async def test_connection_managed(
        tenant_id: int,
        data: OpenAgentConnectionTestRequest,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentConnectionTestResponse:
        """Test OpenAgent connectivity without holding a DB session during HTTP."""
        async with AsyncSessionLocal() as db:
            api_key = data.api_key or await OpenAgentSettingsService._load_saved_api_key(db, tenant_id)
        return await OpenAgentSettingsService._test_connection_with_api_key(
            data.base_url,
            api_key,
            open_agent_client=open_agent_client,
        )

    @staticmethod
    async def _test_connection_with_api_key(
        base_url: str,
        api_key: str | None,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentConnectionTestResponse:
        if not api_key:
            raise ValidationError("API key is required before testing OpenAgent connection")

        client = open_agent_client or create_open_agent_client()
        result = await client.test_connection(base_url, api_key)
        if not result.ok:
            raise ValidationError(result.message)
        return OpenAgentConnectionTestResponse(ok=True, message=result.message)

    @staticmethod
    async def get_credentials(db: AsyncSession, tenant_id: int) -> tuple[str, str] | None:
        """Return decrypted OpenAgent credentials for future server-side callers."""
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item or not item.base_url or not item.api_key_ciphertext:
            return None
        return item.base_url, decrypt_secret(item.api_key_ciphertext)

    @staticmethod
    async def get_voice_speed_settings(db: AsyncSession, tenant_id: int) -> VoiceSpeedSettingsResponse:
        """Get VoiceSpeed settings for a tenant without exposing the API key."""
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item:
            return VoiceSpeedSettingsResponse()
        return VoiceSpeedSettingsResponse(
            base_url=item.voice_speed_base_url,
            has_api_key=bool(item.voice_speed_api_key_ciphertext),
            updated_at=item.updated_at,
        )

    @staticmethod
    async def update_voice_speed_settings(
        db: AsyncSession,
        tenant_id: int,
        data: VoiceSpeedSettingsUpdate,
    ) -> VoiceSpeedSettingsResponse:
        """Upsert VoiceSpeed settings for a tenant."""
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        api_key = data.api_key

        if (not item or not item.voice_speed_api_key_ciphertext) and not api_key:
            raise ValidationError("API key is required for first VoiceSpeed binding")

        update_data = {"voice_speed_base_url": data.base_url}
        if api_key:
            update_data["voice_speed_api_key_ciphertext"] = encrypt_secret(api_key)

        if item:
            item = await OpenAgentSettingsRepository.update(db, item, update_data)
        else:
            create_data = {"tenant_id": tenant_id, **update_data}
            item = await OpenAgentSettingsRepository.create(db, create_data)

        return VoiceSpeedSettingsResponse(
            base_url=item.voice_speed_base_url,
            has_api_key=bool(item.voice_speed_api_key_ciphertext),
            updated_at=item.updated_at,
        )

    @staticmethod
    async def test_voice_speed_connection(
        db: AsyncSession,
        tenant_id: int,
        data: VoiceSpeedConnectionTestRequest,
        voice_speed_client: BaseVoiceSpeedClient | None = None,
    ) -> VoiceSpeedConnectionTestResponse:
        """Test VoiceSpeed connectivity using provided or stored credentials."""
        api_key = data.api_key or await OpenAgentSettingsService._load_saved_voice_speed_api_key(db, tenant_id)
        return await OpenAgentSettingsService._test_voice_speed_connection_with_api_key(
            data.base_url,
            api_key,
            voice_speed_client=voice_speed_client,
        )

    @staticmethod
    async def test_voice_speed_connection_managed(
        tenant_id: int,
        data: VoiceSpeedConnectionTestRequest,
        voice_speed_client: BaseVoiceSpeedClient | None = None,
    ) -> VoiceSpeedConnectionTestResponse:
        """Test VoiceSpeed connectivity without holding a DB session during HTTP."""
        async with AsyncSessionLocal() as db:
            api_key = data.api_key or await OpenAgentSettingsService._load_saved_voice_speed_api_key(
                db, tenant_id
            )
        return await OpenAgentSettingsService._test_voice_speed_connection_with_api_key(
            data.base_url,
            api_key,
            voice_speed_client=voice_speed_client,
        )

    @staticmethod
    async def _test_voice_speed_connection_with_api_key(
        base_url: str,
        api_key: str | None,
        voice_speed_client: BaseVoiceSpeedClient | None = None,
    ) -> VoiceSpeedConnectionTestResponse:
        if not api_key:
            raise ValidationError("API key is required before testing VoiceSpeed connection")

        client = voice_speed_client or create_voice_speed_client()
        result = await client.test_connection(base_url, api_key)
        if not result.ok:
            raise ValidationError(result.message)
        return VoiceSpeedConnectionTestResponse(ok=True, message=result.message)

    @staticmethod
    async def get_voice_speed_credentials(db: AsyncSession, tenant_id: int) -> tuple[str, str] | None:
        """Return decrypted VoiceSpeed credentials for future server-side callers."""
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item or not item.voice_speed_base_url or not item.voice_speed_api_key_ciphertext:
            return None
        return item.voice_speed_base_url, decrypt_secret(item.voice_speed_api_key_ciphertext)

    @staticmethod
    async def list_voice_speed_agents(
        db: AsyncSession,
        tenant_id: int,
        voice_speed_client: BaseVoiceSpeedClient | None = None,
    ) -> VoiceSpeedAgentListResponse:
        """List enabled VoiceSpeed agents using saved tenant credentials.

        Returns ``configured=False`` when no VoiceSpeed base_url / api_key is
        bound. The API key never leaves the server and is never returned.
        """
        credentials = await OpenAgentSettingsService.get_voice_speed_credentials(db, tenant_id)
        return await OpenAgentSettingsService._list_voice_speed_agents_from_credentials(
            credentials,
            voice_speed_client=voice_speed_client,
        )

    @staticmethod
    async def list_voice_speed_agents_managed(
        tenant_id: int,
        voice_speed_client: BaseVoiceSpeedClient | None = None,
    ) -> VoiceSpeedAgentListResponse:
        """List VoiceSpeed agents without holding a DB session during HTTP."""
        async with AsyncSessionLocal() as db:
            credentials = await OpenAgentSettingsService.get_voice_speed_credentials(db, tenant_id)
        return await OpenAgentSettingsService._list_voice_speed_agents_from_credentials(
            credentials,
            voice_speed_client=voice_speed_client,
        )

    @staticmethod
    async def _list_voice_speed_agents_from_credentials(
        credentials: tuple[str, str] | None,
        voice_speed_client: BaseVoiceSpeedClient | None = None,
    ) -> VoiceSpeedAgentListResponse:
        if not credentials:
            return VoiceSpeedAgentListResponse(configured=False, items=[])

        base_url, api_key = credentials
        client = voice_speed_client or create_voice_speed_client()
        try:
            result = await client.list_agents(base_url, api_key, status="enabled")
        except VoiceSpeedClientError as exc:
            if exc.status_code == 403:
                raise ForbiddenError(str(exc)) from exc
            raise ValidationError(str(exc)) from exc

        return VoiceSpeedAgentListResponse(
            configured=True,
            items=[
                VoiceSpeedAgentSummary(
                    id=item.id,
                    name=item.name,
                    description=item.description,
                    status=item.status,
                )
                for item in result.items
            ],
        )

    @staticmethod
    async def list_active_agents(
        db: AsyncSession,
        tenant_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentAgentListResponse:
        """List active OpenAgent agents using saved tenant credentials."""
        credentials = await OpenAgentSettingsService.get_credentials(db, tenant_id)
        return await OpenAgentSettingsService._list_active_agents_from_credentials(
            credentials,
            open_agent_client=open_agent_client,
        )

    @staticmethod
    async def list_active_agents_managed(
        tenant_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentAgentListResponse:
        """List active OpenAgent agents without holding a DB session during HTTP."""
        async with AsyncSessionLocal() as db:
            credentials = await OpenAgentSettingsService.get_credentials(db, tenant_id)
        return await OpenAgentSettingsService._list_active_agents_from_credentials(
            credentials,
            open_agent_client=open_agent_client,
        )

    @staticmethod
    async def _list_active_agents_from_credentials(
        credentials: tuple[str, str] | None,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentAgentListResponse:
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
    async def get_attachment_handoff_status(
        db: AsyncSession,
        tenant_id: int,
        agent_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentAttachmentHandoffStatus:
        """Check whether an agent can route attachment-only turns to a human."""
        credentials = await OpenAgentSettingsService.get_credentials(db, tenant_id)
        return await OpenAgentSettingsService._attachment_handoff_status_from_credentials(
            credentials,
            agent_id,
            open_agent_client=open_agent_client,
        )

    @staticmethod
    async def get_attachment_handoff_status_managed(
        tenant_id: int,
        agent_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentAttachmentHandoffStatus:
        """Check attachment handoff without holding a DB session during HTTP."""
        async with AsyncSessionLocal() as db:
            credentials = await OpenAgentSettingsService.get_credentials(db, tenant_id)
        return await OpenAgentSettingsService._attachment_handoff_status_from_credentials(
            credentials,
            agent_id,
            open_agent_client=open_agent_client,
        )

    @staticmethod
    async def _attachment_handoff_status_from_credentials(
        credentials: tuple[str, str] | None,
        agent_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentAttachmentHandoffStatus:
        if not credentials or not credentials[1]:
            raise ValidationError("OpenAgent settings are required before checking attachments")

        base_url, api_key = credentials
        client = open_agent_client or create_open_agent_client()
        try:
            agent = await client.get_agent(base_url, api_key, agent_id)
        except OpenAgentClientError as exc:
            if exc.status_code == 404:
                return OpenAgentAttachmentHandoffStatus(
                    ready=False,
                    reason="agent_unavailable",
                )
            raise ValidationError(str(exc)) from exc

        if agent.status != "active":
            return OpenAgentAttachmentHandoffStatus(
                ready=False,
                reason="agent_unavailable",
            )

        tool_id = agent.attachment_handoff_tool_id
        if tool_id is None:
            return OpenAgentAttachmentHandoffStatus(
                ready=False,
                reason="not_configured",
            )

        try:
            tool = await client.get_agent_tool(base_url, api_key, agent_id, tool_id)
        except OpenAgentClientError as exc:
            if exc.status_code == 404:
                return OpenAgentAttachmentHandoffStatus(
                    ready=False,
                    reason="tool_unavailable",
                    tool_id=tool_id,
                )
            raise ValidationError(str(exc)) from exc

        ready = (
            tool.id == tool_id
            and tool.agent_id == agent_id
            and tool.tool_type == "human_handoff"
            and tool.is_enabled
        )
        return OpenAgentAttachmentHandoffStatus(
            ready=ready,
            reason="ready" if ready else "tool_unavailable",
            tool_id=tool_id,
        )

    @staticmethod
    async def get_agent_welcome_message(
        db: AsyncSession,
        tenant_id: int,
        agent_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentWelcomeMessage | None:
        """Return an enabled OpenAgent welcome message for visitor-facing use."""
        runtime_config = await OpenAgentSettingsService.get_agent_visitor_runtime_config(
            db,
            tenant_id,
            agent_id,
            open_agent_client=open_agent_client,
        )
        return runtime_config.welcome_message

    @staticmethod
    async def get_agent_visitor_runtime_config(
        db: AsyncSession,
        tenant_id: int,
        agent_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentVisitorRuntimeConfig:
        """Return visitor-facing OpenAgent runtime settings."""
        credentials = await OpenAgentSettingsService.get_credentials(db, tenant_id)
        return await OpenAgentSettingsService._visitor_runtime_config_from_credentials(
            credentials,
            agent_id,
            open_agent_client=open_agent_client,
        )

    @staticmethod
    async def get_agent_visitor_runtime_config_managed(
        tenant_id: int,
        agent_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentVisitorRuntimeConfig:
        """Load credentials briefly, then fetch OpenAgent runtime config without a DB session."""
        async with AsyncSessionLocal() as db:
            credentials = await OpenAgentSettingsService.get_credentials(db, tenant_id)
        return await OpenAgentSettingsService._visitor_runtime_config_from_credentials(
            credentials,
            agent_id,
            open_agent_client=open_agent_client,
        )

    @staticmethod
    async def _visitor_runtime_config_from_credentials(
        credentials: tuple[str, str] | None,
        agent_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> OpenAgentVisitorRuntimeConfig:
        if not credentials:
            return OpenAgentVisitorRuntimeConfig()

        base_url, api_key = credentials
        if not api_key:
            return OpenAgentVisitorRuntimeConfig()

        client = open_agent_client or create_open_agent_client()
        try:
            agent = await client.get_agent(base_url, api_key, agent_id)
        except OpenAgentClientError:
            return OpenAgentVisitorRuntimeConfig()

        if agent.status != "active":
            return OpenAgentVisitorRuntimeConfig()

        welcome_message = None
        try:
            if agent.welcome_message:
                candidate = OpenAgentWelcomeMessage.model_validate(agent.welcome_message)
                if candidate.enabled and candidate.blocks:
                    welcome_message = candidate
        except PydanticValidationError:
            welcome_message = None

        if welcome_message and agent.faq:
            try:
                faq = OpenAgentFAQ.model_validate(agent.faq)
            except PydanticValidationError:
                faq = None
            if faq and faq.enabled and faq.categories:
                welcome_message.faq = faq

        ai_disclaimer = None
        try:
            if agent.ai_disclaimer:
                candidate = OpenAgentAIDisclaimer.model_validate(agent.ai_disclaimer)
                if candidate.enabled and candidate.content:
                    ai_disclaimer = candidate
        except PydanticValidationError:
            ai_disclaimer = None

        return OpenAgentVisitorRuntimeConfig(
            welcome_message=welcome_message,
            ai_disclaimer=ai_disclaimer,
        )

    @staticmethod
    async def _load_saved_api_key(db: AsyncSession, tenant_id: int) -> str | None:
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item or not item.api_key_ciphertext:
            return None
        return decrypt_secret(item.api_key_ciphertext)

    @staticmethod
    async def _load_saved_voice_speed_api_key(db: AsyncSession, tenant_id: int) -> str | None:
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item or not item.voice_speed_api_key_ciphertext:
            return None
        return decrypt_secret(item.voice_speed_api_key_ciphertext)
