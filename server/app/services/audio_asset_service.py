"""
Audio asset service — upload mp3/wav prompts and issue temporary preview URLs.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.libs.storage import create_storage_client
from app.repositories.audio_asset_repository import AudioAssetRepository


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
        if content_type not in ALLOWED_AUDIO_MIME:
            raise ValidationError(f"Unsupported audio type: {content_type}")
        if len(data) > MAX_AUDIO_SIZE:
            raise ValidationError("Audio file exceeds 10MB limit")
        if not data:
            raise ValidationError("Empty file")

        ext = _EXT_BY_MIME.get(content_type, "bin")
        storage_key = f"voice-flow/audio/{tenant_id}/{uuid.uuid4().hex}.{ext}"
        storage = create_storage_client()
        await storage.upload(storage_key, data, content_type=content_type)

        row = await AudioAssetRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "name": filename or f"audio.{ext}",
                "storage_provider": settings.STORAGE_PROVIDER,
                "storage_key": storage_key,
                "mime_type": content_type,
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
    async def get(db: AsyncSession, asset_id: int, tenant_id: int) -> dict:
        row = await AudioAssetRepository.get_by_id(db, asset_id, tenant_id)
        if not row:
            raise NotFoundError("Audio asset not found")
        storage = create_storage_client()
        preview_url = await storage.get_temporary_url(row.storage_key, expires_seconds=300)
        return await AudioAssetService._to_response(row, preview_url)

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
