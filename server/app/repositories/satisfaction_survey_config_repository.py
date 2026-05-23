"""
Satisfaction survey config repository.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.satisfaction_survey_config import (
    SatisfactionSurveyConfig,
    SatisfactionSurveyConfigVersion,
)


class SatisfactionSurveyConfigRepository:
    @staticmethod
    async def get_current(db: AsyncSession, tenant_id: int) -> SatisfactionSurveyConfig | None:
        q = select(SatisfactionSurveyConfig).where(SatisfactionSurveyConfig.tenant_id == tenant_id)
        return (await db.execute(q)).scalar_one_or_none()

    @staticmethod
    async def max_version(db: AsyncSession, tenant_id: int) -> int:
        q = select(func.max(SatisfactionSurveyConfigVersion.version)).where(
            SatisfactionSurveyConfigVersion.tenant_id == tenant_id
        )
        value = (await db.execute(q)).scalar_one()
        return int(value or 0)

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        config_data: dict,
        version_data: dict,
        *,
        bump_version: bool,
    ) -> tuple[SatisfactionSurveyConfig, SatisfactionSurveyConfigVersion]:
        current = await SatisfactionSurveyConfigRepository.get_current(db, tenant_id)
        if current:
            for key, value in config_data.items():
                setattr(current, key, value)
        else:
            current = SatisfactionSurveyConfig(tenant_id=tenant_id, **config_data)
            db.add(current)
        await db.flush()

        should_create_version = bump_version or current.current_version is None
        if should_create_version:
            version_number = await SatisfactionSurveyConfigRepository.max_version(db, tenant_id) + 1
            current.current_version = version_number
            version = SatisfactionSurveyConfigVersion(
                tenant_id=tenant_id,
                config_id=current.id,
                version=version_number,
                **version_data,
            )
            db.add(version)
        else:
            version = await SatisfactionSurveyConfigRepository.get_version(
                db,
                tenant_id,
                current.current_version,
            )
            if not version:
                version_number = await SatisfactionSurveyConfigRepository.max_version(db, tenant_id) + 1
                current.current_version = version_number
                version = SatisfactionSurveyConfigVersion(
                    tenant_id=tenant_id,
                    config_id=current.id,
                    version=version_number,
                    **version_data,
                )
                db.add(version)
            else:
                for key, value in version_data.items():
                    setattr(version, key, value)

        await db.commit()
        await db.refresh(current)
        await db.refresh(version)
        return current, version

    @staticmethod
    async def list_versions(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[SatisfactionSurveyConfigVersion], int]:
        count_q = (
            select(func.count())
            .select_from(SatisfactionSurveyConfigVersion)
            .where(SatisfactionSurveyConfigVersion.tenant_id == tenant_id)
        )
        total = (await db.execute(count_q)).scalar_one()

        offset = (page - 1) * per_page
        q = (
            select(SatisfactionSurveyConfigVersion)
            .where(SatisfactionSurveyConfigVersion.tenant_id == tenant_id)
            .order_by(SatisfactionSurveyConfigVersion.version.desc())
            .offset(offset)
            .limit(per_page)
        )
        rows = list((await db.execute(q)).scalars().all())
        return rows, total

    @staticmethod
    async def get_version(
        db: AsyncSession,
        tenant_id: int,
        version: int,
    ) -> SatisfactionSurveyConfigVersion | None:
        q = select(SatisfactionSurveyConfigVersion).where(
            SatisfactionSurveyConfigVersion.tenant_id == tenant_id,
            SatisfactionSurveyConfigVersion.version == version,
        )
        return (await db.execute(q)).scalar_one_or_none()
