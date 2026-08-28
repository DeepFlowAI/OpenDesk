"""
SMS repositories: signatures, templates, tenant grants and send records.
"""
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_record import CallRecord
from app.models.employee import Employee
from app.models.sms import (
    SMS_SEND_STATUS_DELIVERED,
    SMS_SEND_STATUS_FAILED,
    SMS_SEND_STATUS_PENDING,
    SMS_SEND_STATUS_SUBMITTED,
    SMS_STATUS_ENABLED,
    SmsSendRecord,
    SmsSignature,
    SmsTemplate,
    SmsTemplateGrant,
)


class SmsSignatureRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, signature_id: int) -> SmsSignature | None:
        return await db.get(SmsSignature, signature_id)

    @staticmethod
    async def get_enabled_by_provider_sign(
        db: AsyncSession, provider: str, provider_sign_name: str
    ) -> SmsSignature | None:
        result = await db.execute(
            select(SmsSignature).where(
                SmsSignature.provider == provider,
                SmsSignature.provider_sign_name == provider_sign_name,
                SmsSignature.status == "enabled",
            )
        )
        return result.scalars().first()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        *,
        page: int = 1,
        per_page: int = 20,
        q: str | None = None,
        status: str | None = None,
    ) -> tuple[list[SmsSignature], int]:
        stmt = select(SmsSignature)
        count_stmt = select(func.count()).select_from(SmsSignature)
        if q:
            condition = SmsSignature.name.ilike(f"%{q}%")
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            stmt = stmt.where(SmsSignature.status == status)
            count_stmt = count_stmt.where(SmsSignature.status == status)
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            stmt.order_by(SmsSignature.updated_at.desc()).offset((page - 1) * per_page).limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SmsSignature:
        item = SmsSignature(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: SmsSignature, data: dict) -> SmsSignature:
        for key, value in data.items():
            setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item


