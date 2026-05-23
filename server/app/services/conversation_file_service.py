"""
Conversation file service.
"""
import base64
import re
import uuid
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.storage import create_storage_client
from app.repositories.conversation_repository import ConversationRepository

MAX_CONVERSATION_FILE_SIZE = 100 * 1024 * 1024
TEMPORARY_URL_EXPIRES_SECONDS = 300
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
    ):
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation:
            raise NotFoundError("Conversation not found")
        if conversation.tenant_id != tenant_id:
            raise ValidationError("Conversation does not match tenant")
        if conversation.agent_id != agent_id:
            raise ValidationError("Conversation does not match agent")
        return conversation

    @staticmethod
    async def _upload_file(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        file: UploadFile,
    ) -> dict:
        raw_name = file.filename or "upload"
        ext = ConversationFileService._extension(raw_name)
        if ext in BLOCKED_CONVERSATION_FILE_EXTENSIONS:
            raise ValidationError(f"File type .{ext} is not allowed for security reasons")

        data = await file.read()
        if not data:
            raise ValidationError("File is empty")
        if len(data) > MAX_CONVERSATION_FILE_SIZE:
            raise ValidationError("File size exceeds 100MB limit")

        safe_ext = ext if ext and ext not in BLOCKED_CONVERSATION_FILE_EXTENSIONS else "bin"
        date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
        key = f"conversation-files/{tenant_id}/{conversation_id}/{date_prefix}/{uuid.uuid4().hex}.{safe_ext}"

        storage = create_storage_client()
        content_type = file.content_type or "application/octet-stream"
        ConversationFileService._validate_magic_number(content_type, data)
        await storage.upload(key, data, content_type=content_type)

        file_id = ConversationFileService.encode_file_id(key)
        access_url = await ConversationFileService.get_temporary_url(
            db,
            conversation_id=conversation_id,
            file_id=file_id,
            download_name=raw_name,
            download=False,
        )
        return {
            "schema_version": 1,
            "file_id": file_id,
            "name": raw_name,
            "size": len(data),
            "mime_type": content_type,
            "access_url": access_url["url"],
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
            db,
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
            db,
            conversation_id=conversation.id,
            tenant_id=conversation.tenant_id,
            file=file,
        )

    @staticmethod
    async def upload_agent_file(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        file: UploadFile,
    ) -> dict:
        """Upload an agent conversation file and return structured metadata."""
        await ConversationFileService._get_conversation_for_agent(
            db,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
        )

        return await ConversationFileService._upload_file(
            db,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            file=file,
        )

    @staticmethod
    async def get_temporary_url(
        db: AsyncSession,
        conversation_id: int,
        file_id: str,
        download_name: str | None = None,
        download: bool = False,
    ) -> dict:
        """Create a short-lived URL for a conversation file."""
        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation:
            raise NotFoundError("Conversation not found")

        key = ConversationFileService.decode_file_id(file_id)
        expected_prefix = f"conversation-files/{conversation.tenant_id}/{conversation_id}/"
        if not key.startswith(expected_prefix):
            raise ValidationError("File does not belong to conversation")

        storage = create_storage_client()
        url = await storage.get_temporary_url(
            key,
            expires_seconds=TEMPORARY_URL_EXPIRES_SECONDS,
            download_name=ConversationFileService._safe_download_name(download_name or "download") if download else None,
        )
        return {"url": url, "expires_seconds": TEMPORARY_URL_EXPIRES_SECONDS}

    @staticmethod
    async def get_temporary_url_for_visitor_session(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
        file_id: str,
        download_name: str | None = None,
        download: bool = False,
    ) -> dict:
        """Create a short-lived URL for a token-bound visitor conversation file."""
        from app.services.conversation_service import ConversationService

        conversation = await ConversationService.get_conversation_for_visitor_session(
            db,
            conversation_public_id=conversation_public_id,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
        )
        return await ConversationFileService.get_temporary_url(
            db,
            conversation_id=conversation.id,
            file_id=file_id,
            download_name=download_name,
            download=download,
        )

    @staticmethod
    async def get_temporary_url_for_agent(
        db: AsyncSession,
        conversation_id: int,
        tenant_id: int,
        agent_id: int,
        file_id: str,
        download_name: str | None = None,
        download: bool = False,
    ) -> dict:
        """Create a short-lived URL for an agent-accessible conversation file."""
        await ConversationFileService._get_conversation_for_agent(
            db,
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
        )
        return await ConversationFileService.get_temporary_url(
            db,
            conversation_id=conversation_id,
            file_id=file_id,
            download_name=download_name,
            download=download,
        )
