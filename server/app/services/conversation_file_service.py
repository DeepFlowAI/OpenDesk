"""
Conversation file service.
"""
import base64
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.enums import MessageContentType
from app.libs.storage import create_storage_client
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.permission import EffectivePrincipal

MAX_CONVERSATION_FILE_SIZE = 100 * 1024 * 1024
TEMPORARY_URL_EXPIRES_SECONDS = 24 * 60 * 60
CONVERSATION_IMAGE_DISPLAY_PROCESS = "image/resize,w_720/quality,q_80"
KNOWLEDGE_IMAGE_PROCESS_PROFILES = (
    "image/resize,l_4096,limit_1/format,webp/quality,Q_85",
    "image/resize,l_3072,limit_1/format,webp/quality,Q_75",
    "image/resize,l_2048,limit_1/format,webp/quality,Q_65",
    "image/resize,l_4096,limit_1/format,gif",
    "image/resize,l_3072,limit_1/format,gif",
    "image/resize,l_2048,limit_1/format,gif",
)
ALLOWED_CONVERSATION_IMAGE_PROCESSES = {
    CONVERSATION_IMAGE_DISPLAY_PROCESS,
    *KNOWLEDGE_IMAGE_PROCESS_PROFILES,
}
BLOCKED_CONVERSATION_FILE_EXTENSIONS = {
    "exe",
    "bat",
    "cmd",
    "com",
    "msi",
    "scr",
    "pif",
    "dll",
    "vbs",
    "jar",
    "app",
    "deb",
    "rpm",
}
IMAGE_MAGIC_NUMBERS = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
}
IMAGE_MIME_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}
GENERIC_UPLOAD_CONTENT_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
}


