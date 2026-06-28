"""
Knowledge base repository.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ColumnElement

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
    def _keyword_terms(search: str | None) -> list[str]:
        if not search:
            return []
        return [part.casefold() for part in re.split(r"\s+", search.strip()) if part]

    @staticmethod
    def _content_for_search_sql() -> ColumnElement:
        return func.concat_ws(" ", KnowledgeDocument.title, KnowledgeDocument.content_plain)

    @staticmethod
    def _content_for_search(document: KnowledgeDocument) -> str:
        return " ".join(part for part in [document.title, document.content_plain] if part)

    @staticmethod
    def _compute_keyword_score(search: str | None, content_for_search: str) -> int:
        terms = KnowledgeDocumentRepository._keyword_terms(search)
        if not terms:
            return 0
        content = content_for_search.casefold()
        return sum(content.count(term) for term in terms)

    @staticmethod
    def _updated_at_sort_value(document: KnowledgeDocument) -> float:
        updated_at = getattr(document, "updated_at", None)
        if not isinstance(updated_at, datetime):
            return float("-inf")
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return updated_at.timestamp()

    @staticmethod
    def _sort_by_keyword_score(
        documents: list[KnowledgeDocument],
        search: str | None,
    ) -> list[KnowledgeDocument]:
        return sorted(
            documents,
            key=lambda document: (
                KnowledgeDocumentRepository._compute_keyword_score(
                    search,
                    KnowledgeDocumentRepository._content_for_search(document),
                ),
                KnowledgeDocumentRepository._updated_at_sort_value(document),
                int(document.id or 0),
            ),
            reverse=True,
        )

    @staticmethod
    def _apply_search_filter(query: Select, search: str | None) -> Select:
        terms = KnowledgeDocumentRepository._keyword_terms(search)
        if not terms:
            return query
        content_for_search = KnowledgeDocumentRepository._content_for_search_sql()
        return query.where(or_(*(content_for_search.ilike(f"%{term}%") for term in terms)))

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
        query = KnowledgeDocumentRepository._apply_search_filter(query, search)
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
        if KnowledgeDocumentRepository._keyword_terms(search):
            result = await db.execute(query)
            items = KnowledgeDocumentRepository._sort_by_keyword_score(list(result.scalars().all()), search)
            return items[offset : offset + per_page], total

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
        query = KnowledgeDocumentRepository._apply_search_filter(query, search)
        if not include_drafts:
            query = query.where(KnowledgeDocument.status == "published")
        if KnowledgeDocumentRepository._keyword_terms(search):
            result = await db.execute(query)
            return KnowledgeDocumentRepository._sort_by_keyword_score(list(result.scalars().all()), search)
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
