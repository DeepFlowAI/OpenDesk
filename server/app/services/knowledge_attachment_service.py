"""Knowledge document attachment storage and access services."""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import UploadFile
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.enums import ConversationStatus, MessageContentType, MessageSenderType
from app.libs.storage import create_storage_client
from app.models.knowledge import KnowledgeDocumentAttachment
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.knowledge_repository import (
    KnowledgeDocumentAttachmentRepository,
    KnowledgeDocumentRepository,
)
from app.repositories.message_repository import MessageRepository
from app.schemas.knowledge import KnowledgeDocumentAttachmentResponse
from app.schemas.message import FileMessageContent
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_file_service import (
    BLOCKED_CONVERSATION_FILE_EXTENSIONS,
    TEMPORARY_URL_EXPIRES_SECONDS,
    ConversationFileService,
)

logger = logging.getLogger(__name__)

KNOWLEDGE_ATTACHMENT_STAGING_HOURS = 24
MAX_KNOWLEDGE_DOCUMENT_ATTACHMENTS = 10


class KnowledgeAttachmentService:
    @staticmethod
    def response(attachment: KnowledgeDocumentAttachment) -> KnowledgeDocumentAttachmentResponse:
        return KnowledgeDocumentAttachmentResponse.model_validate(attachment)

    @staticmethod
    async def delete_storage_keys(storage_keys: list[str]) -> None:
        if not storage_keys:
            return
        storage = create_storage_client()
        for storage_key in storage_keys:
            try:
                await storage.delete(storage_key)
            except Exception:
                logger.exception("Failed to delete knowledge attachment object: %s", storage_key)

    @staticmethod
    async def _cleanup_expired_staging(tenant_id: int) -> None:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            expired = await KnowledgeDocumentAttachmentRepository.list_expired_unbound(db, tenant_id, now)
            storage_keys = [attachment.storage_key for attachment in expired]
            for attachment in expired:
                await db.delete(attachment)
            if expired:
                await db.commit()
        await KnowledgeAttachmentService.delete_storage_keys(storage_keys)

    @staticmethod
    async def upload_managed(
        tenant_id: int,
        actor_id: int,
        file: UploadFile,
    ) -> KnowledgeDocumentAttachmentResponse:
        await KnowledgeAttachmentService._cleanup_expired_staging(tenant_id)
        raw_name, data, content_type, safe_ext = await ConversationFileService.read_validated_upload(file)
        date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
        storage_key = f"knowledge-attachments/{tenant_id}/{date_prefix}/{uuid.uuid4().hex}.{safe_ext}"
        storage = create_storage_client()
        await storage.upload(storage_key, data, content_type=content_type)

        try:
            async with AsyncSessionLocal() as db:
                attachment = await KnowledgeDocumentAttachmentRepository.create(
                    db,
                    {
                        "tenant_id": tenant_id,
                        "storage_key": storage_key,
                        "name": raw_name,
                        "size": len(data),
                        "mime_type": content_type,
                        "expires_at": datetime.now(timezone.utc)
                        + timedelta(hours=KNOWLEDGE_ATTACHMENT_STAGING_HOURS),
                        "created_by_actor_type": "employee",
                        "created_by_actor_id": actor_id,
                        "updated_by_actor_type": "employee",
                        "updated_by_actor_id": actor_id,
                    },
                )
        except Exception:
            await KnowledgeAttachmentService.delete_storage_keys([storage_key])
            raise
        return KnowledgeAttachmentService.response(attachment)

    @staticmethod
    async def stage_from_conversation_message_managed(
        principal: EffectivePrincipal,
        message_id: int,
    ) -> KnowledgeDocumentAttachmentResponse:
        """Copy an accessible agent file message into knowledge attachment staging."""
        await KnowledgeAttachmentService._cleanup_expired_staging(principal.tenant_id)
        async with AsyncSessionLocal() as db:
            message = await MessageRepository.get_by_id_for_tenant(
                db,
                principal.tenant_id,
                message_id,
            )
            if not message:
                raise NotFoundError("Message not found")
            if (
                message.sender_type != MessageSenderType.AGENT.value
                or message.content_type != MessageContentType.FILE.value
                or message.is_recalled
            ):
                raise ValidationError("Message is not an eligible file message")

            conversation = await ConversationRepository.get_by_id(db, message.conversation_id)
            if not conversation or conversation.tenant_id != principal.tenant_id:
                raise NotFoundError("Message not found")
            if conversation.status != ConversationStatus.ACTIVE.value:
                raise ValidationError("Conversation is not active")

            from app.services.conversation_service import ConversationService

            await ConversationService._assert_conversation_view_access(db, principal, conversation)
            try:
                payload = FileMessageContent.model_validate_json(message.content)
            except PydanticValidationError as exc:
                raise ValidationError("File message content is invalid") from exc

            source_key = ConversationFileService.decode_file_id(payload.file_id)
            conversation_prefix = (
                f"conversation-files/{principal.tenant_id}/{conversation.id}/"
            )
            if not source_key.startswith(conversation_prefix):
                raise ValidationError("File does not belong to conversation")
            name = payload.name
            size = payload.size
            mime_type = payload.mime_type

        ext = ConversationFileService._extension(name)
        safe_ext = ext if ext and ext not in BLOCKED_CONVERSATION_FILE_EXTENSIONS else "bin"
        date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
        storage_key = (
            f"knowledge-attachments/{principal.tenant_id}/{date_prefix}/"
            f"{uuid.uuid4().hex}.{safe_ext}"
        )
        storage = create_storage_client()
        await storage.copy(source_key, storage_key)

        try:
            async with AsyncSessionLocal() as db:
                attachment = await KnowledgeDocumentAttachmentRepository.create(
                    db,
                    {
                        "tenant_id": principal.tenant_id,
                        "storage_key": storage_key,
                        "name": name,
                        "size": size,
                        "mime_type": mime_type,
                        "expires_at": datetime.now(timezone.utc)
                        + timedelta(hours=KNOWLEDGE_ATTACHMENT_STAGING_HOURS),
                        "created_by_actor_type": "employee",
                        "created_by_actor_id": principal.user_id,
                        "updated_by_actor_type": "employee",
                        "updated_by_actor_id": principal.user_id,
                    },
                )
        except Exception:
            await KnowledgeAttachmentService.delete_storage_keys([storage_key])
            raise
        return KnowledgeAttachmentService.response(attachment)

    @staticmethod
    async def delete_staged_managed(tenant_id: int, actor_id: int, attachment_id: int) -> None:
        async with AsyncSessionLocal() as db:
            attachment = await KnowledgeDocumentAttachmentRepository.get_by_id(db, attachment_id)
            if not attachment or attachment.tenant_id != tenant_id:
                raise NotFoundError("Attachment not found")
            if attachment.document_id is not None:
                raise ValidationError("Saved attachment must be removed by updating the document")
            if attachment.created_by_actor_id != actor_id:
                raise NotFoundError("Attachment not found")
            storage_key = attachment.storage_key
            await KnowledgeDocumentAttachmentRepository.delete(db, attachment)
        await KnowledgeAttachmentService.delete_storage_keys([storage_key])

    @staticmethod
    async def get_temporary_url_managed(
        principal: EffectivePrincipal,
        attachment_id: int,
    ) -> dict:
        async with AsyncSessionLocal() as db:
            attachment = await KnowledgeDocumentAttachmentRepository.get_by_id(db, attachment_id)
            if not attachment or attachment.tenant_id != principal.tenant_id or attachment.document_id is None:
                raise NotFoundError("Attachment not found")
            document = await KnowledgeDocumentRepository.get_by_id(db, attachment.document_id)
            if not document or document.tenant_id != principal.tenant_id:
                raise NotFoundError("Attachment not found")
            if document.status == "draft" and not principal.has_permission("knowledge.workspace.document.edit"):
                raise NotFoundError("Attachment not found")
            storage_key = attachment.storage_key
            download_name = ConversationFileService._safe_download_name(attachment.name)

        storage = create_storage_client()
        url = await storage.get_temporary_url(
            storage_key,
            expires_seconds=TEMPORARY_URL_EXPIRES_SECONDS,
            download_name=download_name,
        )
        return {"url": url, "expires_seconds": TEMPORARY_URL_EXPIRES_SECONDS}
