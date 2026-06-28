"""
Knowledge base service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.employee import Employee
from app.models.knowledge import KnowledgeDirectory, KnowledgeDocument
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.knowledge_repository import (
    KnowledgeDirectoryRepository,
    KnowledgeDocumentRepository,
)
from app.schemas.knowledge import (
    KnowledgeDirectoryCreate,
    KnowledgeDirectoryListResponse,
    KnowledgeDirectoryMove,
    KnowledgeDirectoryNode,
    KnowledgeDirectoryPathItem,
    KnowledgeDirectoryResponse,
    KnowledgeDirectoryUpdate,
    KnowledgeDocumentCreate,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentUpdate,
)
from app.schemas.permission import EffectivePrincipal

MAX_DIRECTORY_DEPTH = 3


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())


def html_to_plain_text(html: str) -> str:
    parser = _PlainTextParser()
    parser.feed(html or "")
    return parser.text()


class KnowledgeService:
    @staticmethod
    def document_display_status(document: KnowledgeDocument, now: datetime | None = None) -> str:
        if document.status == "draft":
            return "draft"
        current = now or datetime.now(timezone.utc)
        if document.validity_type == "scheduled":
            if document.valid_from is None or document.valid_to is None:
                return "expired"
            if current < document.valid_from or current > document.valid_to:
                return "expired"
        return document.status

    @staticmethod
    def _include_drafts(principal: EffectivePrincipal | None) -> bool:
        if principal is None:
            return False
        return principal.has_permission("knowledge.workspace.document.edit")

    @staticmethod
    def _actor_display_name(employee: Employee | None) -> str | None:
        if not employee:
            return None
        for value in (employee.display_name, employee.nickname, employee.name, employee.username):
            if value and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    async def _actor_update(
        db: AsyncSession,
        tenant_id: int,
        actor_id: int | None,
        *,
        actor_type: str = "employee",
        actor_name: str | None = None,
    ) -> dict:
        if actor_type != "employee":
            return {
                "updated_by_actor_type": actor_type,
                "updated_by_actor_id": actor_id,
                "updated_by_actor_name": actor_name,
            }
        employee_actor_name: str | None = None
        if actor_id is not None:
            employee = await EmployeeRepository.get_by_id(db, actor_id)
            if employee and employee.tenant_id == tenant_id:
                employee_actor_name = KnowledgeService._actor_display_name(employee)
        return {
            "updated_by_actor_type": "employee" if actor_id is not None else None,
            "updated_by_actor_id": actor_id,
            "updated_by_actor_name": employee_actor_name,
        }

    @staticmethod
    async def _actor_create(
        db: AsyncSession,
        tenant_id: int,
        actor_id: int | None,
        *,
        actor_type: str = "employee",
        actor_name: str | None = None,
    ) -> dict:
        actor_data = await KnowledgeService._actor_update(
            db,
            tenant_id,
            actor_id,
            actor_type=actor_type,
            actor_name=actor_name,
        )
        return {
            "created_by_actor_type": actor_data["updated_by_actor_type"],
            "created_by_actor_id": actor_data["updated_by_actor_id"],
            "created_by_actor_name": actor_data["updated_by_actor_name"],
            **actor_data,
        }

    @staticmethod
    def _depth_map(directories: list[KnowledgeDirectory]) -> dict[int, int]:
        by_id = {directory.id: directory for directory in directories}
        memo: dict[int, int] = {}

        def depth(directory: KnowledgeDirectory, seen: set[int] | None = None) -> int:
            if directory.id in memo:
                return memo[directory.id]
            seen = seen or set()
            if directory.id in seen or directory.parent_id is None or directory.parent_id not in by_id:
                memo[directory.id] = 1
                return 1
            seen.add(directory.id)
            parent_depth = depth(by_id[directory.parent_id], seen)
            memo[directory.id] = parent_depth + 1
            return memo[directory.id]

        for item in directories:
            depth(item)
        return memo

    @staticmethod
    async def _validate_parent(
        db: AsyncSession,
        tenant_id: int,
        parent_id: int | None,
        current_id: int | None = None,
    ) -> int:
        if parent_id is None:
            return 1
        if current_id is not None and parent_id == current_id:
            raise ValidationError("Directory cannot be its own parent")
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        by_id = {directory.id: directory for directory in directories}
        parent = by_id.get(parent_id)
        if not parent:
            raise NotFoundError("Parent directory not found")
        depth = 2
        cursor = parent
        seen: set[int] = set()
        while cursor.parent_id is not None:
            if cursor.id in seen:
                raise ValidationError("Invalid directory tree")
            if current_id is not None and cursor.parent_id == current_id:
                raise ValidationError("Directory cannot move under its descendant")
            seen.add(cursor.id)
            cursor = by_id.get(cursor.parent_id)
            if cursor is None:
                break
            depth += 1
        if depth > MAX_DIRECTORY_DEPTH:
            raise ValidationError("Directory depth cannot exceed 3 levels")
        return depth

    @staticmethod
    def _descendant_ids(directories: list[KnowledgeDirectory], directory_id: int) -> list[int]:
        children_by_parent: dict[int | None, list[KnowledgeDirectory]] = {}
        for directory in directories:
            children_by_parent.setdefault(directory.parent_id, []).append(directory)
        ids: list[int] = []

        def walk(node_id: int) -> None:
            ids.append(node_id)
            for child in children_by_parent.get(node_id, []):
                walk(child.id)

        walk(directory_id)
        return ids

    @staticmethod
    def _directory_path(
        directories: list[KnowledgeDirectory],
        directory_id: int,
    ) -> list[KnowledgeDirectoryPathItem]:
        by_id = {directory.id: directory for directory in directories}
        cursor = by_id.get(directory_id)
        path: list[KnowledgeDirectoryPathItem] = []
        seen: set[int] = set()
        while cursor and cursor.id not in seen:
            path.append(KnowledgeDirectoryPathItem(id=cursor.id, name=cursor.name))
            seen.add(cursor.id)
            cursor = by_id.get(cursor.parent_id) if cursor.parent_id is not None else None
        return list(reversed(path))

    @staticmethod
    def _directory_response(
        directory: KnowledgeDirectory,
        depth: int,
        document_count: int = 0,
    ) -> KnowledgeDirectoryResponse:
        return KnowledgeDirectoryResponse(
            id=directory.id,
            tenant_id=directory.tenant_id,
            parent_id=directory.parent_id,
            name=directory.name,
            sort_order=directory.sort_order,
            depth=depth,
            document_count=document_count,
            created_at=directory.created_at,
            updated_at=directory.updated_at,
            created_by=directory.created_by,
            updated_by=directory.updated_by,
        )

    @staticmethod
    def _document_response(
        document: KnowledgeDocument,
        directory_path: list[KnowledgeDirectoryPathItem],
    ) -> KnowledgeDocumentResponse:
        return KnowledgeDocumentResponse(
            id=document.id,
            tenant_id=document.tenant_id,
            directory_id=document.directory_id,
            directory_path=directory_path,
            title=document.title,
            content_html=document.content_html,
            status=document.status,
            display_status=KnowledgeService.document_display_status(document),
            validity_type=document.validity_type,
            valid_from=document.valid_from,
            valid_to=document.valid_to,
            created_at=document.created_at,
            updated_at=document.updated_at,
            created_by=document.created_by,
            updated_by=document.updated_by,
        )

    @staticmethod
    async def list_directories(
        db: AsyncSession,
        tenant_id: int,
        principal: EffectivePrincipal | None = None,
        *,
        include_drafts: bool | None = None,
    ) -> KnowledgeDirectoryListResponse:
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        depth_by_id = KnowledgeService._depth_map(directories)
        direct_counts = await KnowledgeDocumentRepository.count_by_directory_ids(
            db,
            tenant_id,
            [directory.id for directory in directories],
            include_drafts=include_drafts
            if include_drafts is not None
            else KnowledgeService._include_drafts(principal),
        )
        children_by_parent: dict[int | None, list[KnowledgeDirectory]] = {}
        for directory in directories:
            parent_key = directory.parent_id if directory.parent_id in depth_by_id else None
            children_by_parent.setdefault(parent_key, []).append(directory)

        def build(directory: KnowledgeDirectory) -> KnowledgeDirectoryNode:
            children = [build(child) for child in children_by_parent.get(directory.id, [])]
            total_count = direct_counts.get(directory.id, 0) + sum(child.document_count for child in children)
            response = KnowledgeService._directory_response(
                directory,
                depth=depth_by_id.get(directory.id, 1),
                document_count=total_count,
            )
            return KnowledgeDirectoryNode(**response.model_dump(), children=children)

        roots = [build(directory) for directory in children_by_parent.get(None, [])]
        return KnowledgeDirectoryListResponse(items=roots)

    @staticmethod
    async def create_directory(
        db: AsyncSession,
        tenant_id: int,
        data: KnowledgeDirectoryCreate,
        actor_id: int | None,
        *,
        actor_type: str = "employee",
        actor_name: str | None = None,
    ) -> KnowledgeDirectoryResponse:
        await KnowledgeService._validate_parent(db, tenant_id, data.parent_id)
        if await KnowledgeDirectoryRepository.get_by_name(db, tenant_id, data.parent_id, data.name):
            raise ValidationError("Directory name already exists")
        sort_order = await KnowledgeDirectoryRepository.max_sort_order(db, tenant_id, data.parent_id) + 10
        directory = await KnowledgeDirectoryRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "parent_id": data.parent_id,
                "name": data.name,
                "sort_order": sort_order,
                **await KnowledgeService._actor_create(
                    db,
                    tenant_id,
                    actor_id,
                    actor_type=actor_type,
                    actor_name=actor_name,
                ),
            },
        )
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        depth = KnowledgeService._depth_map(directories).get(directory.id, 1)
        return KnowledgeService._directory_response(directory, depth=depth)

    @staticmethod
    async def update_directory(
        db: AsyncSession,
        tenant_id: int,
        directory_id: int,
        data: KnowledgeDirectoryUpdate,
        actor_id: int | None,
        *,
        actor_type: str = "employee",
        actor_name: str | None = None,
    ) -> KnowledgeDirectoryResponse:
        directory = await KnowledgeDirectoryRepository.get_by_id(db, directory_id)
        if not directory or directory.tenant_id != tenant_id:
            raise NotFoundError("Directory not found")
        update_data = data.model_dump(exclude_unset=True)
        parent_id = update_data.get("parent_id", directory.parent_id)
        await KnowledgeService._validate_parent(db, tenant_id, parent_id, current_id=directory.id)
        name = update_data.get("name", directory.name)
        if await KnowledgeDirectoryRepository.get_by_name(
            db,
            tenant_id,
            parent_id,
            name,
            exclude_id=directory.id,
        ):
            raise ValidationError("Directory name already exists")
        update_data.update(
            await KnowledgeService._actor_update(
                db,
                tenant_id,
                actor_id,
                actor_type=actor_type,
                actor_name=actor_name,
            )
        )
        updated = await KnowledgeDirectoryRepository.update(db, directory, update_data)
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        depth = KnowledgeService._depth_map(directories).get(updated.id, 1)
        return KnowledgeService._directory_response(updated, depth=depth)

    @staticmethod
    async def move_directory(
        db: AsyncSession,
        tenant_id: int,
        directory_id: int,
        data: KnowledgeDirectoryMove,
        actor_id: int | None,
        *,
        actor_type: str = "employee",
        actor_name: str | None = None,
    ) -> KnowledgeDirectoryResponse:
        directory = await KnowledgeDirectoryRepository.get_by_id(db, directory_id)
        if not directory or directory.tenant_id != tenant_id:
            raise NotFoundError("Directory not found")
        parent_id = data.parent_id
        await KnowledgeService._validate_parent(db, tenant_id, parent_id, current_id=directory.id)
        if await KnowledgeDirectoryRepository.get_by_name(
            db,
            tenant_id,
            parent_id,
            directory.name,
            exclude_id=directory.id,
        ):
            raise ValidationError("Directory name already exists")
        update_data = {"parent_id": parent_id}
        if data.sort_order is not None:
            update_data["sort_order"] = data.sort_order
        update_data.update(
            await KnowledgeService._actor_update(
                db,
                tenant_id,
                actor_id,
                actor_type=actor_type,
                actor_name=actor_name,
            )
        )
        updated = await KnowledgeDirectoryRepository.update(db, directory, update_data)
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        depth = KnowledgeService._depth_map(directories).get(updated.id, 1)
        return KnowledgeService._directory_response(updated, depth=depth)

    @staticmethod
    async def delete_directory(db: AsyncSession, tenant_id: int, directory_id: int) -> None:
        directory = await KnowledgeDirectoryRepository.get_by_id(db, directory_id)
        if not directory or directory.tenant_id != tenant_id:
            raise NotFoundError("Directory not found")
        if await KnowledgeDirectoryRepository.count_children(db, tenant_id, directory_id) > 0:
            raise ValidationError("Directory is not empty")
        if await KnowledgeDocumentRepository.count_direct(db, tenant_id, directory_id) > 0:
            raise ValidationError("Directory is not empty")
        await KnowledgeDirectoryRepository.delete(db, directory)

    @staticmethod
    def _validate_document_values(
        values: dict,
        existing: KnowledgeDocument | None = None,
    ) -> dict:
        def local_naive(value: datetime | None) -> datetime | None:
            if value is None:
                return None
            if value.tzinfo is not None:
                return value.astimezone().replace(tzinfo=None)
            return value

        validity_type = values.get("validity_type", existing.validity_type if existing else "permanent")
        valid_from = local_naive(values.get("valid_from", existing.valid_from if existing else None))
        valid_to = local_naive(values.get("valid_to", existing.valid_to if existing else None))
        if validity_type == "permanent":
            values["valid_from"] = None
            values["valid_to"] = None
            return values
        if valid_from is None or valid_to is None:
            raise ValidationError("Valid period is required")
        if valid_to <= valid_from:
            raise ValidationError("Valid end must be later than valid start")
        values["valid_from"] = valid_from
        values["valid_to"] = valid_to
        return values

    @staticmethod
    async def _validate_directory_exists(
        db: AsyncSession,
        tenant_id: int,
        directory_id: int,
    ) -> KnowledgeDirectory:
        directory = await KnowledgeDirectoryRepository.get_by_id(db, directory_id)
        if not directory or directory.tenant_id != tenant_id:
            raise NotFoundError("Directory not found")
        return directory

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        tenant_id: int,
        principal: EffectivePrincipal | None = None,
        *,
        directory_id: int | None = None,
        search: str | None = None,
        status: str | None = None,
        display_status: str | None = None,
        include_drafts: bool | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> KnowledgeDocumentListResponse:
        page = max(1, page)
        per_page = max(1, min(per_page, 100))
        all_directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        directory_ids: list[int] | None = None
        if directory_id is not None:
            if directory_id not in {directory.id for directory in all_directories}:
                raise NotFoundError("Directory not found")
            directory_ids = KnowledgeService._descendant_ids(all_directories, directory_id)
        items, total = await KnowledgeDocumentRepository.query_paginated(
            db,
            tenant_id,
            directory_ids=directory_ids,
            search=search.strip() if search else None,
            status=status,
            display_status=display_status,
            include_drafts=include_drafts
            if include_drafts is not None
            else KnowledgeService._include_drafts(principal),
            page=page,
            per_page=per_page,
        )
        return KnowledgeDocumentListResponse(
            items=[
                KnowledgeService._document_response(
                    item,
                    KnowledgeService._directory_path(all_directories, item.directory_id),
                )
                for item in items
            ],
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page if total > 0 else 0,
        )

    @staticmethod
    async def create_document(
        db: AsyncSession,
        tenant_id: int,
        data: KnowledgeDocumentCreate,
        actor_id: int | None,
        *,
        actor_type: str = "employee",
        actor_name: str | None = None,
    ) -> KnowledgeDocumentResponse:
        await KnowledgeService._validate_directory_exists(db, tenant_id, data.directory_id)
        if await KnowledgeDocumentRepository.get_by_title(db, tenant_id, data.directory_id, data.title):
            raise ValidationError("Document title already exists")
        content_plain = html_to_plain_text(data.content_html)
        if not content_plain:
            raise ValidationError("Document content is required")
        values = KnowledgeService._validate_document_values(data.model_dump())
        document = await KnowledgeDocumentRepository.create(
            db,
            {
                **values,
                "tenant_id": tenant_id,
                "content_plain": content_plain,
                **await KnowledgeService._actor_create(
                    db,
                    tenant_id,
                    actor_id,
                    actor_type=actor_type,
                    actor_name=actor_name,
                ),
            },
        )
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        from app.services.knowledge_recommendation_service import KnowledgeRecommendationService

        KnowledgeRecommendationService.schedule_document_embedding_refresh(tenant_id, document.id)
        return KnowledgeService._document_response(
            document,
            KnowledgeService._directory_path(directories, document.directory_id),
        )

    @staticmethod
    async def get_document(
        db: AsyncSession,
        tenant_id: int,
        document_id: int,
        principal: EffectivePrincipal | None = None,
        *,
        include_drafts: bool | None = None,
    ) -> KnowledgeDocumentResponse:
        document = await KnowledgeDocumentRepository.get_by_id(db, document_id)
        if not document or document.tenant_id != tenant_id:
            raise NotFoundError("Document not found")
        can_include_drafts = include_drafts
        if can_include_drafts is None:
            can_include_drafts = KnowledgeService._include_drafts(principal)
        if document.status == "draft" and not can_include_drafts:
            raise NotFoundError("Document not found")
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        return KnowledgeService._document_response(
            document,
            KnowledgeService._directory_path(directories, document.directory_id),
        )

    @staticmethod
    async def update_document(
        db: AsyncSession,
        tenant_id: int,
        document_id: int,
        data: KnowledgeDocumentUpdate,
        actor_id: int | None,
        *,
        actor_type: str = "employee",
        actor_name: str | None = None,
    ) -> KnowledgeDocumentResponse:
        document = await KnowledgeDocumentRepository.get_by_id(db, document_id)
        if not document or document.tenant_id != tenant_id:
            raise NotFoundError("Document not found")
        update_data = data.model_dump(exclude_unset=True)
        directory_id = update_data.get("directory_id", document.directory_id)
        await KnowledgeService._validate_directory_exists(db, tenant_id, directory_id)
        title = update_data.get("title", document.title)
        if await KnowledgeDocumentRepository.get_by_title(
            db,
            tenant_id,
            directory_id,
            title,
            exclude_id=document.id,
        ):
            raise ValidationError("Document title already exists")
        if "content_html" in update_data:
            content_plain = html_to_plain_text(update_data["content_html"])
            if not content_plain:
                raise ValidationError("Document content is required")
            update_data["content_plain"] = content_plain
        update_data = KnowledgeService._validate_document_values(update_data, existing=document)
        update_data.update(
            await KnowledgeService._actor_update(
                db,
                tenant_id,
                actor_id,
                actor_type=actor_type,
                actor_name=actor_name,
            )
        )
        updated = await KnowledgeDocumentRepository.update(db, document, update_data)
        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        from app.services.knowledge_recommendation_service import KnowledgeRecommendationService

        KnowledgeRecommendationService.schedule_document_embedding_refresh(tenant_id, updated.id)
        return KnowledgeService._document_response(
            updated,
            KnowledgeService._directory_path(directories, updated.directory_id),
        )

    @staticmethod
    async def delete_document(db: AsyncSession, tenant_id: int, document_id: int) -> None:
        document = await KnowledgeDocumentRepository.get_by_id(db, document_id)
        if not document or document.tenant_id != tenant_id:
            raise NotFoundError("Document not found")
        await KnowledgeDocumentRepository.delete(db, document)
