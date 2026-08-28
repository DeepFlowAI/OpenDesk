"""Managed short-session orchestration for custom dashboard component runs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import text

from app.configs.settings import settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.libs.dashboard_sandbox import create_dashboard_sandbox
from app.libs.dashboard_sandbox.base import (
    SandboxExecutionError,
    SandboxLimits,
)
from app.repositories.custom_dashboard_repository import CustomDashboardRepository
from app.schemas.custom_dashboard_run import CustomDashboardRunRequest
from app.schemas.permission import EffectivePrincipal
from app.services.custom_dashboard_query_service import (
    CustomDashboardQueryService,
    DashboardField,
)
from app.services.custom_dashboard_resource_service import CustomDashboardResourceService
from app.services.data_scope_service import DataScopeService
from app.services.system_settings_service import SystemSettingsService


_HTML_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_FORBIDDEN_OUTPUT_STRINGS = ("http://", "https://", "javascript:", "data:")


@dataclass(frozen=True)
class _RunSnapshot:
    dashboard_id: int
    dashboard_name: str
    version_kind: str
    revision: int
    component: dict
    filter_config: list[dict]
    timezone_name: str
    field_catalog_version: str
    field_catalog: dict[str, DashboardField]
    peer_employee_ids: list[int]


class CustomDashboardRunService:
    """Run one component without retaining a DB session during external waits."""

    @staticmethod
    async def run_managed(
        redis: aioredis.Redis,
        principal: EffectivePrincipal,
        *,
        dashboard_id: int,
        request: CustomDashboardRunRequest,
        preview: bool,
    ) -> dict:
        if principal.user_id is None:
            raise ForbiddenError("Employee identity is required")
        snapshot = await CustomDashboardRunService._load_snapshot(
            principal,
            dashboard_id=dashboard_id,
            component_id=request.component_id,
            preview=preview,
            component_override=(
                request.component_override.model_dump(mode="json")
                if preview and request.component_override is not None
                else None
            ),
            filter_config_override=(
                [item.model_dump(mode="json") for item in request.filter_config_override]
                if preview and request.filter_config_override is not None
                else None
            ),
        )
        request_id = str(request.request_id)
        page_run_id = str(request.page_run_id)

        async def is_cancelled() -> bool:
            return await CustomDashboardResourceService.is_cancelled(
                redis,
                tenant_id=principal.tenant_id,
                employee_id=principal.user_id,
                request_id=request_id,
                page_run_id=page_run_id,
            )

        if await is_cancelled():
            return _failure_response(request.request_id, "cancelled", "Run was cancelled")

        component_key = (
            f"{principal.tenant_id}:{dashboard_id}:{snapshot.revision}:{request.component_id}"
        )
        if not preview and await CustomDashboardResourceService.is_cooling_down(
            redis,
            component_key,
        ):
            return _failure_response(
                request.request_id,
                "cooldown",
                "Component is cooling down after repeated resource limit failures",
                status="cooldown",
            )

        cache_key = CustomDashboardResourceService.build_cache_key(
            {
                "tenant_id": principal.tenant_id,
                "dashboard_id": dashboard_id,
                "version_kind": snapshot.version_kind,
                "revision": snapshot.revision,
                "component_id": request.component_id,
                "code": snapshot.component["code"],
                "filter_values": request.filter_values,
                "employee_id": principal.user_id,
                "permissions": sorted(principal.permissions),
                "data_scopes": principal.data_scopes,
                "group_ids": sorted(principal.group_ids),
                "field_catalog_version": snapshot.field_catalog_version,
            }
        )
        if not preview and not request.bypass_cache:
            cached = await CustomDashboardResourceService.get_cache(redis, cache_key)
            if cached is not None:
                cached["request_id"] = request.request_id
                cached["cached"] = True
                return cached

        if request.bypass_cache:
            await CustomDashboardResourceService.enforce_refresh_cooldown(
                redis,
                tenant_id=principal.tenant_id,
                employee_id=principal.user_id,
                dashboard_id=dashboard_id,
            )
        await CustomDashboardResourceService.enforce_miss_rate(
            redis,
            tenant_id=principal.tenant_id,
            employee_id=principal.user_id,
        )
        lease = await CustomDashboardResourceService.acquire_execution(
            redis,
            tenant_id=principal.tenant_id,
            dashboard_id=dashboard_id,
            cancel_checker=is_cancelled,
        )
        try:
            async def query_handler(method: str, params: dict) -> object:
                await CustomDashboardResourceService.consume_page_query(
                    redis,
                    tenant_id=principal.tenant_id,
                    employee_id=principal.user_id,
                    page_run_id=page_run_id,
                )
                async with AsyncSessionLocal() as db:
                    # Transaction-local statement timeout keeps a slow component query
                    # from holding a shared pool connection past its budget.
                    await db.execute(
                        text("SELECT set_config('statement_timeout', :timeout_ms, true)"),
                        {"timeout_ms": str(settings.DASHBOARD_QUERY_STATEMENT_TIMEOUT_MS)},
                    )
                    return await CustomDashboardQueryService.execute(
                        db,
                        principal,
                        method=method,
                        params=params,
                        filter_config=snapshot.filter_config,
                        filter_values=request.filter_values,
                        timezone_name=snapshot.timezone_name,
                        catalog=snapshot.field_catalog,
                        peer_ids=snapshot.peer_employee_ids,
                    )

            sandbox = create_dashboard_sandbox()
            sandbox_result = await sandbox.execute(
                code=str(snapshot.component["code"]),
                context={
                    "tenant_timezone": snapshot.timezone_name,
                    "viewer_id": principal.user_id,
                    "dashboard_id": dashboard_id,
                    "dashboard_name": snapshot.dashboard_name,
                    "version_kind": snapshot.version_kind,
                    "revision": snapshot.revision,
                },
                filters=request.filter_values,
                query_handler=query_handler,
                cancel_checker=is_cancelled,
                limits=SandboxLimits(
                    wall_seconds=settings.DASHBOARD_RUN_WALL_SECONDS,
                    cpu_seconds=settings.DASHBOARD_RUN_CPU_SECONDS,
                    memory_mb=settings.DASHBOARD_RUN_MEMORY_MB,
                    max_queries=settings.DASHBOARD_RUN_MAX_QUERIES,
                    max_log_bytes=settings.DASHBOARD_RUN_MAX_LOG_BYTES,
                ),
            )
            output = _validate_output(sandbox_result.output)
            response = {
                "request_id": request.request_id,
                "status": "success",
                "result": output,
                "cached": False,
                "error_code": None,
                "message": None,
                "error_line": None,
                "logs": sandbox_result.logs if preview else None,
                "logs_truncated": sandbox_result.truncated if preview else False,
                "query_count": sandbox_result.query_count,
                "completed_at": datetime.now(timezone.utc),
            }
            await CustomDashboardResourceService.record_success(redis, component_key)
            if not preview:
                cache_payload = _json_ready_response(response)
                await CustomDashboardResourceService.set_cache(redis, cache_key, cache_payload)
            return response
        except SandboxExecutionError as exc:
            if not preview and exc.code in {"resource_limit", "runtime_timeout"}:
                await CustomDashboardResourceService.record_resource_failure(redis, component_key)
            status = "cancelled" if exc.code == "cancelled" else "failed"
            return _failure_response(
                request.request_id,
                exc.code,
                exc.message,
                status=status,
                line=exc.line,
            )
        except ValidationError as exc:
            return _failure_response(
                request.request_id,
                "query_invalid",
                exc.message,
            )
        finally:
            await lease.release()

    @staticmethod
    async def cancel_run(
        redis: aioredis.Redis,
        principal: EffectivePrincipal,
        request_id: UUID,
    ) -> None:
        if principal.user_id is None:
            raise ForbiddenError("Employee identity is required")
        await CustomDashboardResourceService.cancel_run(
            redis,
            tenant_id=principal.tenant_id,
            employee_id=principal.user_id,
            request_id=str(request_id),
        )

    @staticmethod
    async def cancel_page(
        redis: aioredis.Redis,
        principal: EffectivePrincipal,
        page_run_id: UUID,
    ) -> None:
        if principal.user_id is None:
            raise ForbiddenError("Employee identity is required")
        await CustomDashboardResourceService.cancel_page(
            redis,
            tenant_id=principal.tenant_id,
            employee_id=principal.user_id,
            page_run_id=str(page_run_id),
        )

    @staticmethod
    async def _load_snapshot(
        principal: EffectivePrincipal,
        *,
        dashboard_id: int,
        component_id: str,
        preview: bool,
        component_override: dict | None = None,
        filter_config_override: list[dict] | None = None,
    ) -> _RunSnapshot:
        async with AsyncSessionLocal() as db:
            dashboard = await CustomDashboardRepository.get_by_id(
                db,
                dashboard_id,
                principal.tenant_id,
            )
            if dashboard is None:
                raise NotFoundError("Custom dashboard not found")
            kind = "draft" if preview else "published"
            if not preview and dashboard.status != "published":
                raise NotFoundError("Custom dashboard not found")
            version = await CustomDashboardRepository.get_version(
                db,
                dashboard_id,
                principal.tenant_id,
                kind,
            )
            if version is None:
                raise NotFoundError("Custom dashboard version not found")
            component = component_override or next(
                (item for item in version.components if item.get("id") == component_id),
                None,
            )
            if component is None:
                raise NotFoundError("Dashboard component not found")
            tenant_settings = await SystemSettingsService.get_settings(db, principal.tenant_id)
            catalog_version = await CustomDashboardQueryService.field_catalog_version(
                db,
                principal.tenant_id,
            )
            # Load the field catalog and scope peers once per run instead of per query.
            catalog = await CustomDashboardQueryService.field_catalog(db, principal.tenant_id)
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
            return _RunSnapshot(
                dashboard_id=dashboard_id,
                dashboard_name=version.name,
                version_kind=kind,
                revision=version.revision,
                component=dict(component),
                filter_config=(
                    filter_config_override
                    if filter_config_override is not None
                    else list(version.filters)
                ),
                timezone_name=tenant_settings.default_timezone,
                field_catalog_version=catalog_version,
                field_catalog=catalog,
                peer_employee_ids=peer_ids,
            )


def _validate_output(output: object) -> dict:
    if not isinstance(output, dict):
        raise SandboxExecutionError(
            "invalid_output",
            "Component output must be an object",
        )
    try:
        encoded = json.dumps(output, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SandboxExecutionError("invalid_output", "Component output must be JSON") from exc
    if len(encoded) > settings.DASHBOARD_RUN_MAX_OUTPUT_BYTES:
        raise SandboxExecutionError("output_too_large", "Component output exceeds 1MB")
    _reject_external_content(output)

    output_type = output.get("type")
    if output_type == "metric":
        if not isinstance(output.get("value"), (int, float)) or isinstance(output.get("value"), bool):
            raise SandboxExecutionError("invalid_output", "Metric value must be numeric")
        if output.get("format", "number") not in {
            "number",
            "percent",
            "currency",
            "duration",
        }:
            raise SandboxExecutionError("invalid_output", "Unsupported metric format")
    elif output_type == "echarts":
        option = output.get("option")
        if not isinstance(option, dict):
            raise SandboxExecutionError("invalid_output", "ECharts option must be an object")
        if _count_echarts_points(option) > 2000:
            raise SandboxExecutionError("too_many_points", "ECharts output exceeds 2000 data points")
    elif output_type == "table":
        columns = output.get("columns")
        rows = output.get("rows")
        if not isinstance(columns, list) or not isinstance(rows, list):
            raise SandboxExecutionError("invalid_output", "Table columns and rows must be arrays")
        if len(columns) > 20 or len(rows) > 200:
            raise SandboxExecutionError("invalid_output", "Table exceeds 20 columns or 200 rows")
        for row in rows:
            values = row.values() if isinstance(row, dict) else row if isinstance(row, list) else None
            if values is None or any(not _is_scalar(value) for value in values):
                raise SandboxExecutionError("invalid_output", "Table cells must be scalar values")
    elif output_type == "markdown":
        content = output.get("content")
        if not isinstance(content, str) or len(content.encode("utf-8")) > 10 * 1024:
            raise SandboxExecutionError("invalid_output", "Markdown must be at most 10KB")
        if _HTML_RE.search(content):
            raise SandboxExecutionError("invalid_output", "Markdown HTML is not allowed")
    else:
        raise SandboxExecutionError("invalid_output", "Unsupported component output type")
    return output


def _reject_external_content(value: object) -> None:
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _FORBIDDEN_OUTPUT_STRINGS):
            raise SandboxExecutionError("invalid_output", "External URLs are not allowed")
        if _HTML_RE.search(value):
            raise SandboxExecutionError("invalid_output", "HTML output is not allowed")
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_external_content(key)
            _reject_external_content(item)
    elif isinstance(value, list):
        for item in value:
            _reject_external_content(item)


def _count_echarts_points(value: object, *, parent_key: str | None = None) -> int:
    if isinstance(value, dict):
        return sum(_count_echarts_points(item, parent_key=str(key)) for key, item in value.items())
    if isinstance(value, list):
        own = len(value) if parent_key == "data" else 0
        return own + sum(_count_echarts_points(item) for item in value)
    return 0


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _failure_response(
    request_id: UUID,
    code: str,
    message: str,
    *,
    status: str = "failed",
    line: int | None = None,
) -> dict:
    return {
        "request_id": request_id,
        "status": status,
        "result": None,
        "cached": False,
        "error_code": code,
        "message": message,
        "error_line": line,
        "logs": None,
        "logs_truncated": False,
        "query_count": 0,
        "completed_at": datetime.now(timezone.utc),
    }


def _json_ready_response(response: dict) -> dict:
    return {
        **response,
        "request_id": str(response["request_id"]),
        "completed_at": response["completed_at"].isoformat(),
    }
