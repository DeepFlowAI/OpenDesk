"""
Queue no-show cancel setting data access.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queue_no_show_setting import QueueNoShowSetting


class QueueNoShowSettingRepository:
    @staticmethod
    async def get_by_tenant(db: AsyncSession, tenant_id: int) -> QueueNoShowSetting | None:
        result = await db.execute(
            select(QueueNoShowSetting).where(QueueNoShowSetting.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        data: dict,
        *,
        commit: bool = True,
    ) -> QueueNoShowSetting:
        row = await QueueNoShowSettingRepository.get_by_tenant(db, tenant_id)
        if row:
            for key, value in data.items():
                setattr(row, key, value)
        else:
            row = QueueNoShowSetting(tenant_id=tenant_id, **data)
            db.add(row)

        if commit:
            await db.commit()
            await db.refresh(row)
        else:
            await db.flush()
        return row
