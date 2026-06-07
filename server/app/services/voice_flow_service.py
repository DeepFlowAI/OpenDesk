"""
Voice flow service — manages the flow header and its versioned graph.

Each save with `graph_json` bumps version_no by 1 and updates
`voice_flows.current_version_id`. Metadata-only updates (name/description/
enabled) don't bump the version.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.fd_field_definition import FdFieldDefinition
from app.repositories.audio_asset_repository import AudioAssetRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.employee_group_repository import EmployeeGroupRepository
from app.repositories.service_hours_repository import ServiceHoursRepository
from app.repositories.voice_flow_repository import VoiceFlowRepository
from app.repositories.voice_flow_system_variable_repository import (
    VoiceFlowSystemVariableRepository,
)
from app.repositories.voice_flow_version_repository import VoiceFlowVersionRepository
from app.schemas.voice_flow import VoiceFlowCreate, VoiceFlowUpdate
from app.schemas.voice_flow_graph import (
    AudioPrompt,
    GraphError,
    GraphValidationResult,
    VoiceFlowGraph,
    default_graph,
)


# Node type → set of allowed source_handle values for edges.
# `next` is used by start / play / assign_queue.
# `success`, `no_input`, `no_match`, `error` are collect outlets.
# condition node validates handles dynamically (group ids + "default").
# assign_queue extra outlet: `timeout`.
_FIXED_HANDLES_BY_TYPE: dict[str, set[str]] = {
    "start": {"next"},
    "play": {"next"},
    "collect": {"success", "no_input", "no_match", "error"},
    # `assign_queue` only exposes `timeout`: a successful bridge ends the
    # workflow (the user is now talking to the agent through the kernel,
    # nothing more for the orchestrator to drive), so a `next` outlet
    # would be unreachable and misleading.
    "assign_queue": {"timeout"},
    "hangup": set(),
}


class VoiceFlowService:

    # ─────────────────── List / Select / Get ───────────────────

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int = 1,
        per_page: int = 10,
        keyword: str | None = None,
        include_deleted: bool = False,
    ) -> dict:
        rows, total = await VoiceFlowRepository.get_paginated(
            db, tenant_id, page, per_page, keyword, include_deleted
        )
        pages = (total + per_page - 1) // per_page if total > 0 else 0
        items = [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "enabled": r.enabled,
                "current_version_no": r.current_version.version_no if r.current_version else None,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    @staticmethod
    async def list_for_select(db: AsyncSession, tenant_id: int) -> dict:
        rows = await VoiceFlowRepository.list_for_select(db, tenant_id)
        return {"items": [{"id": r.id, "name": r.name} for r in rows]}

    @staticmethod
    async def get_by_id(db: AsyncSession, flow_id: int, tenant_id: int) -> dict:
        row = await VoiceFlowRepository.get_by_id(db, flow_id, tenant_id)
        if not row:
            raise NotFoundError("Voice flow not found")
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "enabled": row.enabled,
            "current_version_no": row.current_version.version_no if row.current_version else None,
            "graph_json": row.current_version.graph_json if row.current_version else default_graph(),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    # ─────────────────── Create / Update / Delete ───────────────────

    @staticmethod
    async def create(
        db: AsyncSession, tenant_id: int, actor: dict, data: VoiceFlowCreate
    ) -> dict:
        # 1. Create header row (current_version_id = NULL)
        payload = {
            "tenant_id": tenant_id,
            "name": data.name,
            "description": data.description,
            "enabled": data.enabled,
        }
        row = await VoiceFlowRepository.create(db, payload)

        # 2. Seed v1 with default graph
        version = await VoiceFlowVersionRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "voice_flow_id": row.id,
                "version_no": 1,
                "graph_json": default_graph(),
                "created_by_actor_type": actor.get("actor_type"),
                "created_by_actor_id": actor.get("actor_id"),
                "created_by_actor_name": actor.get("actor_name"),
            },
        )
        # 3. Point flow to the new version
        row.current_version_id = version.id
        await db.commit()
        await db.refresh(row)
        return await VoiceFlowService.get_by_id(db, row.id, tenant_id)

    @staticmethod
    async def update(
        db: AsyncSession,
        flow_id: int,
        tenant_id: int,
        actor: dict,
        data: VoiceFlowUpdate,
    ) -> dict:
        row = await VoiceFlowRepository.get_by_id(db, flow_id, tenant_id)
        if not row:
            raise NotFoundError("Voice flow not found")

        # Metadata patch
        meta_changes: dict = {}
        if data.name is not None:
            meta_changes["name"] = data.name
        if data.description is not None:
            meta_changes["description"] = data.description
        if data.enabled is not None:
            meta_changes["enabled"] = data.enabled

        # Graph patch → new version
        if data.graph_json is not None:
            errors = await VoiceFlowService._validate_graph(db, tenant_id, data.graph_json)
            if errors:
                raise ValidationError(
                    "Graph validation failed",
                    details={"errors": [e.model_dump() for e in errors]},
                )
            latest = await VoiceFlowVersionRepository.get_latest_version_no(
                db, flow_id, tenant_id
            )
            version = await VoiceFlowVersionRepository.create(
                db,
                {
                    "tenant_id": tenant_id,
                    "voice_flow_id": flow_id,
                    "version_no": latest + 1,
                    "graph_json": data.graph_json.model_dump(),
                    "created_by_actor_type": actor.get("actor_type"),
                    "created_by_actor_id": actor.get("actor_id"),
                    "created_by_actor_name": actor.get("actor_name"),
                },
            )
            meta_changes["current_version_id"] = version.id

        if meta_changes:
            await VoiceFlowRepository.update(db, row, meta_changes)

        return await VoiceFlowService.get_by_id(db, flow_id, tenant_id)

    @staticmethod
    async def delete(db: AsyncSession, flow_id: int, tenant_id: int) -> None:
        row = await VoiceFlowRepository.get_by_id(db, flow_id, tenant_id)
        if not row:
            raise NotFoundError("Voice flow not found")
        await VoiceFlowRepository.soft_delete(db, row)

    # ─────────────────── Versions ───────────────────

    @staticmethod
    async def list_versions(
        db: AsyncSession, flow_id: int, tenant_id: int, limit: int = 50
    ) -> dict:
        row = await VoiceFlowRepository.get_by_id(db, flow_id, tenant_id)
        if not row:
            raise NotFoundError("Voice flow not found")
        versions = await VoiceFlowVersionRepository.list_for_flow(db, flow_id, tenant_id, limit)
        return {
            "items": [
                {
                    "id": v.id,
                    "version_no": v.version_no,
                    "comment": v.comment,
                    "is_current": (row.current_version_id == v.id),
                    "created_at": v.created_at,
                    "created_by_actor_name": v.created_by_actor_name,
                }
                for v in versions
            ],
            "current_version_no": row.current_version.version_no if row.current_version else None,
        }

    @staticmethod
    async def get_version(
        db: AsyncSession, flow_id: int, version_no: int, tenant_id: int
    ) -> dict:
        row = await VoiceFlowRepository.get_by_id(db, flow_id, tenant_id)
        if not row:
            raise NotFoundError("Voice flow not found")
        ver = await VoiceFlowVersionRepository.get_by_version_no(
            db, flow_id, version_no, tenant_id
        )
        if not ver:
            raise NotFoundError("Version not found")
        return {
            "id": ver.id,
            "version_no": ver.version_no,
            "graph_json": ver.graph_json,
            "comment": ver.comment,
            "created_at": ver.created_at,
            "created_by_actor_name": ver.created_by_actor_name,
            "is_current": (row.current_version_id == ver.id),
        }

    @staticmethod
    async def rollback_to_version(
        db: AsyncSession,
        flow_id: int,
        version_no: int,
        tenant_id: int,
        actor: dict,
    ) -> dict:
        row = await VoiceFlowRepository.get_by_id(db, flow_id, tenant_id)
        if not row:
            raise NotFoundError("Voice flow not found")
        target = await VoiceFlowVersionRepository.get_by_version_no(
            db, flow_id, version_no, tenant_id
        )
        if not target:
            raise NotFoundError("Version not found")
        latest = await VoiceFlowVersionRepository.get_latest_version_no(
            db, flow_id, tenant_id
        )
        new_version = await VoiceFlowVersionRepository.create(
            db,
            {
                "tenant_id": tenant_id,
                "voice_flow_id": flow_id,
                "version_no": latest + 1,
                "graph_json": target.graph_json,
                "comment": f"Rolled back from version {version_no}",
                "created_by_actor_type": actor.get("actor_type"),
                "created_by_actor_id": actor.get("actor_id"),
                "created_by_actor_name": actor.get("actor_name"),
            },
        )
        await VoiceFlowRepository.update(db, row, {"current_version_id": new_version.id})
        return await VoiceFlowService.get_by_id(db, flow_id, tenant_id)

    # ─────────────────── Validate-only ───────────────────

    @staticmethod
    async def validate(
        db: AsyncSession, tenant_id: int, graph: VoiceFlowGraph
    ) -> GraphValidationResult:
        errors = await VoiceFlowService._validate_graph(db, tenant_id, graph)
        return GraphValidationResult(ok=not errors, errors=errors)

    # ─────────────────── Graph validation logic ───────────────────

    @staticmethod
    async def _validate_graph(
        db: AsyncSession, tenant_id: int, graph: VoiceFlowGraph
    ) -> list[GraphError]:
        errors: list[GraphError] = []

        node_index = {n.id: n for n in graph.nodes}

        # Edges reference existing nodes
        for edge in graph.edges:
            if edge.source not in node_index:
                errors.append(GraphError(
                    field=f"edges[{edge.id}].source",
                    code="edge_source_missing",
                    message=f"Edge '{edge.id}' source '{edge.source}' is not a node",
                ))
            if edge.target not in node_index:
                errors.append(GraphError(
                    field=f"edges[{edge.id}].target",
                    code="edge_target_missing",
                    message=f"Edge '{edge.id}' target '{edge.target}' is not a node",
                ))

        # source_handle must match the source node's outlet semantics
        outgoing_by_source: dict[str, set[str]] = {}
        for edge in graph.edges:
            outgoing_by_source.setdefault(edge.source, set()).add(edge.source_handle)
            src = node_index.get(edge.source)
            if src is None:
                continue
            allowed = _allowed_handles_for(src)
            if allowed is not None and edge.source_handle not in allowed:
                errors.append(GraphError(
                    node_id=src.id,
                    field=f"edges[{edge.id}].source_handle",
                    code="invalid_source_handle",
                    message=(
                        f"Node '{src.id}' (type={src.type}) does not have outlet "
                        f"'{edge.source_handle}'. Allowed: {sorted(allowed)}"
                    ),
                ))

        # Required outlets per node type. `assign_queue` is deliberately
        # absent: a successful bridge ends the workflow, and `timeout` is
        # optional (an unconnected timeout outlet just makes the call hang
        # up naturally if no agent answers in time).
        for node in graph.nodes:
            outs = outgoing_by_source.get(node.id, set())
            if node.type in ("start", "play") and "next" not in outs:
                errors.append(GraphError(
                    node_id=node.id, field="outlet:next",
                    code="missing_next_edge",
                    message=f"Node '{node.id}' ({node.type}) must connect its 'next' outlet",
                ))
            if node.type == "collect" and "success" not in outs:
                errors.append(GraphError(
                    node_id=node.id, field="outlet:success",
                    code="missing_success_edge",
                    message=f"Collect node '{node.id}' must connect its 'success' outlet",
                ))
            if node.type == "condition":
                group_ids = {g.id for g in node.data.groups}
                # condition allowed handles = group ids + default
                if "default" not in outs:
                    errors.append(GraphError(
                        node_id=node.id, field="outlet:default",
                        code="missing_default_edge",
                        message=f"Condition node '{node.id}' must connect its 'default' outlet",
                    ))
                for gid in group_ids:
                    if gid not in outs:
                        errors.append(GraphError(
                            node_id=node.id, field=f"outlet:{gid}",
                            code="missing_group_edge",
                            message=(
                                f"Condition node '{node.id}' group '{gid}' has no outgoing edge"
                            ),
                        ))

        # Cross-entity references: queue targets, audio_asset_id, service_hours.id
        await _validate_external_refs(db, tenant_id, graph, errors)

        # Variable reachability for condition references
        _validate_variable_reachability(graph, errors)

        return errors


# ────────────────── Helpers ──────────────────


def _allowed_handles_for(node) -> set[str] | None:
    if node.type == "condition":
        return {g.id for g in node.data.groups} | {"default"}
    return _FIXED_HANDLES_BY_TYPE.get(node.type)


async def _validate_external_refs(
    db, tenant_id: int, graph: VoiceFlowGraph, errors: list[GraphError]
) -> None:
    asset_ids: list[int] = []
    group_targets: list[tuple[str, int]] = []
    employee_targets: list[tuple[str, int]] = []
    user_field_targets: list[tuple[str, int]] = []
    sh_ids: list[int] = []

    for node in graph.nodes:
        if node.type in ("play", "collect"):
            if isinstance(node.data.prompt, AudioPrompt):
                asset_ids.append(node.data.prompt.asset_id)
        if node.type == "hangup" and node.data.pre_play and isinstance(node.data.pre_play, AudioPrompt):
            asset_ids.append(node.data.pre_play.asset_id)
        if node.type == "assign_queue":
            for target in node.data.queue_targets:
                if target.queue_type == "user_field":
                    user_field_targets.append((node.id, target.queue_id))
                elif target.queue_type == "employee_group":
                    group_targets.append((node.id, target.queue_id))
                elif target.queue_type == "employee":
                    employee_targets.append((node.id, target.queue_id))
        if node.type == "condition":
            for g in node.data.groups:
                for c in g.conditions:
                    if c.operator in ("time_in", "time_not_in") and isinstance(c.value, int):
                        sh_ids.append(c.value)

    if asset_ids:
        existing = await AudioAssetRepository.exists_ids(db, list(set(asset_ids)), tenant_id)
        missing = set(asset_ids) - existing
        for aid in missing:
            errors.append(GraphError(
                code="audio_asset_not_found",
                message=f"Audio asset id {aid} does not exist or has been deleted",
            ))

    for qid in {queue_id for _, queue_id in group_targets}:
        group = await EmployeeGroupRepository.get_by_id(db, qid)
        if group is None or group.tenant_id != tenant_id:
            node_id = next((nid for nid, target_id in group_targets if target_id == qid), None)
            errors.append(GraphError(
                node_id=node_id,
                field="queue_targets",
                code="queue_not_found",
                message=f"Employee group id {qid} not found in this tenant",
            ))

    for eid in {employee_id for _, employee_id in employee_targets}:
        employee = await EmployeeRepository.get_by_id(db, eid)
        if employee is None or employee.tenant_id != tenant_id or not employee.is_active:
            node_id = next((nid for nid, target_id in employee_targets if target_id == eid), None)
            errors.append(GraphError(
                node_id=node_id,
                field="queue_targets",
                code="queue_not_found",
                message=f"Employee id {eid} not found in this tenant",
            ))

    if user_field_targets:
        field_ids = {field_id for _, field_id in user_field_targets}
        q = select(FdFieldDefinition.id).where(
            FdFieldDefinition.tenant_id == tenant_id,
            FdFieldDefinition.id.in_(field_ids),
            FdFieldDefinition.domain == "user",
            FdFieldDefinition.status == "active",
            FdFieldDefinition.field_type.in_(["employee_select", "group_select"]),
        )
        existing_field_ids = set((await db.execute(q)).scalars().all())
        for fid in field_ids - existing_field_ids:
            node_id = next((nid for nid, target_id in user_field_targets if target_id == fid), None)
            errors.append(GraphError(
                node_id=node_id,
                field="queue_targets",
                code="queue_field_not_found",
                message=(
                    f"User field id {fid} is not available for queue routing"
                ),
            ))

    for sid in set(sh_ids):
        sh = await ServiceHoursRepository.get_by_id(db, sid)
        if sh is None or sh.tenant_id != tenant_id:
            errors.append(GraphError(
                code="service_hours_not_found",
                message=f"Service hours id {sid} not found in this tenant",
            ))


def _validate_variable_reachability(graph: VoiceFlowGraph, errors: list[GraphError]) -> None:
    """
    For every variable name referenced in a condition node, ensure it's either
    a `sys.*` system variable OR produced by an upstream collect node reachable
    from the start node.

    Upstream is computed by reverse BFS from each condition node through edges.
    """
    # Build adjacency: target -> [source]
    rev_adj: dict[str, list[str]] = {}
    for e in graph.edges:
        rev_adj.setdefault(e.target, []).append(e.source)

    node_index = {n.id: n for n in graph.nodes}

    # Produced-variable map
    produces: dict[str, str] = {}
    for n in graph.nodes:
        if n.type == "collect":
            produces[n.data.output_variable] = n.id

    for n in graph.nodes:
        if n.type != "condition":
            continue
        for g in n.data.groups:
            for cond in g.conditions:
                vname = cond.variable
                if vname.startswith("sys."):
                    continue  # syntactic check; existence validated against seed
                # find producing node
                producer = produces.get(vname)
                if producer is None:
                    errors.append(GraphError(
                        node_id=n.id,
                        field=f"groups[{g.id}].conditions.variable",
                        code="variable_not_produced",
                        message=f"Variable '{vname}' is not produced by any collect node",
                    ))
                    continue
                # check reachability: producer must be an ancestor of n
                if not _is_ancestor(producer, n.id, rev_adj):
                    errors.append(GraphError(
                        node_id=n.id,
                        field=f"groups[{g.id}].conditions.variable",
                        code="variable_not_reachable",
                        message=(
                            f"Variable '{vname}' is produced by node '{producer}', "
                            f"which is not on any path leading to condition node '{n.id}'"
                        ),
                    ))


def _is_ancestor(ancestor: str, descendant: str, rev_adj: dict[str, list[str]]) -> bool:
    """BFS upstream from `descendant` through `rev_adj` (target → sources)."""
    visited = {descendant}
    queue = [descendant]
    while queue:
        cur = queue.pop()
        for src in rev_adj.get(cur, []):
            if src == ancestor:
                return True
            if src not in visited:
                visited.add(src)
                queue.append(src)
    return False
