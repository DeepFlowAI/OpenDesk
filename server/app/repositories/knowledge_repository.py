"""
Knowledge base repository.
"""
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeDirectory, KnowledgeDocument


class KnowledgeDirectoryRepository:
    @staticmethod
    async def get_by_id(db: AsyncSession, directory_id: int) -> KnowledgeDirectory | None:
        return await db.get(KnowledgeDirectory, directory_id)

    @staticmethod
    async def list_all(db: AsyncSession, tenant_id: int) -> list[KnowledgeDirectory]:
        result = await db.execute(
            select(KnowledgeDirectory)
            .where(KnowledgeDirectory.tenant_id == tenant_id)
            .order_by(
                KnowledgeDirectory.parent_id.asc().nullsfirst(),
                KnowledgeDirectory.sort_order.asc(),
                KnowledgeDirectory.id.asc(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_name(
        db: AsyncSession,
        tenant_id: int,
        parent_id: int | None,
        name: str,
        exclude_id: int | None = None,
    ) -> KnowledgeDirectory | None:
        query = select(KnowledgeDirectory).where(
            KnowledgeDirectory.tenant_id == tenant_id,
            KnowledgeDirectory.name == name,
        )
        if parent_id is None:
            query = query.where(KnowledgeDirectory.parent_id.is_(None))
        else:
            query = query.where(KnowledgeDirectory.parent_id == parent_id)
        if exclude_id is not None:
            query = query.where(KnowledgeDirectory.id != exclude_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def max_sort_order(
        db: AsyncSession,
        tenant_id: int,
        parent_id: int | None,
    ) -> int:
        query = select(func.coalesce(func.max(KnowledgeDirectory.sort_order), 0)).where(
            KnowledgeDirectory.tenant_id == tenant_id
        )
        if parent_id is None:
            query = query.where(KnowledgeDirectory.parent_id.is_(None))
        else:
            query = query.where(KnowledgeDirectory.parent_id == parent_id)
        return int((await db.execute(query)).scalar_one())

    @staticmethod
    async def count_children(db: AsyncSession, tenant_id: int, directory_id: int) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(KnowledgeDirectory)
            .where(
                KnowledgeDirectory.tenant_id == tenant_id,
                KnowledgeDirectory.parent_id == directory_id,
            )
        )
        return int(result.scalar_one())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> KnowledgeDirectory:
        directory = KnowledgeDirectory(**data)
        db.add(directory)
        await db.commit()
        await db.refresh(directory)
        return directory

    @staticmethod
    async def create_pending(db: AsyncSession, data: dict) -> KnowledgeDirectory:
        directory = KnowledgeDirectory(**data)
        db.add(directory)
        await db.flush()
        return directory

    @staticmethod
    async def update(
        db: AsyncSession,
        directory: KnowledgeDirectory,
        data: dict,
    ) -> KnowledgeDirectory:
        for key, value in data.items():
            if hasattr(directory, key):
                setattr(directory, key, value)
        await db.commit()
        await db.refresh(directory)
        return directory

    @staticmethod
    async def delete(db: AsyncSession, directory: KnowledgeDirectory) -> None:
        await db.delete(directory)
        await db.commit()


class KnowledgeDocumentRepository:
    @staticmethod
    async def get_by_id(db: AsyncSession, document_id: int) -> KnowledgeDocument | None:
        return await db.get(KnowledgeDocument, document_id)

    @staticmethod
    async def get_by_ids(
        db: AsyncSession,
        tenant_id: int,
        document_ids: list[int],
    ) -> dict[int, KnowledgeDocument]:
        if not document_ids:
            return {}
        result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.id.in_(document_ids),
            )
        )
        return {document.id: document for document in result.scalars().all()}

    @staticmethod
    async def title_lookup(db: AsyncSession, tenant_id: int) -> dict[tuple[int, str], int]:
        result = await db.execute(
            select(KnowledgeDocument.directory_id, KnowledgeDocument.title, KnowledgeDocument.id).where(
                KnowledgeDocument.tenant_id == tenant_id
            )
        )
        return {(int(directory_id), str(title)): int(document_id) for directory_id, title, document_id in result.all()}

    @staticmethod
    async def get_by_title(
        db: AsyncSession,
        tenant_id: int,
        directory_id: int,
        title: str,
        exclude_id: int | None = None,
    ) -> KnowledgeDocument | None:
        query = select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.directory_id == directory_id,
            KnowledgeDocument.title == title,
        )
        if exclude_id is not None:
            query = query.where(KnowledgeDocument.id != exclude_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def count_by_directory_ids(
        db: AsyncSession,
        tenant_id: int,
        directory_ids: list[int],
        include_drafts: bool,
    ) -> dict[int, int]:
        if not directory_ids:
            return {}
        query = (
            select(KnowledgeDocument.directory_id, func.count(KnowledgeDocument.id))
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.directory_id.in_(directory_ids),
            )
            .group_by(KnowledgeDocument.directory_id)
        )
        if not include_drafts:
            query = query.where(KnowledgeDocument.status == "published")
        result = await db.execute(query)
        return {int(directory_id): int(count) for directory_id, count in result.all()}

    @staticmethod
    async def count_direct(db: AsyncSession, tenant_id: int, directory_id: int) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.directory_id == directory_id,
            )
        )
        return int(result.scalar_one())

    @staticmethod
    async def query_paginated(
        db: AsyncSession,
        tenant_id: int,
        *,
        directory_ids: list[int] | None = None,
        search: str | None = None,
        status: str | None = None,
        display_status: str | None = None,
        include_drafts: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[KnowledgeDocument], int]:
        query = select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == tenant_id)
        if directory_ids is not None:
            if not directory_ids:
                return [], 0
            query = query.where(KnowledgeDocument.directory_id.in_(directory_ids))
        if search:
            like_pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    KnowledgeDocument.title.ilike(like_pattern),
                    KnowledgeDocument.content_plain.ilike(like_pattern),
                )
            )
        if status:
            query = query.where(KnowledgeDocument.status == status)
        if display_status:
            now = datetime.now(timezone.utc)
            if display_status == "draft":
                query = query.where(KnowledgeDocument.status == "draft")
            elif display_status == "published":
                query = query.where(
                    KnowledgeDocument.status == "published",
                    or_(
                        KnowledgeDocument.validity_type != "scheduled",
                        and_(
                            KnowledgeDocument.valid_from.is_not(None),
                            KnowledgeDocument.valid_to.is_not(None),
                            KnowledgeDocument.valid_from <= now,
                            KnowledgeDocument.valid_to >= now,
                        ),
                    ),
                )
            elif display_status == "expired":
                query = query.where(
                    KnowledgeDocument.status == "published",
                    KnowledgeDocument.validity_type == "scheduled",
                    or_(
                        KnowledgeDocument.valid_from.is_(None),
                        KnowledgeDocument.valid_to.is_(None),
                        KnowledgeDocument.valid_from > now,
                        KnowledgeDocument.valid_to < now,
                    ),
                )
        if not include_drafts:
            query = query.where(KnowledgeDocument.status == "published")

        total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one())
        offset = (page - 1) * per_page
        result = await db.execute(
            query.order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
            .offset(offset)
            .limit(per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def query_all(
        db: AsyncSession,
        tenant_id: int,
        *,
        directory_ids: list[int] | None = None,
        search: str | None = None,
        include_drafts: bool = False,
    ) -> list[KnowledgeDocument]:
        query = select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == tenant_id)
        if directory_ids is not None:
            if not directory_ids:
                return []
            query = query.where(KnowledgeDocument.directory_id.in_(directory_ids))
        if search:
            like_pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    KnowledgeDocument.title.ilike(like_pattern),
                    KnowledgeDocument.content_plain.ilike(like_pattern),
                )
            )
        if not include_drafts:
            query = query.where(KnowledgeDocument.status == "published")
        result = await db.execute(query.order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, data: dict) -> KnowledgeDocument:
        document = KnowledgeDocument(**data)
        db.add(document)
        await db.commit()
        await db.refresh(document)
        return document

    @staticmethod
    async def create_pending(db: AsyncSession, data: dict) -> KnowledgeDocument:
        document = KnowledgeDocument(**data)
        db.add(document)
        await db.flush()
        return document

    @staticmethod
    async def update(
        db: AsyncSession,
        document: KnowledgeDocument,
        data: dict,
    ) -> KnowledgeDocument:
        for key, value in data.items():
            if hasattr(document, key):
                setattr(document, key, value)
        await db.commit()
        await db.refresh(document)
        return document

    @staticmethod
    async def update_pending(
        db: AsyncSession,
        document: KnowledgeDocument,
        data: dict,
    ) -> KnowledgeDocument:
        for key, value in data.items():
            if hasattr(document, key):
                setattr(document, key, value)
        await db.flush()
        return document

    @staticmethod
    async def delete(db: AsyncSession, document: KnowledgeDocument) -> None:
        await db.delete(document)
        await db.commit()
