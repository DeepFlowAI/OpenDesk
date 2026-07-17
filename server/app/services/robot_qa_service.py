"""Business logic for OpenAgent robot-QA configuration and proxy calls."""
from typing import NoReturn

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.enums import ConversationStatus, MessageContentType, MessageSenderType
from app.libs.open_agent import create_open_agent_client
from app.libs.open_agent.base import (
    BaseOpenAgentClient,
    OpenAgentClientError,
    OpenAgentKnowledgeBaseSummary,
)
from app.repositories.open_agent_settings_repository import OpenAgentSettingsRepository
from app.schemas.robot_qa import (
    RobotQaKnowledgeBase,
    RobotQaKnowledgeBaseListResponse,
    RobotQaCreatePayload,
    RobotQaCreateResponse,
    RobotQaDirectory,
    RobotQaDirectoryListResponse,
    RobotQaRuntimeResponse,
    RobotQaSettingPayload,
    RobotQaSettingResponse,
)
from app.services.open_agent_settings_service import OpenAgentSettingsService
from app.services.conversation_service import ConversationService
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.permission import EffectivePrincipal
from app.db.session import AsyncSessionLocal


class RobotQaService:
    @staticmethod
    async def get_setting(db: AsyncSession, tenant_id: int) -> RobotQaSettingResponse:
        """Return the local robot-QA configuration without contacting OpenAgent."""
        item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
        if not item:
            return RobotQaSettingResponse()
        return RobotQaSettingResponse(
            enabled=bool(item.robot_qa_enabled),
            knowledge_base_id=item.robot_qa_knowledge_base_id,
            knowledge_base_name=item.robot_qa_knowledge_base_name,
        )

    @staticmethod
    async def list_knowledge_bases_managed(
        tenant_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> RobotQaKnowledgeBaseListResponse:
        """List all candidates without holding a DB connection during HTTP I/O."""
        credentials = await RobotQaService._load_credentials_managed(tenant_id)
        client = open_agent_client or create_open_agent_client()
        items = await RobotQaService._list_all_knowledge_bases(client, credentials)
        if items:
            try:
                await client.list_qa_directories(credentials[0], credentials[1], items[0].id)
            except OpenAgentClientError as exc:
                RobotQaService._raise_open_agent_error(exc)
        return RobotQaKnowledgeBaseListResponse(
            items=[
                RobotQaKnowledgeBase(
                    id=item.id,
                    name=item.name,
                    description=item.description,
                    status=item.status,
                )
                for item in items
            ]
        )

    @staticmethod
    async def save_setting_managed(
        tenant_id: int,
        data: RobotQaSettingPayload,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> RobotQaSettingResponse:
        """Validate upstream first, then persist in a fresh short DB session."""
        if not data.enabled:
            async with AsyncSessionLocal() as db:
                item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
                if not item:
                    return RobotQaSettingResponse()
                item = await OpenAgentSettingsRepository.update(
                    db,
                    item,
                    {"robot_qa_enabled": False},
                )
                return RobotQaService._setting_response(item)

        credentials = await RobotQaService._load_credentials_managed(tenant_id)
        client = open_agent_client or create_open_agent_client()
        items = await RobotQaService._list_all_knowledge_bases(client, credentials)
        target = next((item for item in items if item.id == data.knowledge_base_id), None)
        if target is None:
            raise BusinessError(
                "The selected OpenAgent knowledge base is unavailable",
                status_code=409,
                code="ROBOT_QA_CONFIG_INVALID",
            )
        try:
            await client.list_qa_directories(credentials[0], credentials[1], target.id)
        except OpenAgentClientError as exc:
            RobotQaService._raise_open_agent_error(exc)

        async with AsyncSessionLocal() as db:
            item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
            if not item:
                raise ValidationError("OpenAgent settings are required before enabling robot QA")
            item = await OpenAgentSettingsRepository.update(
                db,
                item,
                {
                    "robot_qa_enabled": True,
                    "robot_qa_knowledge_base_id": target.id,
                    "robot_qa_knowledge_base_name": target.name,
                },
            )
            return RobotQaService._setting_response(item)

    @staticmethod
    async def get_runtime_config_managed(
        tenant_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> RobotQaRuntimeResponse:
        """Validate the configured target for the agent workspace."""
        context = await RobotQaService._load_runtime_context_managed(tenant_id)
        if context is None:
            return RobotQaRuntimeResponse()
        credentials, knowledge_base_id, knowledge_base_name = context
        client = open_agent_client or create_open_agent_client()
        items = await RobotQaService._list_all_knowledge_bases(client, credentials)
        target = next((item for item in items if item.id == knowledge_base_id), None)
        if target is None:
            return RobotQaRuntimeResponse(
                enabled=True,
                available=False,
                knowledge_base_id=knowledge_base_id,
                knowledge_base_name=knowledge_base_name,
            )
        try:
            await client.list_qa_directories(credentials[0], credentials[1], target.id)
        except OpenAgentClientError as exc:
            RobotQaService._raise_open_agent_error(exc)
        return RobotQaRuntimeResponse(
            enabled=True,
            available=True,
            knowledge_base_id=target.id,
            knowledge_base_name=target.name,
        )

    @staticmethod
    async def list_directories_managed(
        tenant_id: int,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> RobotQaDirectoryListResponse:
        """List directories for the server-configured target knowledge base."""
        context = await RobotQaService._require_runtime_context_managed(tenant_id)
        credentials, knowledge_base_id, knowledge_base_name = context
        client = open_agent_client or create_open_agent_client()
        try:
            result = await client.list_qa_directories(
                credentials[0],
                credentials[1],
                knowledge_base_id,
            )
        except OpenAgentClientError as exc:
            RobotQaService._raise_open_agent_error(exc)
        return RobotQaDirectoryListResponse(
            knowledge_base_id=knowledge_base_id,
            knowledge_base_name=knowledge_base_name,
            items=[
                RobotQaDirectory(
                    id=item.id,
                    parent_id=item.parent_id,
                    name=item.name,
                    sort_order=item.sort_order,
                    depth=item.depth,
                    path=item.path,
                )
                for item in result.items
            ],
        )

    @staticmethod
    async def create_from_message_managed(
        *,
        conversation_id: int,
        message_id: int,
        principal: EffectivePrincipal,
        data: RobotQaCreatePayload,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> RobotQaCreateResponse:
        """Validate the live message source, then create QA without a held DB session."""
        async with AsyncSessionLocal() as db:
            item = await OpenAgentSettingsRepository.get_by_tenant_id(db, principal.tenant_id)
            if (
                not item
                or not item.robot_qa_enabled
                or item.robot_qa_knowledge_base_id is None
                or not item.robot_qa_knowledge_base_name
            ):
                raise BusinessError(
                    "Robot QA configuration is unavailable",
                    status_code=409,
                    code="ROBOT_QA_CONFIG_INVALID",
                )
            credentials = await OpenAgentSettingsService.get_credentials(db, principal.tenant_id)
            if not credentials:
                raise BusinessError(
                    "OpenAgent settings are required before using robot QA",
                    status_code=400,
                    code="ROBOT_QA_OPEN_AGENT_NOT_CONFIGURED",
                )
            knowledge_base_id = item.robot_qa_knowledge_base_id

            conversation = await ConversationRepository.get_by_id(db, conversation_id)
            if not conversation or conversation.tenant_id != principal.tenant_id:
                raise NotFoundError("Conversation not found")
            if conversation.status != ConversationStatus.ACTIVE.value:
                raise BusinessError(
                    "Robot QA can only be created from an active conversation",
                    status_code=409,
                    code="ROBOT_QA_MESSAGE_UNAVAILABLE",
                )
            await ConversationService._assert_conversation_view_access(db, principal, conversation)

            message = await MessageRepository.get_by_id_for_conversation(
                db,
                tenant_id=principal.tenant_id,
                conversation_id=conversation_id,
                message_id=message_id,
            )
            RobotQaService._validate_source_message(message)

        client = open_agent_client or create_open_agent_client()
        try:
            directories = await client.list_qa_directories(
                credentials[0],
                credentials[1],
                knowledge_base_id,
            )
            if not any(item.id == data.directory_id for item in directories.items):
                raise BusinessError(
                    "The selected OpenAgent QA directory is unavailable",
                    status_code=409,
                    code="ROBOT_QA_CONFIG_INVALID",
                )
            result = await client.create_qa(
                credentials[0],
                credentials[1],
                knowledge_base_id,
                data.model_dump(),
            )
        except OpenAgentClientError as exc:
            RobotQaService._raise_open_agent_error(exc, allow_duplicate=True)
        return RobotQaCreateResponse(
            id=result.id,
            knowledge_base_id=result.knowledge_base_id,
            directory_id=result.directory_id,
            process_status=result.process_status,
        )

    @staticmethod
    async def _load_credentials_managed(tenant_id: int) -> tuple[str, str]:
        async with AsyncSessionLocal() as db:
            credentials = await OpenAgentSettingsService.get_credentials(db, tenant_id)
        if not credentials:
            raise BusinessError(
                "OpenAgent settings are required before using robot QA",
                status_code=400,
                code="ROBOT_QA_OPEN_AGENT_NOT_CONFIGURED",
            )
        return credentials

    @staticmethod
    async def _load_runtime_context_managed(
        tenant_id: int,
    ) -> tuple[tuple[str, str], int, str] | None:
        async with AsyncSessionLocal() as db:
            item = await OpenAgentSettingsRepository.get_by_tenant_id(db, tenant_id)
            if not item or not item.robot_qa_enabled:
                return None
            if item.robot_qa_knowledge_base_id is None or not item.robot_qa_knowledge_base_name:
                raise BusinessError(
                    "Robot QA configuration is unavailable",
                    status_code=409,
                    code="ROBOT_QA_CONFIG_INVALID",
                )
            credentials = await OpenAgentSettingsService.get_credentials(db, tenant_id)
            knowledge_base_id = item.robot_qa_knowledge_base_id
            knowledge_base_name = item.robot_qa_knowledge_base_name
        if not credentials:
            raise BusinessError(
                "OpenAgent settings are required before using robot QA",
                status_code=400,
                code="ROBOT_QA_OPEN_AGENT_NOT_CONFIGURED",
            )
        return credentials, knowledge_base_id, knowledge_base_name

    @staticmethod
    async def _require_runtime_context_managed(
        tenant_id: int,
    ) -> tuple[tuple[str, str], int, str]:
        context = await RobotQaService._load_runtime_context_managed(tenant_id)
        if context is None:
            raise BusinessError(
                "Robot QA configuration is unavailable",
                status_code=409,
                code="ROBOT_QA_CONFIG_INVALID",
            )
        return context

    @staticmethod
    def _validate_source_message(message: object | None) -> None:
        if message is None or bool(getattr(message, "is_recalled", False)):
            raise BusinessError(
                "Message content is unavailable for robot QA",
                status_code=409,
                code="ROBOT_QA_MESSAGE_UNAVAILABLE",
            )
        if getattr(message, "sender_type", None) not in {
            MessageSenderType.VISITOR.value,
            MessageSenderType.AGENT.value,
            MessageSenderType.BOT.value,
        }:
            raise BusinessError(
                "Message content is unavailable for robot QA",
                status_code=409,
                code="ROBOT_QA_MESSAGE_UNAVAILABLE",
            )
        content_type = getattr(message, "content_type", None)
        if content_type not in {MessageContentType.TEXT.value, MessageContentType.RICH_TEXT.value}:
            raise BusinessError(
                "Message content is unavailable for robot QA",
                status_code=409,
                code="ROBOT_QA_MESSAGE_UNAVAILABLE",
            )
        content = getattr(message, "content", "")
        visible_content = (
            ConversationService._html_to_plain_text(content)
            if content_type == MessageContentType.RICH_TEXT.value
            else content
        )
        if not visible_content.strip():
            raise BusinessError(
                "Message content is unavailable for robot QA",
                status_code=409,
                code="ROBOT_QA_MESSAGE_UNAVAILABLE",
            )

    @staticmethod
    async def _list_all_knowledge_bases(
        client: BaseOpenAgentClient,
        credentials: tuple[str, str],
    ) -> list[OpenAgentKnowledgeBaseSummary]:
        base_url, api_key = credentials
        items: list[OpenAgentKnowledgeBaseSummary] = []
        page = 1
        try:
            while True:
                result = await client.list_knowledge_bases(
                    base_url,
                    api_key,
                    page=page,
                    per_page=100,
                )
                items.extend(result.items)
                if page >= result.pages:
                    break
                page += 1
        except OpenAgentClientError as exc:
            RobotQaService._raise_open_agent_error(exc)
        return items

    @staticmethod
    def _setting_response(item: object) -> RobotQaSettingResponse:
        return RobotQaSettingResponse(
            enabled=bool(getattr(item, "robot_qa_enabled", False)),
            knowledge_base_id=getattr(item, "robot_qa_knowledge_base_id", None),
            knowledge_base_name=getattr(item, "robot_qa_knowledge_base_name", None),
        )

    @staticmethod
    def _raise_open_agent_error(
        exc: OpenAgentClientError,
        *,
        allow_duplicate: bool = False,
    ) -> NoReturn:
        if allow_duplicate and exc.status_code == 409:
            raise BusinessError(
                "The target knowledge base already contains the same question",
                status_code=409,
                code="ROBOT_QA_QUESTION_DUPLICATE",
            ) from exc
        if exc.status_code in {401, 403}:
            raise BusinessError(
                "OpenAgent API key lacks the required knowledge-base permissions",
                status_code=400,
                code="ROBOT_QA_OPEN_AGENT_SCOPE_ERROR",
            ) from exc
        if exc.status_code == 404:
            raise BusinessError(
                "The configured OpenAgent knowledge base is unavailable",
                status_code=409,
                code="ROBOT_QA_CONFIG_INVALID",
            ) from exc
        raise BusinessError(
            "OpenAgent knowledge base is temporarily unavailable",
            status_code=502,
            code="ROBOT_QA_UPSTREAM_UNAVAILABLE",
        ) from exc
