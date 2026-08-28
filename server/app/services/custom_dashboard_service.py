"""Business rules for custom dashboard lifecycle and snapshot publishing."""

from datetime import datetime, timezone
import re

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.custom_dashboard import CustomDashboard, CustomDashboardVersion
from app.libs.dashboard_sandbox.runner import CodeValidationError, validate_code
from app.repositories.custom_dashboard_repository import CustomDashboardRepository
from app.schemas.custom_dashboard import (
    CustomDashboardCopyRequest,
    CustomDashboardCreate,
    CustomDashboardUpdate,
    DashboardSnapshotInput,
)
from app.services.system_settings_service import SystemSettingsService


MAX_DASHBOARDS_PER_TENANT = 30
MAX_PUBLISHED_COMPONENTS_PER_TENANT = 300


class CustomDashboardService:
    """Manage tenant dashboards while keeping draft and published data isolated."""

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        *,
        page: int = 1,
        per_page: int = 20,
        keyword: str | None = None,
        status: str | None = None,
    ) -> dict:
        rows, total = await CustomDashboardRepository.get_paginated(
            db,
            tenant_id,
            page=page,
            per_page=per_page,
            keyword=keyword,
            status=status,
        )
        return {
            "items": [_list_item(dashboard, draft) for dashboard, draft in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page if total else 0,
        }

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        dashboard_id: int,
        tenant_id: int,
    ) -> dict:
        dashboard = await CustomDashboardRepository.get_by_id(db, dashboard_id, tenant_id)
        if dashboard is None:
            raise NotFoundError("Custom dashboard not found")
        draft = await CustomDashboardRepository.get_version(
            db,
            dashboard_id,
            tenant_id,
            "draft",
        )
        if draft is None:
            raise NotFoundError("Custom dashboard draft not found")
        published = await CustomDashboardRepository.get_version(
            db,
            dashboard_id,
            tenant_id,
            "published",
        )
        return _detail(dashboard, draft, published)

    @staticmethod
    async def create(
        db: AsyncSession,
        tenant_id: int,
        data: CustomDashboardCreate,
    ) -> dict:
        await CustomDashboardService._ensure_dashboard_quota(db, tenant_id)
        max_sort_order = await CustomDashboardRepository.get_max_sort_order(db, tenant_id)
        try:
            dashboard = await CustomDashboardRepository.create_dashboard(
                db,
                {
                    "tenant_id": tenant_id,
                    "name": data.name,
                    "slug": data.slug,
                    "status": "draft",
                    "sort_order": max_sort_order + 1,
                },
            )
            draft = await CustomDashboardRepository.create_version(
                db,
                _version_data(
                    dashboard,
                    "draft",
                    revision=1,
                    snapshot=data,
                ),
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError("Dashboard name or slug already exists") from exc
        await db.refresh(dashboard)
        await db.refresh(draft)
        return _detail(dashboard, draft, None)

    @staticmethod
    async def update(
        db: AsyncSession,
        dashboard_id: int,
        tenant_id: int,
        data: CustomDashboardUpdate,
    ) -> dict:
        dashboard = await CustomDashboardRepository.get_by_id(
            db,
            dashboard_id,
            tenant_id,
            for_update=True,
        )
        if dashboard is None:
            raise NotFoundError("Custom dashboard not found")
        draft = await CustomDashboardRepository.get_version(
            db,
            dashboard_id,
            tenant_id,
            "draft",
            for_update=True,
        )
        if draft is None:
            raise NotFoundError("Custom dashboard draft not found")

        try:
            await CustomDashboardRepository.update_dashboard(
                db,
                dashboard,
                {"name": data.name},
            )
            await CustomDashboardRepository.update_version(
                db,
                draft,
                {
                    **_snapshot_values(data),
                    "revision": draft.revision + 1,
                },
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError("Dashboard name already exists") from exc
        await db.refresh(dashboard)
        await db.refresh(draft)
        published = await CustomDashboardRepository.get_version(
            db,
            dashboard_id,
            tenant_id,
            "published",
        )
        return _detail(dashboard, draft, published)

    @staticmethod
    async def publish(
        db: AsyncSession,
        dashboard_id: int,
        tenant_id: int,
    ) -> dict:
        dashboard = await CustomDashboardRepository.get_by_id(
            db,
            dashboard_id,
            tenant_id,
            for_update=True,
        )
        if dashboard is None:
            raise NotFoundError("Custom dashboard not found")
        draft = await CustomDashboardRepository.get_version(
            db,
            dashboard_id,
            tenant_id,
            "draft",
            for_update=True,
        )
        if draft is None:
            raise NotFoundError("Custom dashboard draft not found")
        _validate_stored_snapshot(draft)
        _validate_component_code(draft.components)

        published_component_count = await CustomDashboardRepository.count_published_components(
            db,
            tenant_id,
            exclude_dashboard_id=dashboard_id,
        )
        if published_component_count + len(draft.components) > MAX_PUBLISHED_COMPONENTS_PER_TENANT:
            raise ValidationError("Published component quota exceeded")

        published = await CustomDashboardRepository.get_version(
            db,
            dashboard_id,
            tenant_id,
            "published",
            for_update=True,
        )
        values = {
            "name": draft.name,
            "description": draft.description,
            "icon": draft.icon,
            "filters": draft.filters,
            "components": draft.components,
        }
        if published is None:
            published = await CustomDashboardRepository.create_version(
                db,
                {
                    "tenant_id": tenant_id,
                    "dashboard_id": dashboard_id,
                    "kind": "published",
                    "revision": 1,
                    **values,
                },
            )
        else:
            await CustomDashboardRepository.update_version(
                db,
                published,
                {**values, "revision": published.revision + 1},
            )

        await CustomDashboardRepository.update_dashboard(
            db,
            dashboard,
            {
                "status": "disabled" if dashboard.status == "disabled" else "published",
                "published_at": datetime.now(timezone.utc),
            },
        )
        await db.commit()
        await db.refresh(dashboard)
        await db.refresh(draft)
        await db.refresh(published)
        return _detail(dashboard, draft, published)

    @staticmethod
    async def disable(db: AsyncSession, dashboard_id: int, tenant_id: int) -> dict:
        dashboard = await CustomDashboardRepository.get_by_id(
            db,
            dashboard_id,
            tenant_id,
            for_update=True,
        )
        if dashboard is None:
            raise NotFoundError("Custom dashboard not found")
        if dashboard.status == "draft":
            raise ConflictError("Draft dashboard cannot be disabled")
        await CustomDashboardRepository.update_dashboard(db, dashboard, {"status": "disabled"})
        await db.commit()
        return await CustomDashboardService.get_by_id(db, dashboard_id, tenant_id)

    @staticmethod
    async def enable(db: AsyncSession, dashboard_id: int, tenant_id: int) -> dict:
        dashboard = await CustomDashboardRepository.get_by_id(
            db,
            dashboard_id,
            tenant_id,
            for_update=True,
        )
        if dashboard is None:
            raise NotFoundError("Custom dashboard not found")
        if dashboard.status != "disabled":
            raise ConflictError("Only disabled dashboards can be enabled")
        published = await CustomDashboardRepository.get_version(
            db,
            dashboard_id,
            tenant_id,
            "published",
        )
        if published is None:
            raise ConflictError("Dashboard has no published version")
        await CustomDashboardRepository.update_dashboard(db, dashboard, {"status": "published"})
        await db.commit()
        return await CustomDashboardService.get_by_id(db, dashboard_id, tenant_id)

    @staticmethod
    async def copy(
        db: AsyncSession,
        dashboard_id: int,
        tenant_id: int,
        data: CustomDashboardCopyRequest,
    ) -> dict:
        await CustomDashboardService._ensure_dashboard_quota(db, tenant_id)
        source = await CustomDashboardRepository.get_by_id(db, dashboard_id, tenant_id)
        if source is None:
            raise NotFoundError("Custom dashboard not found")
        draft = await CustomDashboardRepository.get_version(
            db,
            dashboard_id,
            tenant_id,
            "draft",
        )
        if draft is None:
            raise NotFoundError("Custom dashboard draft not found")
        name = data.name or await CustomDashboardService._next_copy_name(
            db,
            tenant_id,
            draft.name,
        )
        create_data = CustomDashboardCreate(
            name=name,
            slug=data.slug,
            description=draft.description,
            icon=draft.icon,
            filters=draft.filters,
            components=draft.components,
        )
        return await CustomDashboardService.create(db, tenant_id, create_data)

    @staticmethod
    async def delete(db: AsyncSession, dashboard_id: int, tenant_id: int) -> None:
        dashboard = await CustomDashboardRepository.get_by_id(
            db,
            dashboard_id,
            tenant_id,
            for_update=True,
        )
        if dashboard is None:
            raise NotFoundError("Custom dashboard not found")
        await CustomDashboardRepository.delete(db, dashboard)
        await db.commit()

    @staticmethod
    async def reorder(db: AsyncSession, tenant_id: int, ids: list[int]) -> None:
        matched = await CustomDashboardRepository.reorder(db, tenant_id, ids)
        if matched != len(ids):
            await db.rollback()
            raise NotFoundError("One or more custom dashboards were not found")
        await db.commit()

    @staticmethod
    async def list_workspace(
        db: AsyncSession,
        tenant_id: int,
        keyword: str | None = None,
    ) -> dict:
        rows = await CustomDashboardRepository.list_workspace(db, tenant_id, keyword)
        items = [_workspace_list_item(dashboard, published) for dashboard, published in rows]
        return {"items": items, "total": len(items)}

    @staticmethod
    async def get_workspace_detail(
        db: AsyncSession,
        dashboard_id: int,
        tenant_id: int,
    ) -> dict:
        dashboard = await CustomDashboardRepository.get_by_id(db, dashboard_id, tenant_id)
        if dashboard is None or dashboard.status != "published":
            raise NotFoundError("Custom dashboard not found")
        published = await CustomDashboardRepository.get_version(
            db,
            dashboard_id,
            tenant_id,
            "published",
        )
        if published is None or dashboard.published_at is None:
            raise NotFoundError("Custom dashboard not found")
        tenant_settings = await SystemSettingsService.get_settings(db, tenant_id)
        return {
            **_workspace_list_item(dashboard, published),
            "revision": published.revision,
            "timezone": tenant_settings.default_timezone,
            "filters": published.filters,
            "components": [_public_component(component) for component in published.components],
        }

    @staticmethod
    async def find_field_references(
        db: AsyncSession,
        tenant_id: int,
        field_ref: str,
    ) -> list[dict]:
        rows = await CustomDashboardRepository.list_versions_for_field_reference_check(
            db,
            tenant_id,
        )
        references = []
        for dashboard, version in rows:
            if _contains_field_reference(version.filters, field_ref) or _contains_field_reference(
                version.components,
                field_ref,
            ):
                references.append(
                    {
                        "dashboard_id": dashboard.id,
                        "dashboard_name": version.name,
                        "version_kind": version.kind,
                    }
                )
        return references

    @staticmethod
    async def _ensure_dashboard_quota(db: AsyncSession, tenant_id: int) -> None:
        count = await CustomDashboardRepository.count_for_tenant(db, tenant_id)
        if count >= MAX_DASHBOARDS_PER_TENANT:
            raise ValidationError("Dashboard quota exceeded")

    @staticmethod
    async def _next_copy_name(
        db: AsyncSession,
        tenant_id: int,
        source_name: str,
    ) -> str:
        base = f"{source_name} 副本"[:80]
        candidate = base
        suffix = 2
        while await CustomDashboardRepository.get_by_name(db, tenant_id, candidate):
            suffix_text = f" {suffix}"
            candidate = f"{base[: 80 - len(suffix_text)]}{suffix_text}"
            suffix += 1
        return candidate


def _snapshot_values(snapshot: DashboardSnapshotInput) -> dict:
    data = snapshot.model_dump(mode="json")
    return {
        "name": data["name"],
        "description": data["description"],
        "icon": data["icon"],
        "filters": data["filters"],
        "components": data["components"],
    }


def _version_data(
    dashboard: CustomDashboard,
    kind: str,
    *,
    revision: int,
    snapshot: DashboardSnapshotInput,
) -> dict:
    return {
        "tenant_id": dashboard.tenant_id,
        "dashboard_id": dashboard.id,
        "kind": kind,
        "revision": revision,
        **_snapshot_values(snapshot),
    }


def _validate_stored_snapshot(version: CustomDashboardVersion) -> None:
    try:
        DashboardSnapshotInput.model_validate(
            {
                "name": version.name,
                "description": version.description,
                "icon": version.icon,
                "filters": version.filters,
                "components": version.components,
            }
        )
    except PydanticValidationError as exc:
        raise ValidationError(
            "Dashboard draft validation failed",
            details={"errors": exc.errors(include_url=False)},
        ) from exc


def _validate_component_code(components: list[dict]) -> None:
    for component in components:
        try:
            validate_code(str(component.get("code") or ""))
        except CodeValidationError as exc:
            raise ValidationError(
                "Dashboard component code validation failed",
                details={
                    "component_id": component.get("id"),
                    "line": exc.line,
                    "message": exc.message,
                },
            ) from exc


def _list_item(
    dashboard: CustomDashboard,
    draft: CustomDashboardVersion,
) -> dict:
    return {
        "id": dashboard.id,
        "name": draft.name,
        "slug": dashboard.slug,
        "description": draft.description,
        "icon": draft.icon,
        "status": dashboard.status,
        "sort_order": dashboard.sort_order,
        "component_count": len(draft.components),
        "published_at": dashboard.published_at,
        "updated_at": dashboard.updated_at,
    }


def _detail(
    dashboard: CustomDashboard,
    draft: CustomDashboardVersion,
    published: CustomDashboardVersion | None,
) -> dict:
    return {
        **_list_item(dashboard, draft),
        "draft": {
            "revision": draft.revision,
            "name": draft.name,
            "description": draft.description,
            "icon": draft.icon,
            "filters": draft.filters,
            "components": draft.components,
            "updated_at": draft.updated_at,
        },
        "published_revision": published.revision if published else None,
    }


def _workspace_list_item(
    dashboard: CustomDashboard,
    published: CustomDashboardVersion,
) -> dict:
    return {
        "id": dashboard.id,
        "name": published.name,
        "slug": dashboard.slug,
        "description": published.description,
        "icon": published.icon,
        "sort_order": dashboard.sort_order,
        "component_count": len(published.components),
        "published_at": dashboard.published_at,
    }


def _public_component(component: dict) -> dict:
    return {key: value for key, value in component.items() if key != "code"}


def _contains_field_reference(value: object, field_ref: str) -> bool:
    if isinstance(value, str):
        pattern = rf"(?<![a-zA-Z0-9_]){re.escape(field_ref)}(?![a-zA-Z0-9_])"
        return re.search(pattern, value) is not None
    if isinstance(value, dict):
        return any(
            _contains_field_reference(key, field_ref)
            or _contains_field_reference(item, field_ref)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_field_reference(item, field_ref) for item in value)
    return False
