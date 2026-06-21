"""
AudioAsset repository
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio_asset import AudioAsset


class AudioAssetRepository:

    @staticmethod
    async def get_by_id(
        db: AsyncSession, asset_id: int, tenant_id: int, include_deleted: bool = False
    ) -> AudioAsset | None:
        q = select(AudioAsset).where(
            AudioAsset.id == asset_id, AudioAsset.tenant_id == tenant_id
        )
        if not include_deleted:
            q = q.where(AudioAsset.deleted_at.is_(None))
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def exists_ids(db: AsyncSession, ids: list[int], tenant_id: int) -> set[int]:
        """Return the subset of asset ids that exist (not soft-deleted) for the tenant."""

        if not ids:
            return set()
        q = select(AudioAsset.id).where(
            AudioAsset.id.in_(ids),
            AudioAsset.tenant_id == tenant_id,
            AudioAsset.deleted_at.is_(None),
        )
        rows = (await db.execute(q)).scalars().all()
        return set(rows)

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> AudioAsset:
        row = AudioAsset(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def soft_delete(db: AsyncSession, row: AudioAsset) -> None:
        row.deleted_at = datetime.now(timezone.utc)
        await db.commit()