class SmsTemplateRepository:

    @staticmethod
    async def get_by_id(db: AsyncSession, template_id: int) -> SmsTemplate | None:
        return await db.get(SmsTemplate, template_id)

    @staticmethod
    async def get_by_ids(db: AsyncSession, template_ids: list[int]) -> list[SmsTemplate]:
        if not template_ids:
            return []
        result = await db.execute(select(SmsTemplate).where(SmsTemplate.id.in_(template_ids)))
        return list(result.scalars().all())

    @staticmethod
    async def get_by_provider_code(
        db: AsyncSession, provider: str, provider_template_code: str
    ) -> SmsTemplate | None:
        result = await db.execute(
            select(SmsTemplate).where(
                SmsTemplate.provider == provider,
                SmsTemplate.provider_template_code == provider_template_code,
            )
        )
        return result.scalars().first()

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        *,
        page: int = 1,
        per_page: int = 20,
        q: str | None = None,
        status: str | None = None,
        type_: str | None = None,
    ) -> tuple[list[SmsTemplate], int]:
        stmt = select(SmsTemplate)
        count_stmt = select(func.count()).select_from(SmsTemplate)
        conditions = []
        if q:
            conditions.append(SmsTemplate.name.ilike(f"%{q}%"))
        if status:
            conditions.append(SmsTemplate.status == status)
        if type_:
            conditions.append(SmsTemplate.type == type_)
        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            stmt.order_by(SmsTemplate.updated_at.desc()).offset((page - 1) * per_page).limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SmsTemplate:
        item = SmsTemplate(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update(db: AsyncSession, item: SmsTemplate, data: dict) -> SmsTemplate:
        for key, value in data.items():
            setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item


class SmsTemplateGrantRepository:

    @staticmethod
    async def list_template_ids_for_tenant(db: AsyncSession, tenant_id: int) -> list[int]:
        result = await db.execute(
            select(SmsTemplateGrant.template_id).where(SmsTemplateGrant.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_grants_for_tenant(db: AsyncSession, tenant_id: int) -> list[SmsTemplateGrant]:
        result = await db.execute(
            select(SmsTemplateGrant)
            .where(SmsTemplateGrant.tenant_id == tenant_id)
            .order_by(SmsTemplateGrant.updated_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, tenant_id: int, template_id: int) -> SmsTemplateGrant:
        item = SmsTemplateGrant(tenant_id=tenant_id, template_id=template_id)
        db.add(item)
        await db.flush()
        return item

    @staticmethod
    async def delete(db: AsyncSession, tenant_id: int, template_id: int) -> bool:
        result = await db.execute(
            select(SmsTemplateGrant).where(
                SmsTemplateGrant.tenant_id == tenant_id,
                SmsTemplateGrant.template_id == template_id,
            )
        )
        item = result.scalars().first()
        if item is None:
            return False
        await db.delete(item)
        return True

    @staticmethod
    async def list_granted_detail_for_tenant_paginated(
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        q: str | None = None,
        only_enabled: bool = False,
    ) -> tuple[list[tuple[SmsTemplateGrant, SmsTemplate, SmsSignature]], int]:
        """Grants joined with template and signature for tenant-side views."""
        stmt = (
            select(SmsTemplateGrant, SmsTemplate, SmsSignature)
            .join(SmsTemplate, SmsTemplate.id == SmsTemplateGrant.template_id)
            .join(SmsSignature, SmsSignature.id == SmsTemplate.signature_id)
            .where(SmsTemplateGrant.tenant_id == tenant_id)
        )
        count_stmt = (
            select(func.count())
            .select_from(SmsTemplateGrant)
            .join(SmsTemplate, SmsTemplate.id == SmsTemplateGrant.template_id)
            .where(SmsTemplateGrant.tenant_id == tenant_id)
        )
        if q:
            condition = SmsTemplate.name.ilike(f"%{q}%")
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if only_enabled:
            stmt = stmt.where(SmsTemplate.status == SMS_STATUS_ENABLED)
            count_stmt = count_stmt.where(SmsTemplate.status == SMS_STATUS_ENABLED)
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            stmt.order_by(SmsTemplateGrant.updated_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return list(result.all()), total

    @staticmethod
    async def get_granted_template(
        db: AsyncSession, *, tenant_id: int, template_id: int
    ) -> tuple[SmsTemplateGrant, SmsTemplate, SmsSignature] | None:
        result = await db.execute(
            select(SmsTemplateGrant, SmsTemplate, SmsSignature)
            .join(SmsTemplate, SmsTemplate.id == SmsTemplateGrant.template_id)
            .join(SmsSignature, SmsSignature.id == SmsTemplate.signature_id)
            .where(
                SmsTemplateGrant.tenant_id == tenant_id,
                SmsTemplateGrant.template_id == template_id,
            )
        )
        return result.first()

    @staticmethod
    async def commit(db: AsyncSession) -> None:
        await db.commit()


class SmsSendRecordRepository:
    """Persistence for single-send records. Never reuses ORM objects across sessions."""

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> SmsSendRecord:
        item = SmsSendRecord(**data)
        db.add(item)
        await db.flush()
        await db.refresh(item)
        return item

    @staticmethod
    async def get_by_client_request_id(
        db: AsyncSession, *, tenant_id: int, client_request_id: str
    ) -> SmsSendRecord | None:
        result = await db.execute(
            select(SmsSendRecord).where(
                SmsSendRecord.tenant_id == tenant_id,
                SmsSendRecord.client_request_id == client_request_id,
            )
        )
        return result.scalars().first()

    @staticmethod
    async def update_send_result(
        db: AsyncSession,
        *,
        record_id: int,
        status: str,
        biz_id: str | None = None,
        fail_reason: str | None = None,
    ) -> None:
        values: dict = {"status": status}
        if biz_id is not None:
            values["provider_biz_id"] = biz_id
        if fail_reason is not None:
            values["fail_reason"] = fail_reason
        await db.execute(
            update(SmsSendRecord).where(SmsSendRecord.id == record_id).values(**values)
        )

    @staticmethod
    async def update_delivery_by_biz_id(
        db: AsyncSession,
        *,
        provider: str,
        biz_id: str,
        delivered: bool,
        fail_reason: str | None = None,
    ) -> int:
        """Advance a record to its final state from a delivery receipt.

        Only ``pending``/``submitted`` records are touched so duplicate or
        out-of-order receipts never roll back a terminal state.
        """
        values: dict = {
            "status": SMS_SEND_STATUS_DELIVERED if delivered else SMS_SEND_STATUS_FAILED
        }
        if not delivered and fail_reason:
            values["fail_reason"] = fail_reason
        result = await db.execute(
            update(SmsSendRecord)
            .where(
                SmsSendRecord.provider == provider,
                SmsSendRecord.provider_biz_id == biz_id,
                SmsSendRecord.status.in_([SMS_SEND_STATUS_PENDING, SMS_SEND_STATUS_SUBMITTED]),
            )
            .values(**values)
        )
        return result.rowcount or 0

    _detail_columns = (
        SmsSendRecord,
        Employee.name.label("employee_name"),
        CallRecord.call_id.label("call_id"),
        CallRecord.public_id.label("call_record_public_id"),
    )

    @staticmethod
    def _detail_stmt():
        return (
            select(*SmsSendRecordRepository._detail_columns)
            .outerjoin(Employee, Employee.id == SmsSendRecord.employee_id)
            .outerjoin(CallRecord, CallRecord.id == SmsSendRecord.call_record_id)
        )

    @staticmethod
    async def list_for_tenant_paginated(
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        phone: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> tuple[list[tuple[SmsSendRecord, str, str | None, object | None]], int]:
        stmt = SmsSendRecordRepository._detail_stmt().where(SmsSendRecord.tenant_id == tenant_id)
        count_stmt = (
            select(func.count())
            .select_from(SmsSendRecord)
            .where(SmsSendRecord.tenant_id == tenant_id)
        )
        if phone:
            condition = SmsSendRecord.phone.ilike(f"%{phone}%")
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        if status:
            stmt = stmt.where(SmsSendRecord.status == status)
            count_stmt = count_stmt.where(SmsSendRecord.status == status)
        if source:
            stmt = stmt.where(SmsSendRecord.source == source)
            count_stmt = count_stmt.where(SmsSendRecord.source == source)
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            stmt.order_by(SmsSendRecord.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        return [tuple(row) for row in result.all()], total

    @staticmethod
    async def get_detail_for_tenant(
        db: AsyncSession, *, tenant_id: int, record_id: int
    ) -> tuple[SmsSendRecord, str, str | None, object | None] | None:
        result = await db.execute(
            SmsSendRecordRepository._detail_stmt().where(
                SmsSendRecord.tenant_id == tenant_id,
                SmsSendRecord.id == record_id,
            )
        )
        row = result.first()
        return tuple(row) if row is not None else None