class ConversationFileService:
    @staticmethod
    def encode_file_id(key: str) -> str:
        """Encode a storage key into a URL-safe file ID."""
        return base64.urlsafe_b64encode(key.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def decode_file_id(file_id: str) -> str:
        """Decode a URL-safe file ID into a storage key."""
        if not file_id or not re.fullmatch(r"[A-Za-z0-9_-]+", file_id):
            raise ValidationError("Invalid file ID")
        padding = "=" * (-len(file_id) % 4)
        try:
            return base64.urlsafe_b64decode(f"{file_id}{padding}").decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise ValidationError("Invalid file ID")

    @staticmethod
    def _extension(filename: str) -> str:
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    @staticmethod
    def _safe_download_name(filename: str) -> str:
        return re.sub(r'[\r\n"]+', "_", filename)[:255] or "download"

    @staticmethod
    def _safe_image_process(image_process: str | None, download: bool) -> str | None:
        if download or image_process is None:
            return None
        if image_process not in ALLOWED_CONVERSATION_IMAGE_PROCESSES:
            raise ValidationError("Unsupported image process")
        return image_process

    @staticmethod
    def _detect_image_mime_type(data: bytes) -> str | None:
        if data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if data.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return "image/webp"
        return None

    @staticmethod
    def _validate_magic_number(content_type: str, data: bytes) -> None:
        if content_type == "image/webp":
            if not (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
                raise ValidationError("File content does not match MIME type")
            return
        signatures = IMAGE_MAGIC_NUMBERS.get(content_type)
        if not signatures:
            return
        if not any(data.startswith(signature) for signature in signatures):
            raise ValidationError("File content does not match MIME type")

    @staticmethod
    def _normalize_upload_metadata(content_type: str | None, ext: str, data: bytes) -> tuple[str, str]:
        declared_content_type = (
            (content_type or "application/octet-stream")
            .split(";", 1)[0]
            .strip()
            .lower()
        )
        if not declared_content_type:
            declared_content_type = "application/octet-stream"

        detected_image_type = ConversationFileService._detect_image_mime_type(data)
        if declared_content_type in IMAGE_MAGIC_NUMBERS:
            if not detected_image_type:
                raise ValidationError("File content does not match MIME type")
            return detected_image_type, IMAGE_MIME_EXTENSIONS[detected_image_type]

        if detected_image_type and declared_content_type in GENERIC_UPLOAD_CONTENT_TYPES:
            return detected_image_type, IMAGE_MIME_EXTENSIONS[detected_image_type]

        safe_ext = ext if ext and ext not in BLOCKED_CONVERSATION_FILE_EXTENSIONS else "bin"
        return declared_content_type, safe_ext

    @staticmethod
    async def read_validated_upload(file: UploadFile) -> tuple[str, bytes, str, str]:
        """Read an upload and return safe metadata shared by file features."""
        raw_name = (file.filename or "upload")[:255]
        ext = ConversationFileService._extension(raw_name)
        if ext in BLOCKED_CONVERSATION_FILE_EXTENSIONS:
            raise ValidationError(f"File type .{ext} is not allowed for security reasons")

        data = await file.read()
        if not data:
            raise ValidationError("File is empty")
        if len(data) > MAX_CONVERSATION_FILE_SIZE:
            raise ValidationError("File size exceeds 100MB limit")

        content_type, safe_ext = ConversationFileService._normalize_upload_metadata(
            file.content_type,
            ext,
            data,
        )
        return raw_name, data, content_type, safe_ext

    @staticmethod
    async def _get_conversation_for_visitor(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        visitor_external_id: str,
    ):
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation:
            raise NotFoundError("Conversation not found")
        if conversation.tenant_id != tenant_id:
            raise ValidationError("Conversation does not match tenant")
        if not conversation.visitor or conversation.visitor.external_id != visitor_external_id:
            raise ValidationError("Conversation does not match visitor")
        return conversation

    @staticmethod
    async def _get_conversation_for_agent(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        principal: EffectivePrincipal | None = None,
        action: str = "view",
    ):
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation:
            raise NotFoundError("Conversation not found")
        if conversation.tenant_id != tenant_id:
            raise ValidationError("Conversation does not match tenant")
        if principal is not None:
            from app.services.conversation_service import ConversationService

            if action == "send_file":
                await ConversationService._assert_conversation_send_access(
                    db,
                    principal,
                    conversation,
                    MessageContentType.FILE.value,
                )
            else:
                await ConversationService._assert_conversation_view_access(
                    db,
                    principal,
                    conversation,
                )
            return conversation
        if conversation.agent_id != agent_id:
            raise ValidationError("Conversation does not match agent")
        return conversation

    @staticmethod
    async def _upload_file(
        conversation_id: int,
        tenant_id: int,
        file: UploadFile,
    ) -> dict:
        raw_name, data, content_type, safe_ext = await ConversationFileService.read_validated_upload(file)
        date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"conversation-files/{tenant_id}/{conversation_id}/{date_prefix}/{uuid.uuid4().hex}.{safe_ext}"

        storage = create_storage_client()
        await storage.upload(key, data, content_type=content_type)
        access_url = await storage.get_temporary_url(
            key,
            expires_seconds=TEMPORARY_URL_EXPIRES_SECONDS,
        )

        file_id = ConversationFileService.encode_file_id(key)
        return {
            "schema_version": 1,
            "file_id": file_id,
            "name": raw_name,
            "size": len(data),
            "mime_type": content_type,
            "access_url": access_url,
        }

    @staticmethod
    async def upload_visitor_file(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        visitor_external_id: str,
        file: UploadFile,
    ) -> dict:
        """Upload a visitor conversation file and return structured metadata."""
        await ConversationFileService._get_conversation_for_visitor(
            db,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            visitor_external_id=visitor_external_id,
        )

        return await ConversationFileService._upload_file(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            file=file,
        )

    @staticmethod
    async def upload_visitor_file_for_session(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
        file: UploadFile,
    ) -> dict:
        """Upload a visitor file for a token-bound public conversation."""
        from app.services.conversation_service import ConversationService

        conversation = await ConversationService.get_conversation_for_visitor_session(
            db,
            conversation_public_id=conversation_public_id,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
        )
        return await ConversationFileService._upload_file(
            conversation_id=conversation.id,
            tenant_id=conversation.tenant_id,
            file=file,
        )

    @staticmethod
    async def upload_visitor_file_for_session_managed(
        conversation_public_id: str,
        visitor_context: dict,
        file: UploadFile,
    ) -> dict:
        """Upload a visitor file without holding a DB session during object storage I/O."""
        from app.services.conversation_service import ConversationService

        async with AsyncSessionLocal() as db:
            conversation = await ConversationService.get_conversation_for_visitor_session(
                db,
                conversation_public_id=conversation_public_id,
                tenant_id=visitor_context["tenant_id"],
                channel_id=visitor_context["channel_id"],
                visitor_external_id=visitor_context["visitor_external_id"],
            )
            conversation_id = conversation.id
            tenant_id = conversation.tenant_id

        return await ConversationFileService._upload_file(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            file=file,
        )

    @staticmethod
    def validate_conversation_file_id(
        file_id: str,
        *,
        tenant_id: int,
        conversation_id: int,
    ) -> str:
        """Return the storage key after verifying conversation ownership."""
        key = ConversationFileService.decode_file_id(file_id)
        expected_prefix = f"conversation-files/{tenant_id}/{conversation_id}/"
        if not key.startswith(expected_prefix):
            raise ValidationError("File does not belong to conversation")
        return key

    @staticmethod
    async def build_open_agent_attachment(
        *,
        tenant_id: int,
        conversation_id: int,
        file_id: str,
        attachment_type: str,
        name: str,
        mime_type: str,
        size: int,
    ) -> dict:
        """Generate a fresh HTTPS URL for an OpenAgent attachment payload."""
        key = ConversationFileService.validate_conversation_file_id(
            file_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        storage = create_storage_client()
        url = await storage.get_temporary_url(
            key,
            expires_seconds=TEMPORARY_URL_EXPIRES_SECONDS,
        )
        if urlsplit(url).scheme.lower() != "https":
            raise ValidationError("OpenAgent attachment URL must use HTTPS")
        return {
            "type": attachment_type,
            "url": url,
            "name": name,
            "mime_type": mime_type,
            "size": size,
        }

    @staticmethod
    async def upload_agent_file(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        file: UploadFile,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        """Upload an agent conversation file and return structured metadata."""
        await ConversationFileService._get_conversation_for_agent(
            db,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            principal=principal,
            action="send_file",
        )

        return await ConversationFileService._upload_file(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            file=file,
        )

    @staticmethod
    async def upload_agent_file_managed(
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        file: UploadFile,
        principal: EffectivePrincipal,
    ) -> dict:
        """Upload an agent file without holding a DB session during file I/O."""
        async with AsyncSessionLocal() as db:
            await ConversationFileService._get_conversation_for_agent(
                db,
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                agent_id=agent_id,
                principal=principal,
                action="send_file",
            )

        return await ConversationFileService._upload_file(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            file=file,
        )

    @staticmethod
    async def prepare_knowledge_attachment_managed(
        conversation_id: int,
        attachment_id: int,
        principal: EffectivePrincipal,
    ) -> dict:
        """Copy a saved knowledge attachment into a conversation file namespace."""
        from app.repositories.knowledge_repository import (
            KnowledgeDocumentAttachmentRepository,
            KnowledgeDocumentRepository,
        )

        async with AsyncSessionLocal() as db:
            await ConversationFileService._get_conversation_for_agent(
                db,
                conversation_id=conversation_id,
                tenant_id=principal.tenant_id,
                agent_id=principal.user_id,
                principal=principal,
                action="send_file",
            )
            attachment = await KnowledgeDocumentAttachmentRepository.get_by_id(db, attachment_id)
            if not attachment or attachment.tenant_id != principal.tenant_id or attachment.document_id is None:
                raise NotFoundError("Attachment not found")
            document = await KnowledgeDocumentRepository.get_by_id(db, attachment.document_id)
            if not document or document.tenant_id != principal.tenant_id or document.status != "published":
                raise NotFoundError("Attachment not found")
            if document.validity_type == "scheduled":
                now = datetime.now(timezone.utc)
                valid_from = document.valid_from
                valid_to = document.valid_to
                if valid_from is not None and valid_from.tzinfo is None:
                    valid_from = valid_from.replace(tzinfo=timezone.utc)
                if valid_to is not None and valid_to.tzinfo is None:
                    valid_to = valid_to.replace(tzinfo=timezone.utc)
                if valid_from is None or valid_to is None or now < valid_from or now > valid_to:
                    raise NotFoundError("Attachment not found")
            source_key = attachment.storage_key
            name = attachment.name
            size = attachment.size
            mime_type = attachment.mime_type

        ext = ConversationFileService._extension(name)
        safe_ext = ext if ext and ext not in BLOCKED_CONVERSATION_FILE_EXTENSIONS else "bin"
        date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
        destination_key = (
            f"conversation-files/{principal.tenant_id}/{conversation_id}/{date_prefix}/"
            f"{uuid.uuid4().hex}.{safe_ext}"
        )
        storage = create_storage_client()
        await storage.copy(source_key, destination_key)
        access_url = await storage.get_temporary_url(
            destination_key,
            expires_seconds=TEMPORARY_URL_EXPIRES_SECONDS,
        )
        return {
            "schema_version": 1,
            "file_id": ConversationFileService.encode_file_id(destination_key),
            "name": name,
            "size": size,
            "mime_type": mime_type,
            "access_url": access_url,
        }

    @staticmethod
    async def _resolve_accessible_file_key(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        file_id: str,
    ) -> str:
        """Validate file ownership / recall state and return the storage key."""
        from app.repositories.message_repository import MessageRepository

        key = ConversationFileService.decode_file_id(file_id)
        expected_prefix = f"conversation-files/{tenant_id}/{conversation_id}/"
        offline_message_prefix = f"offline-message-files/{tenant_id}/"
        if not (key.startswith(expected_prefix) or key.startswith(offline_message_prefix)):
            raise ValidationError("File does not belong to conversation")
        message = await MessageRepository.get_file_message_by_file_id(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            file_id=file_id,
        )
        if message and getattr(message, "is_recalled", False):
            raise NotFoundError("File not found")
        return key

    @staticmethod
    async def _issue_temporary_url(
        key: str,
        *,
        download_name: str | None = None,
        download: bool = False,
        image_process: str | None = None,
    ) -> dict:
        """Create a short-lived object-storage URL (no DB session required)."""
        storage = create_storage_client()
        url = await storage.get_temporary_url(
            key,
            expires_seconds=TEMPORARY_URL_EXPIRES_SECONDS,
            download_name=ConversationFileService._safe_download_name(download_name or "download") if download else None,
            image_process=ConversationFileService._safe_image_process(image_process, download),
        )
        return {"url": url, "expires_seconds": TEMPORARY_URL_EXPIRES_SECONDS}

    @staticmethod
    async def get_temporary_url_for_visitor_session_managed(
        conversation_public_id: str,
        visitor_context: dict,
        file_id: str,
        download_name: str | None = None,
        download: bool = False,
        image_process: str | None = None,
    ) -> dict:
        """Create a short-lived URL without holding a DB session during object storage I/O."""
        from app.services.conversation_service import ConversationService

        async with AsyncSessionLocal() as db:
            conversation = await ConversationService.get_conversation_for_visitor_session(
                db,
                conversation_public_id=conversation_public_id,
                tenant_id=visitor_context["tenant_id"],
                channel_id=visitor_context["channel_id"],
                visitor_external_id=visitor_context["visitor_external_id"],
            )
            key = await ConversationFileService._resolve_accessible_file_key(
                db,
                tenant_id=conversation.tenant_id,
                conversation_id=conversation.id,
                file_id=file_id,
            )

        return await ConversationFileService._issue_temporary_url(
            key,
            download_name=download_name,
            download=download,
            image_process=image_process,
        )

    @staticmethod
    async def get_temporary_url_for_agent_managed(
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        file_id: str,
        download_name: str | None = None,
        download: bool = False,
        image_process: str | None = None,
        principal: EffectivePrincipal | None = None,
    ) -> dict:
        """Create a short-lived agent URL without holding a DB session during storage I/O."""
        async with AsyncSessionLocal() as db:
            conversation = await ConversationFileService._get_conversation_for_agent(
                db,
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                agent_id=agent_id,
                principal=principal,
                action="view",
            )
            key = await ConversationFileService._resolve_accessible_file_key(
                db,
                tenant_id=conversation.tenant_id,
                conversation_id=conversation_id,
                file_id=file_id,
            )

        return await ConversationFileService._issue_temporary_url(
            key,
            download_name=download_name,
            download=download,
            image_process=image_process,
        )
