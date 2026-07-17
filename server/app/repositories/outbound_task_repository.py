"""
Data access for manual outbound tasks.
"""
from datetime import datetime

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.outbound_task import (
    OutboundCallRecord,
    OutboundTask,
    OutboundTaskTarget,
    OutboundTaskTemplate,
)


def _paginate_statement(stmt: Select, page: int, per_page: int) -> Select:
    return stmt.offset((page - 1) * per_page).limit(per_page)


class OutboundTaskRepository:
    @staticmethod
    async def list_templates(
        db: AsyncSession,
        tenant_id: int,
        page: int,
        per_page: int,
        q: str | None = None,
    ) -> tuple[list[OutboundTaskTemplate], int]:
        stmt = select(OutboundTaskTemplate).where(OutboundTaskTemplate.tenant_id == tenant_id)
        count_stmt = select(func.count()).select_from(OutboundTaskTemplate).where(OutboundTaskTemplate.tenant_id == tenant_id)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(OutboundTaskTemplate.name.ilike(like))
            count_stmt = count_stmt.where(OutboundTaskTemplate.name.ilike(like))
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            _paginate_statement(stmt.order_by(OutboundTaskTemplate.updated_at.desc()), page, per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_template(db: AsyncSession, template_id: int) -> OutboundTaskTemplate | None:
        return await db.get(OutboundTaskTemplate, template_id)

    @staticmethod
    async def create_template(db: AsyncSession, data: dict) -> OutboundTaskTemplate:
        item = OutboundTaskTemplate(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update_template(db: AsyncSession, item: OutboundTaskTemplate, data: dict) -> OutboundTaskTemplate:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete_template(db: AsyncSession, item: OutboundTaskTemplate) -> None:
        await db.delete(item)
        await db.commit()

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        tenant_id: int,
        page: int,
        per_page: int,
        q: str | None = None,
        status: str | None = None,
        template_id: int | None = None,
        creator_id: int | None = None,
    ) -> tuple[list[OutboundTask], int]:
        filters = [OutboundTask.tenant_id == tenant_id]
        if q:
            filters.append(OutboundTask.name.ilike(f"%{q}%"))
        if status:
            filters.append(OutboundTask.status == status)
        if template_id:
            filters.append(OutboundTask.template_id == template_id)
        if creator_id:
            filters.append(OutboundTask.created_by_id == creator_id)

        stmt = select(OutboundTask).where(*filters)
        count_stmt = select(func.count()).select_from(OutboundTask).where(*filters)
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            _paginate_statement(stmt.order_by(OutboundTask.updated_at.desc()), page, per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_task(db: AsyncSession, task_id: int) -> OutboundTask | None:
        return await db.get(OutboundTask, task_id)

    @staticmethod
    async def create_task(db: AsyncSession, data: dict) -> OutboundTask:
        item = OutboundTask(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update_task(db: AsyncSession, item: OutboundTask, data: dict) -> OutboundTask:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def count_targets(db: AsyncSession, tenant_id: int, task_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(OutboundTaskTarget).where(
                OutboundTaskTarget.tenant_id == tenant_id,
                OutboundTaskTarget.task_id == task_id,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def task_stats(db: AsyncSession, tenant_id: int, task_ids: list[int]) -> dict[int, dict]:
        if not task_ids:
            return {}
        result = await db.execute(
            select(
                OutboundTaskTarget.task_id,
                func.count(OutboundTaskTarget.id).label("total_targets"),
                func.count().filter(OutboundTaskTarget.status.in_(["pending", "redial"])).label("pending_targets"),
                func.count().filter(OutboundTaskTarget.status == "completed").label("completed_targets"),
                func.coalesce(func.sum(OutboundTaskTarget.call_count), 0).label("call_count"),
                func.coalesce(func.sum(OutboundTaskTarget.answered_count), 0).label("answered_count"),
            )
            .where(OutboundTaskTarget.tenant_id == tenant_id, OutboundTaskTarget.task_id.in_(task_ids))
            .group_by(OutboundTaskTarget.task_id)
        )
        return {
            row.task_id: {
                "total_targets": row.total_targets,
                "pending_targets": row.pending_targets,
                "completed_targets": row.completed_targets,
                "call_count": row.call_count,
                "answered_count": row.answered_count,
            }
            for row in result
        }

    @staticmethod
    async def list_targets(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        page: int,
        per_page: int,
        q: str | None = None,
        status: str | None = None,
        assignee_id: int | None = None,
    ) -> tuple[list[OutboundTaskTarget], int]:
        filters = [OutboundTaskTarget.tenant_id == tenant_id, OutboundTaskTarget.task_id == task_id]
        if q:
            filters.append(OutboundTaskTarget.phone_number.ilike(f"%{q}%"))
        if status:
            filters.append(OutboundTaskTarget.status == status)
        if assignee_id:
            filters.append(OutboundTaskTarget.assignee_id == assignee_id)

        stmt = select(OutboundTaskTarget).where(*filters)
        count_stmt = select(func.count()).select_from(OutboundTaskTarget).where(*filters)
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            _paginate_statement(stmt.order_by(OutboundTaskTarget.updated_at.desc()), page, per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def list_my_targets(
        db: AsyncSession,
        tenant_id: int,
        assignee_id: int,
        page: int,
        per_page: int,
        task_id: int | None = None,
        status: str | None = None,
    ) -> tuple[list[OutboundTaskTarget], int]:
        filters = [
            OutboundTaskTarget.tenant_id == tenant_id,
            OutboundTaskTarget.assignee_id == assignee_id,
            OutboundTask.status.in_(["active", "paused"]),
        ]
        if task_id:
            filters.append(OutboundTaskTarget.task_id == task_id)
        if status:
            filters.append(OutboundTaskTarget.status == status)
        else:
            filters.append(OutboundTaskTarget.status.in_(["pending", "redial", "completed"]))

        stmt = (
            select(OutboundTaskTarget)
            .join(OutboundTask, OutboundTask.id == OutboundTaskTarget.task_id)
            .options(selectinload(OutboundTaskTarget.task))
            .where(*filters)
        )
        count_stmt = (
            select(func.count())
            .select_from(OutboundTaskTarget)
            .join(OutboundTask, OutboundTask.id == OutboundTaskTarget.task_id)
            .where(*filters)
        )
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            _paginate_statement(
                stmt.order_by(
                    OutboundTaskTarget.next_follow_up_at.asc().nulls_last(),
                    OutboundTaskTarget.created_at.asc(),
                ),
                page,
                per_page,
            )
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_target(db: AsyncSession, target_id: int) -> OutboundTaskTarget | None:
        return await db.get(OutboundTaskTarget, target_id)

    @staticmethod
    async def create_target(db: AsyncSession, data: dict) -> OutboundTaskTarget:
        item = OutboundTaskTarget(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update_target(db: AsyncSession, item: OutboundTaskTarget, data: dict) -> OutboundTaskTarget:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def bulk_assign(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        target_ids: list[int],
        assignee_id: int | None,
        overwrite: bool,
    ) -> int:
        filters = [
            OutboundTaskTarget.tenant_id == tenant_id,
            OutboundTaskTarget.task_id == task_id,
            OutboundTaskTarget.id.in_(target_ids),
            OutboundTaskTarget.status.notin_(["completed", "do_not_call", "invalid_number"]),
        ]
        if not overwrite:
            filters.append(OutboundTaskTarget.assignee_id.is_(None))
        result = await db.execute(
            update(OutboundTaskTarget)
            .where(*filters)
            .values(assignee_id=assignee_id)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def bulk_delete_targets(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        target_ids: list[int],
    ) -> int:
        result = await db.execute(
            delete(OutboundTaskTarget).where(
                OutboundTaskTarget.tenant_id == tenant_id,
                OutboundTaskTarget.task_id == task_id,
                OutboundTaskTarget.id.in_(target_ids),
            )
        )
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def create_record(db: AsyncSession, data: dict) -> OutboundCallRecord:
        item = OutboundCallRecord(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def list_records(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        page: int,
        per_page: int,
    ) -> tuple[list[OutboundCallRecord], int]:
        filters = [OutboundCallRecord.tenant_id == tenant_id, OutboundCallRecord.task_id == task_id]
        total = (await db.execute(select(func.count()).select_from(OutboundCallRecord).where(*filters))).scalar_one()
        result = await db.execute(
            _paginate_statement(
                select(OutboundCallRecord).where(*filters).order_by(OutboundCallRecord.started_at.desc()),
                page,
                per_page,
            )
        )
        return list(result.scalars().all()), total
