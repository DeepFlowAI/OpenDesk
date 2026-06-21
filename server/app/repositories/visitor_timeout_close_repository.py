"""
Visitor timeout auto-close data access.
"""
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visitor_timeout_close import VisitorTimeoutCloseSetting, VisitorTimeoutCloseState


class VisitorTimeoutCloseSettingRepository:
    @staticmethod
    async def get_by_tenant(db: AsyncSession, tenant_id: int) -> VisitorTimeoutCloseSetting | None:
        result = await db.execute(
            select(VisitorTimeoutCloseSetting).where(VisitorTimeoutCloseSetting.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def save(
        db: AsyncSession,
        tenant_id: int,
        data: dict,
        *,
        commit: bool = True,
    ) -> VisitorTimeoutCloseSetting:
        row = await VisitorTimeoutCloseSettingRepository.get_by_tenant(db, tenant_id)
        if row:
            data = {**data, "version": row.version + 1}
            for key, value in data.items():
                setattr(row, key, value)
        else:
            row = VisitorTimeoutCloseSetting(tenant_id=tenant_id, **data)
            db.add(row)

        if commit:
            await db.commit()
            await db.refresh(row)
        else:
            await db.flush()
        return row


class VisitorTimeoutCloseStateRepository:
    @staticmethod
    async def get_by_conversation(db: AsyncSession, conversation_id: int) -> VisitorTimeoutCloseState | None:
        result = await db.execute(
            select(VisitorTimeoutCloseState).where(VisitorTimeoutCloseState.conversation_id == conversation_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_for_conversation(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        anchor_at: datetime,
        anchor_message_id: int | None,
        first_reminded_at: datetime | None,
        closed_at: datetime | None,
        next_check_at: datetime | None,
        config_version: int | None,
        commit: bool = True,
    ) -> VisitorTimeoutCloseState:
        row = await VisitorTimeoutCloseStateRepository.get_by_conversation(db, conversation_id)
        data = {
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "anchor_at": anchor_at,
            "anchor_message_id": anchor_message_id,
            "first_reminded_at": first_reminded_at,
            "closed_at": closed_at,
            "next_check_at": next_check_at,
            "config_version": config_version,
        }
        if row:
            for key, value in data.items():
                setattr(row, key, value)
        else:
            row = VisitorTimeoutCloseState(**data)
            db.add(row)

        if commit:
            await db.commit()
            await db.refresh(row)
        else:
            await db.flush()
        return row

    @staticmethod
    async def update(
        db: AsyncSession,
        row: VisitorTimeoutCloseState,
        data: dict,
        *,
        commit: bool = True,
    ) -> VisitorTimeoutCloseState:
        for key, value in data.items():
            setattr(row, key, value)
        if commit:
            await db.commit()
            await db.refresh(row)
        else:
            await db.flush()
        return row

    @staticmethod
    async def claim_due(
        db: AsyncSession,
        *,
        now: datetime,
        lease_until: datetime,
    ) -> VisitorTimeoutCloseState | None:
        due_state_id = (
            select(VisitorTimeoutCloseState.id)
            .where(
                VisitorTimeoutCloseState.next_check_at.is_not(None),
                VisitorTimeoutCloseState.next_check_at <= now,
                VisitorTimeoutCloseState.closed_at.is_(None),
            )
            .order_by(VisitorTimeoutCloseState.next_check_at.asc(), VisitorTimeoutCloseState.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        result = await db.execute(
            update(VisitorTimeoutCloseState)
            .where(VisitorTimeoutCloseState.id == due_state_id)
            .values(next_check_at=lease_until)
            .returning(VisitorTimeoutCloseState)
        )
        row = result.scalar_one_or_none()
        await db.commit()
        return row
