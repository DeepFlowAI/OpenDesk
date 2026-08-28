"""Persistence helpers for embedded call integrations."""
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedded_call_integration import EmbeddedCallIntegration


class EmbeddedCallIntegrationRepository:
    @staticmethod
    async def list_for_tenant(
        db: AsyncSession, tenant_id: int
    ) -> list[EmbeddedCallIntegration]:
        result = await db.execute(
            select(EmbeddedCallIntegration)
            .where(EmbeddedCallIntegration.tenant_id == tenant_id)
            .order_by(desc(EmbeddedCallIntegration.updated_at), desc(EmbeddedCallIntegration.id))
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_public_id(
        db: AsyncSession, tenant_id: int, public_id: UUID | str
    ) -> EmbeddedCallIntegration | None:
        result = await db.execute(
            select(EmbeddedCallIntegration).where(
                EmbeddedCallIntegration.tenant_id == tenant_id,
                EmbeddedCallIntegration.public_id == public_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_integration_key(
        db: AsyncSession, integration_key: str
    ) -> EmbeddedCallIntegration | None:
        result = await db.execute(
            select(EmbeddedCallIntegration).where(
                EmbeddedCallIntegration.integration_key == integration_key
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        db: AsyncSession, integration_id: int, tenant_id: int
    ) -> EmbeddedCallIntegration | None:
        result = await db.execute(
            select(EmbeddedCallIntegration).where(
                EmbeddedCallIntegration.id == integration_id,
                EmbeddedCallIntegration.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession, data: dict
    ) -> EmbeddedCallIntegration:
        row = EmbeddedCallIntegration(**data)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update(
        db: AsyncSession, row: EmbeddedCallIntegration, patch: dict
    ) -> EmbeddedCallIntegration:
        for key, value in patch.items():
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def delete(db: AsyncSession, row: EmbeddedCallIntegration) -> None:
        await db.delete(row)
        await db.commit()
