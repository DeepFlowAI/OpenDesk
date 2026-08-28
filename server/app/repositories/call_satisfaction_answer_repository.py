"""Persistence helpers for mapped call satisfaction answers."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_satisfaction import CallSatisfactionAnswer


class CallSatisfactionAnswerRepository:
    @staticmethod
    async def get_by_question(
        db: AsyncSession, execution_id: int, question_node_id: str
    ) -> CallSatisfactionAnswer | None:
        query = select(CallSatisfactionAnswer).where(
            CallSatisfactionAnswer.execution_id == execution_id,
            CallSatisfactionAnswer.question_node_id == question_node_id,
        )
        return (await db.execute(query)).scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession, data: dict, *, commit: bool = True
    ) -> CallSatisfactionAnswer:
        row = CallSatisfactionAnswer(**data)
        db.add(row)
        if commit:
            await db.commit()
            await db.refresh(row)
        else:
            await db.flush()
        return row

    @staticmethod
    async def list_for_execution(
        db: AsyncSession, execution_id: int
    ) -> list[CallSatisfactionAnswer]:
        query = (
            select(CallSatisfactionAnswer)
            .where(CallSatisfactionAnswer.execution_id == execution_id)
            .order_by(
                CallSatisfactionAnswer.question_order.asc(),
                CallSatisfactionAnswer.id.asc(),
            )
        )
        return list((await db.execute(query)).scalars().all())
