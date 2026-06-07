"""
Ticket workflow service — CRUD, graph versioning, ordering, and validation.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.ticket_workflow_repository import TicketWorkflowRepository
from app.repositories.ticket_workflow_version_repository import TicketWorkflowVersionRepository
from app.schemas.ticket_workflow import TicketWorkflowCreate, TicketWorkflowUpdate
from app.schemas.ticket_workflow_graph import (
    BranchNode,
    GraphError,
    GraphValidationResult,
    TicketWorkflowGraph,
    WorkflowCondition,
    default_graph,
)
from app.services.fd_field_definition_service import FdFieldDefinitionService


NO_VALUE_OPERATORS = {"is_empty", "is_not_empty", "changed", "not_changed"}
EVENT_OPERATORS = {"changed", "not_changed"}
EVENT_SCOPES = {"before"}

FIELD_OPERATORS_BY_TYPE: dict[str, set[str]] = {
    "single_line_text": {"is_empty", "is_not_empty", "eq", "ne", "contains", "not_contains", "starts_with", "ends_with"},
    "multi_line_text": {"is_empty", "is_not_empty", "eq", "ne", "contains", "not_contains", "starts_with", "ends_with"},
    "email": {"is_empty", "is_not_empty", "eq", "ne", "contains", "not_contains", "starts_with", "ends_with"},
    "phone": {"is_empty", "is_not_empty", "eq", "ne", "contains", "not_contains", "starts_with", "ends_with"},
    "url": {"is_empty", "is_not_empty", "eq", "ne", "contains", "not_contains", "starts_with", "ends_with"},
    "rich_text": {"is_empty", "is_not_empty", "contains", "not_contains"},
    "number": {"is_empty", "is_not_empty", "eq", "ne", "gt", "gte", "lt", "lte", "between"},
    "date": {"is_empty", "is_not_empty", "eq", "ne", "gt", "gte", "lt", "lte", "between"},
    "time": {"is_empty", "is_not_empty", "eq", "ne", "gt", "gte", "lt", "lte", "between"},
    "datetime": {"is_empty", "is_not_empty", "eq", "ne", "gt", "gte", "lt", "lte", "between"},
    "single_select": {"is_empty", "is_not_empty", "eq", "ne", "in", "not_in"},
    "single_select_tree": {"is_empty", "is_not_empty", "eq", "ne", "in", "not_in"},
    "multi_select": {"is_empty", "is_not_empty"},
    "multi_select_tree": {"is_empty", "is_not_empty"},
    "file": {"is_empty", "is_not_empty"},
    "user_select": {"is_empty", "is_not_empty", "eq", "ne", "in", "not_in"},
    "organization_select": {"is_empty", "is_not_empty", "eq", "ne", "in", "not_in"},
    "employee_select": {"is_empty", "is_not_empty", "eq", "ne", "in", "not_in"},
    "group_select": {"is_empty", "is_not_empty", "eq", "ne", "in", "not_in"},
}

WRITABLE_SYSTEM_FIELD_KEYS = {
    "title",
    "description",
    "status",
    "priority",
    "assignee",
    "assignee_group",
    "user_id",
}


class TicketWorkflowService:
    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 20,
        keyword: str | None = None,
        include_deleted: bool = False,
    ) -> dict:
        rows, total = await TicketWorkflowRepository.get_paginated(
            db,
            tenant_id,
            page,
            per_page,
            keyword,
            include_deleted,
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        return {
            "items": [_workflow_list_item(row) for row in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def get_by_id(db: AsyncSession, workflow_id: int, tenant_id: int) -> dict:
        row = await TicketWorkflowRepository.get_by_id(db, workflow_id, tenant_id)
        if not row:
            raise NotFoundError("Ticket workflow not found")
        return _workflow_detail(row)

    @staticmethod
    async def create(
        db: AsyncSession,
        tenant_id: int,
        actor: dict,
        data: TicketWorkflowCreate,
    ) -> dict:
        max_sort = await TicketWorkflowRepository.get_max_sort_order(db, tenant_id)
        row = await TicketWorkflowRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "name": data.name,
                "description": data.description,
                "enabled": data.enabled,
                "sort_order": max_sort + 1,
            },
        )
        version = await TicketWorkflowVersionRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "workflow_id": row.id,
                "version_no": 1,
                "graph_json": default_graph(),
                "created_by_actor_type": actor.get("actor_type"),
                "created_by_actor_id": actor.get("actor_id"),
                "created_by_actor_name": actor.get("actor_name"),
            },
        )
        row.current_version_id = version.id
        await db.commit()
        await db.refresh(row)
        return await TicketWorkflowService.get_by_id(db, row.id, tenant_id)

    @staticmethod
    async def update(
        db: AsyncSession,
        workflow_id: int,
        tenant_id: int,
        actor: dict,
        data: TicketWorkflowUpdate,
    ) -> dict:
        row = await TicketWorkflowRepository.get_by_id(
            db,
            workflow_id,
            tenant_id,
            for_update=data.graph_json is not None,
        )
        if not row:
            raise NotFoundError("Ticket workflow not found")

        changes: dict[str, Any] = {}
        if data.name is not None:
            changes["name"] = data.name
        if data.description is not None:
            changes["description"] = data.description
        if data.enabled is not None:
            changes["enabled"] = data.enabled

        if data.graph_json is not None:
            errors = await TicketWorkflowService._validate_graph(db, tenant_id, data.graph_json)
            if errors:
                raise ValidationError(
                    "Graph validation failed",
                    details={"errors": [e.model_dump() for e in errors]},
                )
            latest = await TicketWorkflowVersionRepository.get_latest_version_no(
                db,
                workflow_id,
                tenant_id,
            )
            version = await TicketWorkflowVersionRepository.create(
                db,
                {
                    "tenant_id": tenant_id,
                    "workflow_id": workflow_id,
                    "version_no": latest + 1,
                    "graph_json": data.graph_json.model_dump(mode="json"),
                    "created_by_actor_type": actor.get("actor_type"),
                    "created_by_actor_id": actor.get("actor_id"),
                    "created_by_actor_name": actor.get("actor_name"),
                },
            )
            changes["current_version_id"] = version.id

        if changes:
            await TicketWorkflowRepository.update(db, row, changes)
        return await TicketWorkflowService.get_by_id(db, workflow_id, tenant_id)

    @staticmethod
    async def delete(db: AsyncSession, workflow_id: int, tenant_id: int) -> None:
        row = await TicketWorkflowRepository.get_by_id(db, workflow_id, tenant_id)
        if not row:
            raise NotFoundError("Ticket workflow not found")
        await TicketWorkflowRepository.soft_delete(db, row)

    @staticmethod
    async def reorder(db: AsyncSession, tenant_id: int, ids: list[int]) -> None:
        await TicketWorkflowRepository.reorder(db, tenant_id, ids)

    @staticmethod
    async def validate(
        db: AsyncSession,
        tenant_id: int,
        graph: TicketWorkflowGraph,
    ) -> GraphValidationResult:
        errors = await TicketWorkflowService._validate_graph(db, tenant_id, graph)
        return GraphValidationResult(ok=not errors, errors=errors)

    @staticmethod
    async def list_versions(
        db: AsyncSession,
        workflow_id: int,
        tenant_id: int,
        limit: int = 50,
    ) -> dict:
        row = await TicketWorkflowRepository.get_by_id(db, workflow_id, tenant_id)
        if not row:
            raise NotFoundError("Ticket workflow not found")
        versions = await TicketWorkflowVersionRepository.list_for_workflow(
            db,
            workflow_id,
            tenant_id,
            limit,
        )
        return {
            "items": [
                {
                    "id": version.id,
                    "version_no": version.version_no,
                    "comment": version.comment,
                    "is_current": row.current_version_id == version.id,
                    "created_at": version.created_at,
                    "created_by_actor_name": version.created_by_actor_name,
                }
                for version in versions
            ],
            "current_version_no": row.current_version.version_no if row.current_version else None,
        }

    @staticmethod
    async def get_version(
        db: AsyncSession,
        workflow_id: int,
        version_no: int,
        tenant_id: int,
    ) -> dict:
        row = await TicketWorkflowRepository.get_by_id(db, workflow_id, tenant_id)
        if not row:
            raise NotFoundError("Ticket workflow not found")
        version = await TicketWorkflowVersionRepository.get_by_version_no(
            db,
            workflow_id,
            version_no,
            tenant_id,
        )
        if not version:
            raise NotFoundError("Version not found")
        return {
            "id": version.id,
            "version_no": version.version_no,
            "graph_json": version.graph_json,
            "comment": version.comment,
            "created_at": version.created_at,
            "created_by_actor_name": version.created_by_actor_name,
            "is_current": row.current_version_id == version.id,
        }

    @staticmethod
    async def rollback_to_version(
        db: AsyncSession,
        workflow_id: int,
        version_no: int,
        tenant_id: int,
        actor: dict,
    ) -> dict:
        row = await TicketWorkflowRepository.get_by_id(db, workflow_id, tenant_id, for_update=True)
        if not row:
            raise NotFoundError("Ticket workflow not found")
        target = await TicketWorkflowVersionRepository.get_by_version_no(
            db,
            workflow_id,
            version_no,
            tenant_id,
        )
        if not target:
            raise NotFoundError("Version not found")
        graph = TicketWorkflowGraph.model_validate(target.graph_json)
        errors = await TicketWorkflowService._validate_graph(db, tenant_id, graph)
        if errors:
            raise ValidationError(
                "Graph validation failed",
                details={"errors": [e.model_dump() for e in errors]},
            )
        latest = await TicketWorkflowVersionRepository.get_latest_version_no(
            db,
            workflow_id,
            tenant_id,
        )
        new_version = await TicketWorkflowVersionRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "version_no": latest + 1,
                "graph_json": graph.model_dump(mode="json"),
                "comment": f"Rolled back from version {version_no}",
                "created_by_actor_type": actor.get("actor_type"),
                "created_by_actor_id": actor.get("actor_id"),
                "created_by_actor_name": actor.get("actor_name"),
            },
        )
        await TicketWorkflowRepository.update(db, row, {"current_version_id": new_version.id})
        return await TicketWorkflowService.get_by_id(db, workflow_id, tenant_id)

    @staticmethod
    async def _validate_graph(
        db: AsyncSession,
        tenant_id: int,
        graph: TicketWorkflowGraph,
    ) -> list[GraphError]:
        errors: list[GraphError] = []
        node_index = {node.id: node for node in graph.nodes}

        _validate_edges(graph, node_index, errors)
        _validate_dag_and_reachability(graph, node_index, errors)

        unified = await FdFieldDefinitionService.get_unified_list(
            db,
            tenant_id,
            "ticket",
            include_metadata=True,
        )
        fields_by_id, fields_by_key = _build_field_indexes(unified["items"])
        trigger = next(node for node in graph.nodes if node.type == "trigger")
        trigger_event_types = set(trigger.data.event_types)

        _validate_conditions(
            trigger.id,
            "data.conditions",
            trigger.data.conditions,
            trigger_event_types,
            fields_by_id,
            fields_by_key,
            errors,
        )

        for node in graph.nodes:
            if node.type == "branch":
                for branch in node.data.branches:
                    if branch.is_default and branch.conditions:
                        errors.append(GraphError(
                            node_id=node.id,
                            field=f"branches[{branch.id}].conditions",
                            code="default_branch_has_conditions",
                            message="Default branch must not define conditions",
                        ))
                    _validate_conditions(
                        node.id,
                        f"branches[{branch.id}].conditions",
                        branch.conditions,
                        trigger_event_types,
                        fields_by_id,
                        fields_by_key,
                        errors,
                    )
            if node.type == "update_record":
                for index, operation in enumerate(node.data.operations):
                    field = _resolve_update_field(operation, fields_by_id, fields_by_key)
                    if not field:
                        errors.append(GraphError(
                            node_id=node.id,
                            field=f"operations[{index}].target",
                            code="target_field_not_found",
                            message="Update target field is not available",
                        ))
                        continue
                    if not _is_writable_field(field):
                        errors.append(GraphError(
                            node_id=node.id,
                            field=f"operations[{index}].target",
                            code="target_field_not_writable",
                            message=f"Field '{field.get('name')}' is not writable by workflow",
                        ))
                        continue
                    if operation.action == "set":
                        _validate_write_value(node.id, f"operations[{index}].value", field, operation.value, errors)

        return errors


def _workflow_list_item(row) -> dict:
    graph = row.current_version.graph_json if row.current_version else None
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "enabled": row.enabled,
        "sort_order": row.sort_order,
        "current_version_no": row.current_version.version_no if row.current_version else None,
        "trigger_event_types": _trigger_event_types(graph),
        "updated_at": row.updated_at,
    }


def _workflow_detail(row) -> dict:
    graph = row.current_version.graph_json if row.current_version else default_graph()
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "enabled": row.enabled,
        "sort_order": row.sort_order,
        "current_version_no": row.current_version.version_no if row.current_version else None,
        "trigger_event_types": _trigger_event_types(graph),
        "graph_json": graph,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _trigger_event_types(graph: dict | None) -> list[str]:
    if not graph:
        return []
    for node in graph.get("nodes", []):
        if node.get("type") == "trigger":
            data = node.get("data") or {}
            event_types = data.get("event_types")
            return list(event_types) if isinstance(event_types, list) else []
    return []


def _validate_edges(graph: TicketWorkflowGraph, node_index: dict[str, Any], errors: list[GraphError]) -> None:
    edge_ids = [edge.id for edge in graph.edges]
    if len(set(edge_ids)) != len(edge_ids):
        errors.append(GraphError(code="duplicate_edge_id", message="Edge ids must be unique"))

    outgoing: dict[str, list[str]] = {}
    outlet_edge_ids: dict[tuple[str, str], str] = {}
    for edge in graph.edges:
        if edge.source not in node_index:
            errors.append(GraphError(
                field=f"edges[{edge.id}].source",
                code="edge_source_missing",
                message=f"Edge source '{edge.source}' is not a node",
            ))
            continue
        if edge.target not in node_index:
            errors.append(GraphError(
                field=f"edges[{edge.id}].target",
                code="edge_target_missing",
                message=f"Edge target '{edge.target}' is not a node",
            ))
            continue
        source = node_index[edge.source]
        outgoing.setdefault(edge.source, []).append(edge.source_handle)
        outlet_key = (edge.source, edge.source_handle)
        previous_edge_id = outlet_edge_ids.get(outlet_key)
        if previous_edge_id is not None:
            errors.append(GraphError(
                node_id=edge.source,
                field=f"outlet:{edge.source_handle}",
                code="duplicate_outlet_edge",
                message=(
                    f"Node '{edge.source}' outlet '{edge.source_handle}' must have only one outgoing edge "
                    f"(duplicates: '{previous_edge_id}', '{edge.id}')"
                ),
            ))
        else:
            outlet_edge_ids[outlet_key] = edge.id
        allowed = _allowed_handles_for(source)
        if allowed is not None and edge.source_handle not in allowed:
            errors.append(GraphError(
                node_id=edge.source,
                field=f"edges[{edge.id}].source_handle",
                code="invalid_source_handle",
                message=f"Invalid source handle '{edge.source_handle}' for node '{edge.source}'",
            ))

    for node in graph.nodes:
        handles = set(outgoing.get(node.id, []))
        if node.type in ("trigger", "update_record") and "next" not in handles:
            errors.append(GraphError(
                node_id=node.id,
                field="outlet:next",
                code="missing_next_edge",
                message=f"Node '{node.id}' must connect its next outlet",
            ))
        if node.type == "branch":
            for branch in node.data.branches:
                if branch.id not in handles:
                    errors.append(GraphError(
                        node_id=node.id,
                        field=f"outlet:{branch.id}",
                        code="missing_branch_edge",
                        message=f"Branch '{branch.name}' has no outgoing edge",
                    ))
        if node.type == "end" and handles:
            errors.append(GraphError(
                node_id=node.id,
                code="end_has_outgoing_edge",
                message="End node cannot have outgoing edges",
            ))


def _allowed_handles_for(node) -> set[str] | None:
    if node.type == "branch":
        return {branch.id for branch in node.data.branches}
    if node.type in ("trigger", "update_record"):
        return {"next"}
    if node.type == "end":
        return set()
    return None


def _validate_dag_and_reachability(
    graph: TicketWorkflowGraph,
    node_index: dict[str, Any],
    errors: list[GraphError],
) -> None:
    adjacency: dict[str, list[str]] = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        if edge.source in node_index and edge.target in node_index:
            adjacency.setdefault(edge.source, []).append(edge.target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for target in adjacency.get(node_id, []):
            if dfs(target):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    if any(dfs(node.id) for node in graph.nodes if node.id not in visited):
        errors.append(GraphError(code="graph_has_cycle", message="Workflow graph must be a DAG"))

    trigger_id = next(node.id for node in graph.nodes if node.type == "trigger")
    reachable = _reachable_from(trigger_id, adjacency)
    for node in graph.nodes:
        if node.id not in reachable:
            errors.append(GraphError(
                node_id=node.id,
                code="node_unreachable",
                message=f"Node '{node.id}' is not reachable from trigger",
            ))
    if not any(node.type == "end" and node.id in reachable for node in graph.nodes):
        errors.append(GraphError(code="end_not_reachable", message="At least one end node must be reachable"))

    end_ids = {node.id for node in graph.nodes if node.type == "end"}
    for node in graph.nodes:
        if node.id not in reachable or node.type == "end":
            continue
        node_reachable = _reachable_from(node.id, adjacency)
        if not (node_reachable & end_ids):
            errors.append(GraphError(
                node_id=node.id,
                code="no_path_to_end",
                message=f"Node '{node.id}' has no path to an end node",
            ))


def _reachable_from(start: str, adjacency: dict[str, list[str]]) -> set[str]:
    seen = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for target in adjacency.get(current, []):
            if target in seen:
                continue
            seen.add(target)
            queue.append(target)
    return seen


def _build_field_indexes(fields: list[dict]) -> tuple[dict[int, dict], dict[str, dict]]:
    fields_by_id = {
        int(field["id"]): field
        for field in fields
        if field.get("id") is not None and field.get("status", "active") == "active"
    }
    fields_by_key = {
        str(field["key"]): field
        for field in fields
        if field.get("key") is not None and field.get("status", "active") == "active"
    }
    return fields_by_id, fields_by_key


def _validate_conditions(
    node_id: str,
    field_path: str,
    conditions: list[WorkflowCondition],
    trigger_event_types: set[str],
    fields_by_id: dict[int, dict],
    fields_by_key: dict[str, dict],
    errors: list[GraphError],
) -> None:
    for index, condition in enumerate(conditions):
        path = f"{field_path}[{index}]"
        field = _resolve_condition_field(condition, fields_by_id, fields_by_key)
        if not field:
            errors.append(GraphError(
                node_id=node_id,
                field=path,
                code="condition_field_not_found",
                message="Condition field is not available",
            ))
            continue
        operator = condition.operator.lower()
        allowed = set(FIELD_OPERATORS_BY_TYPE.get(str(field.get("field_type")), set())) | EVENT_OPERATORS
        if operator not in allowed:
            errors.append(GraphError(
                node_id=node_id,
                field=f"{path}.operator",
                code="operator_not_supported",
                message=f"Operator '{condition.operator}' is not supported for field type '{field.get('field_type')}'",
            ))
            continue
        if operator in EVENT_OPERATORS and "update" not in trigger_event_types:
            errors.append(GraphError(
                node_id=node_id,
                field=f"{path}.operator",
                code="event_operator_requires_update",
                message="changed/not_changed can only be used when trigger includes update",
            ))
        if condition.value_scope in EVENT_SCOPES and "update" not in trigger_event_types:
            errors.append(GraphError(
                node_id=node_id,
                field=f"{path}.value_scope",
                code="before_scope_requires_update",
                message="before value scope can only be used when trigger includes update",
            ))
        if operator in EVENT_OPERATORS and condition.value_scope not in (None, "current"):
            errors.append(GraphError(
                node_id=node_id,
                field=f"{path}.value_scope",
                code="event_operator_disallows_scope",
                message="changed/not_changed cannot use value_scope",
            ))
        _validate_condition_value(node_id, path, field, operator, condition.value, errors)


def _resolve_condition_field(
    condition: WorkflowCondition,
    fields_by_id: dict[int, dict],
    fields_by_key: dict[str, dict],
) -> dict | None:
    if condition.field_id is not None:
        return fields_by_id.get(condition.field_id)
    if condition.field_key is not None:
        return fields_by_key.get(condition.field_key)
    return None


def _resolve_update_field(operation, fields_by_id: dict[int, dict], fields_by_key: dict[str, dict]) -> dict | None:
    if operation.target_field_id is not None:
        return fields_by_id.get(operation.target_field_id)
    if operation.target_field_key is not None:
        return fields_by_key.get(operation.target_field_key)
    return None


def _validate_condition_value(
    node_id: str,
    path: str,
    field: dict,
    operator: str,
    value: Any,
    errors: list[GraphError],
) -> None:
    if operator in NO_VALUE_OPERATORS:
        if value is not None:
            errors.append(GraphError(
                node_id=node_id,
                field=f"{path}.value",
                code="operator_disallows_value",
                message=f"Operator '{operator}' does not accept a value",
            ))
        return
    if value is None or value == "":
        errors.append(GraphError(
            node_id=node_id,
            field=f"{path}.value",
            code="condition_value_required",
            message=f"Operator '{operator}' requires a value",
        ))
        return
    if operator == "between":
        if isinstance(value, dict) and {"min", "max"} <= set(value.keys()):
            return
        if isinstance(value, list) and len(value) == 2:
            return
        errors.append(GraphError(
            node_id=node_id,
            field=f"{path}.value",
            code="between_value_invalid",
            message="between requires {min, max} or a two-item list",
        ))
        return
    if operator in ("in", "not_in") and not isinstance(value, list):
        errors.append(GraphError(
            node_id=node_id,
            field=f"{path}.value",
            code="list_value_required",
            message=f"Operator '{operator}' requires a list value",
        ))
        return
    _validate_choice_values(node_id, f"{path}.value", field, operator, value, errors)


def _validate_choice_values(
    node_id: str,
    path: str,
    field: dict,
    operator: str,
    value: Any,
    errors: list[GraphError],
) -> None:
    field_type = str(field.get("field_type"))
    if field_type not in {"single_select", "single_select_tree"}:
        return
    candidate_values = _choice_values(field)
    if not candidate_values:
        return
    values = value if operator in ("in", "not_in") and isinstance(value, list) else [value]
    invalid = [item for item in values if str(item) not in candidate_values]
    if invalid:
        errors.append(GraphError(
            node_id=node_id,
            field=path,
            code="choice_value_invalid",
            message="Condition value is not in the field options",
        ))


def _choice_values(field: dict) -> set[str]:
    values: set[str] = set()
    for option in field.get("options") or []:
        value = _get_attr(option, "value")
        active = _get_attr(option, "is_active", True)
        if active and value is not None:
            values.add(str(value))
    for node in field.get("tree_nodes") or []:
        value = _get_attr(node, "value")
        active = _get_attr(node, "is_active", True)
        if active and value is not None:
            values.add(str(value))
    return values


def _get_attr(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _is_writable_field(field: dict) -> bool:
    if field.get("source") == "metadata":
        return False
    type_config = field.get("type_config") or {}
    if type_config.get("readonly"):
        return False
    if field.get("source") == "custom":
        return field.get("id") is not None
    key = field.get("key")
    if key is not None:
        return str(key) in WRITABLE_SYSTEM_FIELD_KEYS
    return False


def _validate_write_value(
    node_id: str,
    path: str,
    field: dict,
    value: Any,
    errors: list[GraphError],
) -> None:
    field_type = str(field.get("field_type"))
    if value is None or value == "":
        return
    if field_type in {"single_select", "single_select_tree"}:
        candidate_values = _choice_values(field)
        if candidate_values and str(value) not in candidate_values:
            errors.append(GraphError(
                node_id=node_id,
                field=path,
                code="write_choice_value_invalid",
                message="Write value is not in the field options",
            ))
    if field_type in {"multi_select", "multi_select_tree"}:
        if not isinstance(value, list):
            errors.append(GraphError(
                node_id=node_id,
                field=path,
                code="write_list_value_required",
                message="Multi-select write value must be a list",
            ))
            return
        candidate_values = _choice_values(field)
        if candidate_values:
            invalid = [item for item in value if str(item) not in candidate_values]
            if invalid:
                errors.append(GraphError(
                    node_id=node_id,
                    field=path,
                    code="write_choice_value_invalid",
                    message="Write value contains inactive or unknown options",
                ))
