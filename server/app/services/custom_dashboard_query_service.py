"""Validated product query surface exposed to custom dashboard components."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import ValidationError
from app.models.ticket import Ticket
from app.repositories.dashboard_ticket_query_repository import (
    DashboardTicketQueryRepository,
    SYSTEM_TICKET_COLUMNS,
    build_filter_clause,
)
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService


MAX_CANDIDATE_TICKETS = 200_000
MAX_GROUPS = 100
MAX_DETAIL_ROWS = 200
MAX_DETAIL_COLUMNS = 20
MAX_TIMESERIES_DAYS = 366

GROUPABLE_TYPES = {
    "single_select",
    "single_select_tree",
    "multi_select",
    "multi_select_tree",
    "boolean",
    "employee_select",
    "group_select",
}
NUMERIC_TYPES = {"number"}
DATE_TYPES = {"date", "datetime"}
DETAIL_EXCLUDED_TYPES = {"multi_line_text", "rich_text", "file"}


@dataclass(frozen=True)
class DashboardField:
    """Authorized mapping from a stable product field reference to a Ticket column."""

    ref: str
    name: str
    field_type: str
    column: ColumnElement
    status: str = "active"
    options: dict[str, str] | None = None

    @property
    def multi_select(self) -> bool:
        return self.field_type in {"multi_select", "multi_select_tree"}


class CustomDashboardQueryService:
    """Validate component query parameters and enforce ticket data scope."""

    @staticmethod
    async def field_catalog_version(db: AsyncSession, tenant_id: int) -> str:
        return await DashboardTicketQueryRepository.field_catalog_version(db, tenant_id)

    @staticmethod
    async def field_catalog(db: AsyncSession, tenant_id: int) -> dict[str, DashboardField]:
        """Load the authorized field catalog once so a run can reuse it across queries."""
        return await CustomDashboardQueryService._field_catalog(db, tenant_id)

    @staticmethod
    async def execute(
        db: AsyncSession,
        principal: EffectivePrincipal,
        *,
        method: str,
        params: dict,
        filter_config: list[dict],
        filter_values: dict,
        timezone_name: str,
        catalog: dict[str, DashboardField] | None = None,
        peer_ids: list[int] | None = None,
    ) -> object:
        if catalog is None:
            catalog = await CustomDashboardQueryService._field_catalog(db, principal.tenant_id)
        where = params.get("where") or {}
        if not isinstance(where, dict):
            raise ValidationError("where must be an object")
        merged_where = dict(where)
        if params.get("inherit_filters", True):
            merged_where = _merge_public_filters(merged_where, filter_config, filter_values)

        if peer_ids is None:
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        clauses = []
        scope_clause = DataScopeService.build_ticket_predicate(principal, peer_ids)
        if scope_clause is not None:
            clauses.append(scope_clause)
        clauses.extend(_where_clauses(merged_where, catalog, timezone_name))

        if method == "count":
            count = await DashboardTicketQueryRepository.count(
                db,
                principal.tenant_id,
                clauses,
            )
            if count > MAX_CANDIDATE_TICKETS:
                raise ValidationError("Query candidate range exceeds 200000 tickets")
            return count

        candidate_count = await DashboardTicketQueryRepository.candidate_count(
            db,
            principal.tenant_id,
            clauses,
        )
        if candidate_count > MAX_CANDIDATE_TICKETS:
            raise ValidationError("Query candidate range exceeds 200000 tickets")

        if method == "group_by":
            return await CustomDashboardQueryService._group_by(
                db,
                principal,
                params,
                clauses,
                catalog,
            )
        if method == "timeseries":
            return await CustomDashboardQueryService._timeseries(
                db,
                principal,
                params,
                clauses,
                catalog,
                merged_where,
                timezone_name,
            )
        if method == "list":
            return await CustomDashboardQueryService._list_rows(
                db,
                principal,
                params,
                clauses,
                catalog,
            )
        raise ValidationError("Unsupported ticket query method")

    @staticmethod
    async def _field_catalog(
        db: AsyncSession,
        tenant_id: int,
    ) -> dict[str, DashboardField]:
        catalog = _system_catalog()
        definitions = await DashboardTicketQueryRepository.list_field_definitions(db, tenant_id)
        for definition in definitions:
            column = getattr(Ticket, definition.slot_column, None)
            if column is None:
                continue
            options: dict[str, str] = {}
            for option in getattr(definition, "options", []) or []:
                label = option.label
                if not option.is_active:
                    label = f"{label}（已停用）"
                options[str(option.value)] = label
            for option in (definition.type_config or {}).get("options", []):
                if isinstance(option, dict) and option.get("value") is not None:
                    options.setdefault(str(option["value"]), str(option.get("label") or option["value"]))
            catalog[f"custom:{definition.field_key}"] = DashboardField(
                ref=f"custom:{definition.field_key}",
                name=definition.name,
                field_type=definition.field_type,
                column=column,
                status=definition.status,
                options=options,
            )
        return catalog

    @staticmethod
    async def _group_by(
        db: AsyncSession,
        principal: EffectivePrincipal,
        params: dict,
        clauses: list[ColumnElement],
        catalog: dict[str, DashboardField],
    ) -> list[dict]:
        group_field = _require_field(catalog, params.get("group_field"))
        if group_field.ref not in {
            "system:status",
            "system:priority",
            "system:assignee",
            "system:assignee_group",
            "system:created_by",
        } and group_field.field_type not in GROUPABLE_TYPES:
            raise ValidationError("Field does not support grouping")
        aggregate = str(params.get("aggregate") or "count")
        aggregate_field = _optional_numeric_field(catalog, params.get("value_field"), aggregate)
        limit = min(max(int(params.get("limit") or MAX_GROUPS), 1), MAX_GROUPS)
        rows = await DashboardTicketQueryRepository.group_by(
            db,
            principal.tenant_id,
            clauses,
            group_column=group_field.column,
            aggregate_column=aggregate_field.column if aggregate_field else None,
            aggregate=aggregate,
            multi_select=group_field.multi_select,
            limit=limit,
        )
        for row in rows:
            key = row["key"]
            row["label"] = (
                "未填写"
                if key in {None, ""}
                else (group_field.options or {}).get(str(key), str(key))
            )
        return rows

    @staticmethod
    async def _timeseries(
        db: AsyncSession,
        principal: EffectivePrincipal,
        params: dict,
        clauses: list[ColumnElement],
        catalog: dict[str, DashboardField],
        where: dict,
        timezone_name: str,
    ) -> list[dict]:
        date_ref = params.get("date_field") or "system:created_at"
        date_field = _require_field(catalog, date_ref)
        if date_field.field_type not in DATE_TYPES:
            raise ValidationError("Timeseries date field must be a date or datetime")
        _validate_timeseries_range(where, date_field.ref)
        granularity = str(params.get("granularity") or "day")
        if granularity not in {"day", "week", "month"}:
            raise ValidationError("Unsupported timeseries granularity")
        aggregate = str(params.get("aggregate") or "count")
        aggregate_field = _optional_numeric_field(catalog, params.get("value_field"), aggregate)
        return await DashboardTicketQueryRepository.timeseries(
            db,
            principal.tenant_id,
            clauses,
            date_column=date_field.column,
            aggregate_column=aggregate_field.column if aggregate_field else None,
            aggregate=aggregate,
            granularity=granularity,
            timezone_name=timezone_name,
            limit=MAX_TIMESERIES_DAYS + 2,
        )

    @staticmethod
    async def _list_rows(
        db: AsyncSession,
        principal: EffectivePrincipal,
        params: dict,
        clauses: list[ColumnElement],
        catalog: dict[str, DashboardField],
    ) -> list[dict]:
        raw_fields = params.get("fields") or []
        if not isinstance(raw_fields, list) or not raw_fields:
            raise ValidationError("fields must be a non-empty array")
        if len(raw_fields) > MAX_DETAIL_COLUMNS:
            raise ValidationError("Detail query supports at most 20 fields")
        fields = [_require_field(catalog, ref) for ref in raw_fields]
        if any(field.field_type in DETAIL_EXCLUDED_TYPES for field in fields):
            raise ValidationError("One or more fields do not support detail output")
        limit = int(params.get("limit") or MAX_DETAIL_ROWS)
        if limit < 1 or limit > MAX_DETAIL_ROWS:
            raise ValidationError("Detail query limit must be between 1 and 200")
        return await DashboardTicketQueryRepository.list_rows(
            db,
            principal.tenant_id,
            clauses,
            fields=[(field.ref, field.column) for field in fields],
            limit=limit,
        )


def _system_catalog() -> dict[str, DashboardField]:
    types = {
        "ticket_number": "single_line_text",
        "title": "single_line_text",
        "status": "single_select",
        "priority": "single_select",
        "assignee": "employee_select",
        "assignee_group": "group_select",
        "created_by": "employee_select",
        "created_at": "datetime",
        "updated_at": "datetime",
    }
    catalog: dict[str, DashboardField] = {}
    for key, column in SYSTEM_TICKET_COLUMNS.items():
        field = DashboardField(
            ref=f"system:{key}",
            name=key,
            field_type=types[key],
            column=column,
        )
        catalog[field.ref] = field
        if key in {"created_at", "updated_at"}:
            catalog[f"metadata:{key}"] = DashboardField(
                ref=f"metadata:{key}",
                name=key,
                field_type="datetime",
                column=column,
            )
    return catalog


def _require_field(
    catalog: dict[str, DashboardField],
    ref: object,
) -> DashboardField:
    if not isinstance(ref, str) or ref not in catalog:
        raise ValidationError(f"Field reference is not available: {ref}")
    return catalog[ref]


def _optional_numeric_field(
    catalog: dict[str, DashboardField],
    ref: object,
    aggregate: str,
) -> DashboardField | None:
    if aggregate == "count":
        return None
    if aggregate not in {"sum", "avg", "max", "min"}:
        raise ValidationError("Unsupported aggregate")
    field = _require_field(catalog, ref)
    if field.field_type not in NUMERIC_TYPES:
        raise ValidationError("Aggregate value field must be numeric")
    return field


def _merge_public_filters(where: dict, config: list[dict], values: dict) -> dict:
    merged = {key: dict(value) if isinstance(value, dict) else value for key, value in where.items()}
    config_by_id = {item.get("id"): item for item in config if isinstance(item, dict)}
    for filter_id, value in values.items():
        item = config_by_id.get(filter_id)
        if not item:
            continue
        if item.get("type") == "date_range" and isinstance(value, dict):
            start = value.get("start")
            end = value.get("end")
            for field_ref in item.get("field_keys") or []:
                operators = merged.setdefault(field_ref, {})
                if not isinstance(operators, dict):
                    operators = {"eq": operators}
                    merged[field_ref] = operators
                if start is not None:
                    operators["gte"] = start
                if end is not None:
                    operators["lte"] = end
        if item.get("type") == "field_option" and item.get("field_key"):
            selected = value if isinstance(value, list) else [value]
            selected = [item for item in selected if item not in {None, ""}]
            if selected:
                merged[item["field_key"]] = {"in": selected}
    return merged


def _where_clauses(
    where: dict,
    catalog: dict[str, DashboardField],
    timezone_name: str,
) -> list[ColumnElement]:
    clauses: list[ColumnElement] = []
    for field_ref, condition in where.items():
        field = _require_field(catalog, field_ref)
        operators = condition if isinstance(condition, dict) else {"eq": condition}
        for operator, raw_value in operators.items():
            value = _coerce_value(field, raw_value, str(operator), timezone_name)
            clauses.append(
                build_filter_clause(
                    field.column,
                    str(operator),
                    value,
                    multi_select=field.multi_select,
                )
            )
    return clauses


def _coerce_value(
    field: DashboardField,
    value: object,
    operator: str,
    timezone_name: str,
) -> object:
    if isinstance(value, list):
        return [_coerce_value(field, item, operator, timezone_name) for item in value]
    try:
        if field.field_type == "datetime" and isinstance(value, str):
            if len(value) == 10:
                local_date = date.fromisoformat(value)
                try:
                    tenant_timezone = ZoneInfo(timezone_name)
                except ZoneInfoNotFoundError:
                    tenant_timezone = timezone.utc
                boundary = time.max if operator in {"lte", "<="} else time.min
                return datetime.combine(local_date, boundary, tenant_timezone).astimezone(timezone.utc)
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if field.field_type == "date" and isinstance(value, str):
            return date.fromisoformat(value[:10])
        if field.field_type == "number" and value is not None:
            return Decimal(str(value))
        if field.field_type in {"employee_select", "group_select"} and value is not None:
            return int(value)
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValidationError(f"Invalid value for field {field.ref}") from exc
    return value


def _validate_timeseries_range(where: dict, field_ref: str) -> None:
    condition = where.get(field_ref)
    if not isinstance(condition, dict):
        raise ValidationError("Timeseries requires a bounded date range")
    start = condition.get("gte", condition.get("gt"))
    end = condition.get("lte", condition.get("lt"))
    if start is None or end is None:
        raise ValidationError("Timeseries requires a bounded date range")
    try:
        start_date = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        end_date = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("Invalid timeseries date range") from exc
    if end_date < start_date or (end_date - start_date).days > MAX_TIMESERIES_DAYS:
        raise ValidationError("Timeseries date range must not exceed 366 days")
