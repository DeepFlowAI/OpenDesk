"""Persistence helpers for call satisfaction executions."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_satisfaction import CallSatisfactionExecution


class CallSatisfactionExecutionRepository:
    @staticmethod
    async def get_by_id(
        db: AsyncSession, execution_id: int, tenant_id: int
    ) -> CallSatisfactionExecution | None:
        query = select(CallSatisfactionExecution).where(
            CallSatisfactionExecution.id == execution_id,
            CallSatisfactionExecution.tenant_id == tenant_id,
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def get_by_call_record_id(
        db: AsyncSession, call_record_id: int
    ) -> CallSatisfactionExecution | None:
        query = select(CallSatisfactionExecution).where(
            CallSatisfactionExecution.call_record_id == call_record_id
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def lock_by_id(
        db: AsyncSession, execution_id: int
    ) -> CallSatisfactionExecution | None:
        query = (
            select(CallSatisfactionExecution)
            .where(CallSatisfactionExecution.id == execution_id)
            .with_for_update()
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession, data: dict, *, commit: bool = True
    ) -> CallSatisfactionExecution:
        row = CallSatisfactionExecution(**data)
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
        row: CallSatisfactionExecution,
        patch: dict,
        *,
        commit: bool = True,
    ) -> CallSatisfactionExecution:
        for key, value in patch.items():
            setattr(row, key, value)
        if commit:
            await db.commit()
            await db.refresh(row)
        else:
            await db.flush()
        return row
