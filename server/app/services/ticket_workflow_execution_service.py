"""
Runtime executor for ticket workflows.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ticket_repository import SYSTEM_FIELD_MAP
from app.repositories.ticket_workflow_repository import TicketWorkflowRepository
from app.schemas.ticket_workflow_graph import (
    BranchNode,
    TicketWorkflowGraph,
    WorkflowCondition,
)
from app.services.fd_field_definition_service import FdFieldDefinitionService, coerce_slot_value


logger = logging.getLogger(__name__)


@dataclass
class WorkflowExecutionResult:
    updates: dict[str, Any] = field(default_factory=dict)
    field_labels: dict[str, str] = field(default_factory=dict)


@dataclass
class RuntimeField:
    ref: str
    label: str
    field_type: str
    column: str
    slot_column: str | None = None


class TicketWorkflowExecutionService:
    @staticmethod
    async def apply(
        db: AsyncSession,
        tenant_id: int,
        event_type: str,
        before_data: dict[str, Any],
        current_data: dict[str, Any],
    ) -> WorkflowExecutionResult:
        workflows = await TicketWorkflowRepository.list_enabled_for_execution(db, tenant_id)
        if not workflows:
            return WorkflowExecutionResult()

        fields_by_id, fields_by_key = await _load_runtime_fields(db, tenant_id)
        result = WorkflowExecutionResult()
        working = dict(current_data)

        for workflow in workflows:
            if not workflow.current_version:
                continue
            try:
                graph = TicketWorkflowGraph.model_validate(workflow.current_version.graph_json)
                workflow_working = dict(working)
                writes = await _execute_graph(
                    graph,
                    event_type,
                    before_data,
                    workflow_working,
                    fields_by_id,
                    fields_by_key,
                )
            except Exception:
                _log_workflow_execution_error(workflow, tenant_id, event_type)
                continue
            for column, value in writes.items():
                working[column] = value
                result.updates[column] = value
            for column in writes:
                label = _label_for_column(column, fields_by_id, fields_by_key)
                if label:
                    result.field_labels[column] = label

        return result


def _log_workflow_execution_error(workflow, tenant_id: int, event_type: str) -> None:
    version = getattr(workflow, "current_version", None)
    logger.exception(
        "Ticket workflow execution skipped tenant_id=%s workflow_id=%s version_id=%s version_no=%s event_type=%s",
        tenant_id,
        getattr(workflow, "id", None),
        getattr(version, "id", None),
        getattr(version, "version_no", None),
        event_type,
    )


async def _load_runtime_fields(db: AsyncSession, tenant_id: int) -> tuple[dict[int, RuntimeField], dict[str, RuntimeField]]:
    unified = await FdFieldDefinitionService.get_unified_list(
        db,
        tenant_id,
        "ticket",
        include_metadata=True,
    )
    by_id: dict[int, RuntimeField] = {}
    by_key: dict[str, RuntimeField] = {}
    for item in unified["items"]:
        if item.get("status", "active") != "active":
            continue
        key = item.get("key")
        field_id = item.get("id")
        slot_column = item.get("slot_column")
        if item.get("source") == "custom" and field_id is not None and slot_column:
            runtime = RuntimeField(
                ref=f"id:{field_id}",
                label=str(item.get("name") or field_id),
                field_type=str(item.get("field_type")),
                column=str(slot_column),
                slot_column=str(slot_column),
            )
            by_id[int(field_id)] = runtime
        elif key:
            column = SYSTEM_FIELD_MAP.get(str(key))
            if not column:
                continue
            by_key[str(key)] = RuntimeField(
                ref=f"key:{key}",
                label=str(item.get("name") or key),
                field_type=str(item.get("field_type")),
                column=column,
            )
    return by_id, by_key


async def _execute_graph(
    graph: TicketWorkflowGraph,
    event_type: str,
    before_data: dict[str, Any],
    working: dict[str, Any],
    fields_by_id: dict[int, RuntimeField],
    fields_by_key: dict[str, RuntimeField],
) -> dict[str, Any]:
    nodes = {node.id: node for node in graph.nodes}
    trigger = next(node for node in graph.nodes if node.type == "trigger")
    if event_type not in trigger.data.event_types:
        return {}
    if not _evaluate_conditions(
        trigger.data.conditions,
        trigger.data.condition_logic,
        event_type,
        before_data,
        working,
        fields_by_id,
        fields_by_key,
    ):
        return {}

    edge_by_source_handle = {
        (edge.source, edge.source_handle): edge.target
        for edge in graph.edges
    }
    writes: dict[str, Any] = {}
    current_id = edge_by_source_handle.get((trigger.id, "next"))
    visited: set[str] = {trigger.id}

    while current_id and current_id in nodes and current_id not in visited:
        visited.add(current_id)
        node = nodes[current_id]
        if node.type == "end":
            break
        if node.type == "update_record":
            for operation in node.data.operations:
                field = _resolve_update_field(operation, fields_by_id, fields_by_key)
                if not field:
                    continue
                value = None if operation.action == "clear" else operation.value
                if field.slot_column:
                    value = coerce_slot_value(field.slot_column, value)
                writes[field.column] = value
                working[field.column] = value
            current_id = edge_by_source_handle.get((node.id, "next"))
            continue
        if node.type == "branch":
            branch = _select_branch(node, event_type, before_data, working, fields_by_id, fields_by_key)
            current_id = edge_by_source_handle.get((node.id, branch.id if branch else ""))
            continue
        current_id = None

    return writes


def _select_branch(
    node: BranchNode,
    event_type: str,
    before_data: dict[str, Any],
    working: dict[str, Any],
    fields_by_id: dict[int, RuntimeField],
    fields_by_key: dict[str, RuntimeField],
):
    default_branch = None
    for branch in node.data.branches:
        if branch.is_default:
            default_branch = branch
            continue
        if _evaluate_conditions(
            branch.conditions,
            branch.condition_logic,
            event_type,
            before_data,
            working,
            fields_by_id,
            fields_by_key,
        ):
            return branch
    return default_branch


def _evaluate_conditions(
    conditions: list[WorkflowCondition],
    logic: str,
    event_type: str,
    before_data: dict[str, Any],
    working: dict[str, Any],
    fields_by_id: dict[int, RuntimeField],
    fields_by_key: dict[str, RuntimeField],
) -> bool:
    if not conditions:
        return True
    results = [
        _evaluate_condition(condition, event_type, before_data, working, fields_by_id, fields_by_key)
        for condition in conditions
    ]
    if logic == "OR":
        return any(results)
    return all(results)


def _evaluate_condition(
    condition: WorkflowCondition,
    event_type: str,
    before_data: dict[str, Any],
    working: dict[str, Any],
    fields_by_id: dict[int, RuntimeField],
    fields_by_key: dict[str, RuntimeField],
) -> bool:
    field = _resolve_condition_field(condition, fields_by_id, fields_by_key)
    if not field:
        return False
    operator = condition.operator.lower()
    before_value = before_data.get(field.column)
    current_value = working.get(field.column)

    if operator == "changed":
        return event_type == "update" and _normalize(before_value) != _normalize(current_value)
    if operator == "not_changed":
        return event_type == "update" and _normalize(before_value) == _normalize(current_value)

    left = before_value if condition.value_scope == "before" else current_value
    return _apply_operator(left, operator, condition.value)


def _resolve_condition_field(
    condition: WorkflowCondition,
    fields_by_id: dict[int, RuntimeField],
    fields_by_key: dict[str, RuntimeField],
) -> RuntimeField | None:
    if condition.field_id is not None:
        return fields_by_id.get(condition.field_id)
    if condition.field_key is not None:
        return fields_by_key.get(condition.field_key)
    return None


def _resolve_update_field(operation, fields_by_id: dict[int, RuntimeField], fields_by_key: dict[str, RuntimeField]) -> RuntimeField | None:
    if operation.target_field_id is not None:
        return fields_by_id.get(operation.target_field_id)
    if operation.target_field_key is not None:
        return fields_by_key.get(operation.target_field_key)
    return None


def _apply_operator(left: Any, operator: str, value: Any) -> bool:
    if operator == "is_empty":
        return _is_empty(left)
    if operator == "is_not_empty":
        return not _is_empty(left)
    if operator == "eq":
        return _normalize(left) == _normalize(value)
    if operator == "ne":
        return _normalize(left) != _normalize(value)
    if operator == "contains":
        return str(value) in str(left or "")
    if operator == "not_contains":
        return str(value) not in str(left or "")
    if operator == "starts_with":
        return str(left or "").startswith(str(value))
    if operator == "ends_with":
        return str(left or "").endswith(str(value))
    if operator == "in":
        return _normalize(left) in {_normalize(item) for item in value} if isinstance(value, list) else False
    if operator == "not_in":
        return _normalize(left) not in {_normalize(item) for item in value} if isinstance(value, list) else False
    if operator == "between":
        lower, upper = _between_bounds(value)
        return _compare(left, ">=", lower) and _compare(left, "<=", upper)
    if operator in {"gt", "gte", "lt", "lte"}:
        cmp_op = { "gt": ">", "gte": ">=", "lt": "<", "lte": "<=" }[operator]
        return _compare(left, cmp_op, value)
    return False


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
        return True
    return False


def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _normalize(val) for key, val in value.items()}
    return value


def _between_bounds(value: Any) -> tuple[Any, Any]:
    if isinstance(value, dict):
        return value.get("min"), value.get("max")
    if isinstance(value, list) and len(value) == 2:
        return value[0], value[1]
    return None, None


def _compare(left: Any, operator: str, right: Any) -> bool:
    if left is None or right is None:
        return False
    left_value = _coerce_comparable(left)
    right_value = _coerce_comparable(right)
    try:
        if operator == ">":
            return left_value > right_value
        if operator == ">=":
            return left_value >= right_value
        if operator == "<":
            return left_value < right_value
        if operator == "<=":
            return left_value <= right_value
    except TypeError:
        return str(left_value) > str(right_value) if operator == ">" else (
            str(left_value) >= str(right_value) if operator == ">=" else (
                str(left_value) < str(right_value) if operator == "<" else str(left_value) <= str(right_value)
            )
        )
    return False


def _coerce_comparable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception:
            return value
    return value


def _label_for_column(
    column: str,
    fields_by_id: dict[int, RuntimeField],
    fields_by_key: dict[str, RuntimeField],
) -> str | None:
    for field in fields_by_id.values():
        if field.column == column:
            return field.label
    for field in fields_by_key.values():
        if field.column == column:
            return field.label
    return None
