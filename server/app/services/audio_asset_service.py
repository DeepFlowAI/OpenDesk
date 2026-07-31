"""
Audio asset service — upload mp3/wav prompts and issue temporary preview URLs.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.libs.storage import create_storage_client
from app.repositories.audio_asset_repository import AudioAssetRepository
from app.services.audit_actor_service import AuditActorService


ALLOWED_AUDIO_MIME = {
    "audio/mpeg",       # mp3
    "audio/mp3",        # some browsers
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/vnd.wave",
}

MAX_AUDIO_SIZE = 10 * 1024 * 1024  # 10MB

_EXT_BY_MIME = {
    "audio/mpeg": "mp3", "audio/mp3": "mp3",
    "audio/wav": "wav", "audio/wave": "wav",
    "audio/x-wav": "wav", "audio/vnd.wave": "wav",
}

# MIME stored after magic-byte sniff (browser Content-Type is untrusted).
_MIME_BY_KIND = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
}


def detect_playable_audio_kind(data: bytes) -> str | None:
    """Return ``mp3`` / ``wav`` when bytes match a FlowKit-playable container."""

    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if len(data) >= 3 and data[0:3] == b"ID3":
        return "mp3"
    # MPEG frame sync without ID3 tag
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return "mp3"
    return None


def _describe_unsupported_audio(data: bytes) -> str:
    """Human-readable hint when magic bytes are not mp3/wav."""

    if len(data) >= 12 and data[4:8] == b"ftyp":
        return (
            "文件实际是 M4A/AAC 格式，不是真正的 MP3/WAV。"
            "请导出为 MP3 或 WAV 后再上传"
        )
    return "仅支持真正的 MP3 或 WAV 文件，请检查格式后重新上传"


class AudioAssetService:

    @staticmethod
    async def upload(
        db: AsyncSession,
        tenant_id: int,
        actor: dict,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> dict:
        if not data:
            raise ValidationError("文件为空")
        if len(data) > MAX_AUDIO_SIZE:
            raise ValidationError("音频文件不能超过 10MB")

        # Trust file bytes over the browser MIME: phones often rename .m4a to .mp3.
        kind = detect_playable_audio_kind(data)
        if kind is None:
            raise ValidationError(_describe_unsupported_audio(data))

        resolved_mime = _MIME_BY_KIND[kind]
        if content_type and content_type not in ALLOWED_AUDIO_MIME:
            # Still allow when bytes are valid playable audio even if the
            # declared type is odd (e.g. application/octet-stream).
            pass

        ext = kind
        storage_key = f"voice-flow/audio/{tenant_id}/{uuid.uuid4().hex}.{ext}"
        storage = create_storage_client()
        await storage.upload(storage_key, data, content_type=resolved_mime)

        row = await AudioAssetRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "name": filename or f"audio.{ext}",
                "storage_provider": settings.STORAGE_PROVIDER,
                "storage_key": storage_key,
                "mime_type": resolved_mime,
                "size_bytes": len(data),
                "duration_ms": None,
                "created_by_actor_type": actor.get("actor_type"),
                "created_by_actor_id": actor.get("actor_id"),
                "created_by_actor_name": actor.get("actor_name"),
            },
        )

        preview_url = await storage.get_temporary_url(storage_key, expires_seconds=300)
        return await AudioAssetService._to_response(row, preview_url)

    @staticmethod
    async def upload_managed(
        tenant_id: int,
        user_id: int | None,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> dict:
        """Upload audio and persist metadata without holding a pooled DB session
        across object-storage I/O.
        """
        if not data:
            raise ValidationError("文件为空")
        if len(data) > MAX_AUDIO_SIZE:
            raise ValidationError("音频文件不能超过 10MB")

        kind = detect_playable_audio_kind(data)
        if kind is None:
            raise ValidationError(_describe_unsupported_audio(data))

        resolved_mime = _MIME_BY_KIND[kind]
        storage_key = f"voice-flow/audio/{tenant_id}/{uuid.uuid4().hex}.{kind}"
        storage = create_storage_client()
        await storage.upload(storage_key, data, content_type=resolved_mime)

        async with AsyncSessionLocal() as db:
            actor = await AuditActorService.resolve_current_employee(
                db, tenant_id, user_id
            )
            row = await AudioAssetRepository.create(
                db,
                {
                    "tenant_id": tenant_id,
                    "name": filename or f"audio.{kind}",
                    "storage_provider": settings.STORAGE_PROVIDER,
                    "storage_key": storage_key,
                    "mime_type": resolved_mime,
                    "size_bytes": len(data),
                    "duration_ms": None,
                    "created_by_actor_type": actor.get("actor_type"),
                    "created_by_actor_id": actor.get("actor_id"),
                    "created_by_actor_name": actor.get("actor_name"),
                },
            )
            payload = await AudioAssetService._to_response(row, None)

        preview_url = await storage.get_temporary_url(storage_key, expires_seconds=300)
        payload["preview_url"] = preview_url
        return payload

    @staticmethod
    async def get(db: AsyncSession, asset_id: int, tenant_id: int) -> dict:
        row = await AudioAssetRepository.get_by_id(db, asset_id, tenant_id)
        if not row:
            raise NotFoundError("Audio asset not found")
        storage = create_storage_client()
        preview_url = await storage.get_temporary_url(row.storage_key, expires_seconds=300)
        return await AudioAssetService._to_response(row, preview_url)

    @staticmethod
    async def get_managed(asset_id: int, tenant_id: int) -> dict:
        """Load an asset and issue a preview URL without holding a pooled DB
        session across object-storage I/O.
        """
        async with AsyncSessionLocal() as db:
            row = await AudioAssetRepository.get_by_id(db, asset_id, tenant_id)
            if not row:
                raise NotFoundError("Audio asset not found")
            storage_key = row.storage_key
            payload = await AudioAssetService._to_response(row, None)

        storage = create_storage_client()
        preview_url = await storage.get_temporary_url(storage_key, expires_seconds=300)
        payload["preview_url"] = preview_url
        return payload

    @staticmethod
    async def delete(db: AsyncSession, asset_id: int, tenant_id: int) -> None:
        row = await AudioAssetRepository.get_by_id(db, asset_id, tenant_id)
        if not row:
            raise NotFoundError("Audio asset not found")
        await AudioAssetRepository.soft_delete(db, row)

    @staticmethod
    async def _to_response(row, preview_url: str | None) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "mime_type": row.mime_type,
            "size_bytes": row.size_bytes,
            "duration_ms": row.duration_ms,
            "preview_url": preview_url,
            "created_at": row.created_at,
        }
