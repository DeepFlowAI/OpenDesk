"""Business logic for versioned call satisfaction flows."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ConflictError, NotFoundError, ValidationError
from app.models.satisfaction_flow import SatisfactionFlow, SatisfactionFlowVersion
from app.repositories.satisfaction_flow_repository import SatisfactionFlowRepository
from app.repositories.satisfaction_flow_version_repository import (
    SatisfactionFlowVersionRepository,
)
from app.schemas.satisfaction_flow import (
    SatisfactionFlowCreate,
    SatisfactionFlowSave,
    SatisfactionFlowSettings,
)
from app.schemas.satisfaction_flow_graph import (
    ConditionNode,
    GraphError,
    GraphValidationResult,
    QuestionNode,
    SatisfactionFlowGraph,
)
from app.services.audit_actor_service import AuditActorService


class SatisfactionFlowService:
    """Validate and persist tenant-scoped satisfaction flow versions."""

    @staticmethod
    def _reachable(adjacency: dict[str, list[str]], source: str, target: str) -> bool:
        pending = [source]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(adjacency.get(current, []))
        return False

    @staticmethod
    def validate_graph(graph: SatisfactionFlowGraph) -> GraphValidationResult:
        """Return structural and business validation errors for a draft graph."""

        errors: list[GraphError] = []
        node_index = {node.id: node for node in graph.nodes}
        start = next((node for node in graph.nodes if node.type == "start"), None)
        questions = [node for node in graph.nodes if node.type == "question"]
        end_nodes = [node for node in graph.nodes if node.type == "end"]

        if not questions:
            errors.append(GraphError(code="missing_question", message="At least one question is required"))
        if not end_nodes:
            errors.append(GraphError(code="missing_end", message="At least one end node is required"))

        question_names = [node.data.name for node in questions]
        duplicate_names = {name for name in question_names if question_names.count(name) > 1}
        for node in questions:
            if node.data.name in duplicate_names:
                errors.append(GraphError(
                    node_id=node.id,
                    field="data.name",
                    code="duplicate_question_name",
                    message="Question names must be unique within a flow",
                ))

        adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_index}
        outgoing: dict[str, dict[str, int]] = {node_id: {} for node_id in node_index}
        for edge in graph.edges:
            source = node_index.get(edge.source)
            target = node_index.get(edge.target)
            if source is None:
                errors.append(GraphError(
                    field="edges", code="unknown_source", message=f"Unknown source node: {edge.source}"
                ))
                continue
            if target is None:
                errors.append(GraphError(
                    node_id=edge.source,
                    field="edges",
                    code="unknown_target",
                    message=f"Unknown target node: {edge.target}",
                ))
                continue
            if target.type == "start":
                errors.append(GraphError(
                    node_id=edge.source,
                    field="edges",
                    code="edge_to_start",
                    message="Start node cannot have incoming edges",
                ))
            adjacency[edge.source].append(edge.target)
            handle_count = outgoing[edge.source].get(edge.source_handle, 0) + 1
            outgoing[edge.source][edge.source_handle] = handle_count
            if handle_count > 1:
                errors.append(GraphError(
                    node_id=edge.source,
                    field=f"outlet:{edge.source_handle}",
                    code="duplicate_outlet",
                    message="Each outlet can have only one connection",
                ))

        for node in graph.nodes:
            required: set[str]
            allowed: set[str]
            if node.type in {"start", "play"}:
                required = allowed = {"next"}
            elif node.type == "question":
                required = allowed = {"answered", "no_input", "no_match", "error"}
            elif node.type == "condition":
                allowed = {group.id for group in node.data.groups} | {"default"}
                required = allowed
            else:
                required = allowed = set()
            actual = set(outgoing[node.id])
            for handle in sorted(required - actual):
                errors.append(GraphError(
                    node_id=node.id,
                    field=f"outlet:{handle}",
                    code="missing_outlet",
                    message=f"Required outlet '{handle}' is not connected",
                ))
            for handle in sorted(actual - allowed):
                errors.append(GraphError(
                    node_id=node.id,
                    field=f"outlet:{handle}",
                    code="invalid_outlet",
                    message=f"Outlet '{handle}' is not valid for {node.type}",
                ))

        if start is not None:
            reachable: set[str] = set()
            pending = [start.id]
            while pending:
                node_id = pending.pop()
                if node_id in reachable:
                    continue
                reachable.add(node_id)
                pending.extend(adjacency.get(node_id, []))
            for node in graph.nodes:
                if node.id not in reachable:
                    errors.append(GraphError(
                        node_id=node.id,
                        code="unreachable_node",
                        message="Node is not reachable from start",
                    ))

            colors: dict[str, int] = {}

            def visit(node_id: str) -> None:
                colors[node_id] = 1
                for next_id in adjacency.get(node_id, []):
                    if colors.get(next_id) == 1:
                        errors.append(GraphError(
                            node_id=node_id,
                            field="edges",
                            code="cycle_detected",
                            message="Satisfaction flows cannot contain cycles",
                        ))
                    elif colors.get(next_id, 0) == 0:
                        visit(next_id)
                colors[node_id] = 2

            visit(start.id)

        for node in graph.nodes:
            if not isinstance(node, ConditionNode):
                continue
            for group in node.data.groups:
                for index, condition in enumerate(group.conditions):
                    referenced = node_index.get(condition.question_node_id)
                    field = f"data.groups.{group.id}.conditions.{index}"
                    if not isinstance(referenced, QuestionNode):
                        errors.append(GraphError(
                            node_id=node.id,
                            field=field,
                            code="invalid_question_reference",
                            message="Condition must reference a question node",
                        ))
                        continue
                    if not SatisfactionFlowService._reachable(
                        adjacency, referenced.id, node.id
                    ):
                        errors.append(GraphError(
                            node_id=node.id,
                            field=field,
                            code="question_not_before_condition",
                            message="Condition can only reference a reachable earlier question",
                        ))
                    if condition.option_id and condition.option_id not in {
                        option.id for option in referenced.data.options
                    }:
                        errors.append(GraphError(
                            node_id=node.id,
                            field=field,
                            code="invalid_option_reference",
                            message="Condition references an unknown question option",
                        ))

        return GraphValidationResult(ok=not errors, errors=errors)

    @staticmethod
    def validate(
        graph: SatisfactionFlowGraph, settings: SatisfactionFlowSettings
    ) -> GraphValidationResult:
        """Validate a full satisfaction flow draft."""

        del settings
        return SatisfactionFlowService.validate_graph(graph)

    @staticmethod
    def _ensure_valid(
        graph: SatisfactionFlowGraph, settings: SatisfactionFlowSettings
    ) -> None:
        result = SatisfactionFlowService.validate(graph, settings)
        if not result.ok:
            raise ValidationError(
                "Satisfaction flow validation failed",
                details={"errors": [error.model_dump() for error in result.errors]},
            )

    @staticmethod
    def _question_count(graph: SatisfactionFlowGraph) -> int:
        return sum(node.type == "question" for node in graph.nodes)

    @staticmethod
    def _version_data(
        *,
        flow_id: int,
        tenant_id: int,
        version_no: int,
        draft: SatisfactionFlowCreate | SatisfactionFlowSave,
        actor: dict,
        comment: str | None = None,
    ) -> dict:
        return {
            "tenant_id": tenant_id,
            "satisfaction_flow_id": flow_id,
            "version_no": version_no,
            "name_snapshot": draft.name,
            "description_snapshot": draft.description,
            "graph_json": draft.graph_json.model_dump(mode="json"),
            "settings_json": draft.settings.model_dump(mode="json"),
            "question_count": SatisfactionFlowService._question_count(draft.graph_json),
            "comment": comment if comment is not None else draft.comment,
            **AuditActorService.to_columns("created", actor),
            **AuditActorService.to_columns("updated", actor),
        }

    @staticmethod
    def _response(
        flow: SatisfactionFlow, version: SatisfactionFlowVersion | None = None
    ) -> dict:
        current = version or flow.current_version
        return {
            "id": flow.id,
            "name": flow.name,
            "description": flow.description,
            "enabled": flow.enabled,
            "current_version_no": current.version_no if current else None,
            "graph_json": current.graph_json if current else None,
            "settings": current.settings_json if current else None,
            "created_at": flow.created_at,
            "updated_at": flow.updated_at,
        }

    @staticmethod
    async def get_paginated(
        db: AsyncSession,
        tenant_id: int,
        page: int,
        per_page: int,
        keyword: str | None,
        enabled: bool | None,
    ) -> dict:
        rows, total = await SatisfactionFlowRepository.get_paginated(
            db, tenant_id, page, per_page, keyword, enabled
        )
        items = []
        for row in rows:
            version = row.current_version
            settings = version.settings_json if version else {}
            items.append({
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "enabled": row.enabled,
                "triggers": [
                    key
                    for key, flag in (
                        ("auto_transfer", settings.get("auto_transfer")),
                        ("agent_invite", settings.get("agent_invite")),
                    )
                    if flag
                ],
                "directions": [
                    key
                    for key, flag in (
                        ("inbound", settings.get("inbound")),
                        ("outbound", settings.get("outbound")),
                    )
                    if flag
                ],
                "question_count": version.question_count if version else 0,
                "current_version_no": version.version_no if version else None,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            })
        pages = (total + per_page - 1) // per_page
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": pages}

    @staticmethod
    async def get_by_id(db: AsyncSession, flow_id: int, tenant_id: int) -> dict:
        flow = await SatisfactionFlowRepository.get_by_id(db, flow_id, tenant_id)
        if flow is None:
            raise NotFoundError("Satisfaction flow not found")
        return SatisfactionFlowService._response(flow)

    @staticmethod
    async def create(
        db: AsyncSession, tenant_id: int, actor: dict, draft: SatisfactionFlowCreate
    ) -> dict:
        SatisfactionFlowService._ensure_valid(draft.graph_json, draft.settings)
        flow = await SatisfactionFlowRepository.create(db, {
            "tenant_id": tenant_id,
            "name": draft.name,
            "description": draft.description,
            "enabled": False,
        })
        version = await SatisfactionFlowVersionRepository.create(
            db,
            SatisfactionFlowService._version_data(
                flow_id=flow.id,
                tenant_id=tenant_id,
                version_no=1,
                draft=draft,
                actor=actor,
            ),
        )
        await SatisfactionFlowRepository.update(
            db, flow, {"current_version_id": version.id}
        )
        # onupdate=func.now() expires updated_at after flush; refresh before read.
        # Build response before commit: expire_on_commit would otherwise trigger
        # MissingGreenlet when reading ORM attributes in async sessions.
        await db.refresh(flow, attribute_names=["updated_at"])
        response = SatisfactionFlowService._response(flow, version)
        await db.commit()
        return response

    @staticmethod
    async def save(
        db: AsyncSession,
        flow_id: int,
        tenant_id: int,
        actor: dict,
        draft: SatisfactionFlowSave,
    ) -> dict:
        SatisfactionFlowService._ensure_valid(draft.graph_json, draft.settings)
        flow = await SatisfactionFlowRepository.get_by_id(
            db, flow_id, tenant_id, for_update=True
        )
        if flow is None:
            raise NotFoundError("Satisfaction flow not found")
        version_no = await SatisfactionFlowVersionRepository.latest_version_no(
            db, flow_id, tenant_id
        ) + 1
        version = await SatisfactionFlowVersionRepository.create(
            db,
            SatisfactionFlowService._version_data(
                flow_id=flow.id,
                tenant_id=tenant_id,
                version_no=version_no,
                draft=draft,
                actor=actor,
            ),
        )
        await SatisfactionFlowRepository.update(db, flow, {
            "name": draft.name,
            "description": draft.description,
            "current_version_id": version.id,
        })
        await db.refresh(flow, attribute_names=["updated_at"])
        response = SatisfactionFlowService._response(flow, version)
        await db.commit()
        return response

    @staticmethod
    async def copy(
        db: AsyncSession, flow_id: int, tenant_id: int, actor: dict
    ) -> dict:
        source = await SatisfactionFlowRepository.get_by_id(db, flow_id, tenant_id)
        if source is None or source.current_version is None:
            raise NotFoundError("Satisfaction flow version not found")
        version = source.current_version
        suffix = " - 副本"
        name = f"{source.name[: 50 - len(suffix)]}{suffix}"
        draft = SatisfactionFlowCreate(
            name=name,
            description=source.description,
            graph_json=SatisfactionFlowGraph.model_validate(version.graph_json),
            settings=SatisfactionFlowSettings.model_validate(version.settings_json),
            comment=f"Copied from {source.name} V{version.version_no}",
        )
        return await SatisfactionFlowService.create(db, tenant_id, actor, draft)

    @staticmethod
    async def enable(
        db: AsyncSession,
        flow_id: int,
        tenant_id: int,
        replace_active: bool,
    ) -> dict:
        flow = await SatisfactionFlowRepository.get_by_id(
            db, flow_id, tenant_id, for_update=True
        )
        if flow is None or flow.current_version is None:
            raise NotFoundError("Satisfaction flow not found")
        graph = SatisfactionFlowGraph.model_validate(flow.current_version.graph_json)
        settings = SatisfactionFlowSettings.model_validate(flow.current_version.settings_json)
        SatisfactionFlowService._ensure_valid(graph, settings)
        active = await SatisfactionFlowRepository.get_active(
            db, tenant_id, for_update=True
        )
        if active and active.id != flow.id and not replace_active:
            raise BusinessError(
                "Another satisfaction flow is active",
                status_code=409,
                code="ACTIVE_SATISFACTION_FLOW_EXISTS",
                details={
                    "id": active.id,
                    "name": active.name,
                    "version": active.current_version.version_no
                    if active.current_version
                    else None,
                },
            )
        if active and active.id != flow.id:
            await SatisfactionFlowRepository.update(db, active, {"enabled": False})
        await SatisfactionFlowRepository.update(db, flow, {"enabled": True})
        await db.refresh(flow, attribute_names=["updated_at"])
        response = SatisfactionFlowService._response(flow)
        await db.commit()
        return response

    @staticmethod
    async def disable(db: AsyncSession, flow_id: int, tenant_id: int) -> dict:
        flow = await SatisfactionFlowRepository.get_by_id(db, flow_id, tenant_id)
        if flow is None:
            raise NotFoundError("Satisfaction flow not found")
        await SatisfactionFlowRepository.update(db, flow, {"enabled": False})
        await db.refresh(flow, attribute_names=["updated_at"])
        response = SatisfactionFlowService._response(flow)
        await db.commit()
        return response

    @staticmethod
    async def delete(db: AsyncSession, flow_id: int, tenant_id: int) -> None:
        flow = await SatisfactionFlowRepository.get_by_id(db, flow_id, tenant_id)
        if flow is None:
            raise NotFoundError("Satisfaction flow not found")
        if flow.enabled:
            raise ConflictError("Disable the satisfaction flow before deleting it")
        await SatisfactionFlowRepository.soft_delete(db, flow)
        await db.commit()

    @staticmethod
    async def list_versions(
        db: AsyncSession, flow_id: int, tenant_id: int, limit: int
    ) -> dict:
        flow = await SatisfactionFlowRepository.get_by_id(db, flow_id, tenant_id)
        if flow is None:
            raise NotFoundError("Satisfaction flow not found")
        rows = await SatisfactionFlowVersionRepository.list_for_flow(
            db, flow_id, tenant_id, limit
        )
        current_id = flow.current_version_id
        return {
            "items": [
                {
                    "id": row.id,
                    "version_no": row.version_no,
                    "name_snapshot": row.name_snapshot,
                    "comment": row.comment,
                    "is_current": row.id == current_id,
                    "question_count": row.question_count,
                    "created_at": row.created_at,
                    "created_by_actor_name": row.created_by_actor_name,
                }
                for row in rows
            ],
            "current_version_no": flow.current_version.version_no
            if flow.current_version
            else None,
        }

    @staticmethod
    async def get_version(
        db: AsyncSession, flow_id: int, version_no: int, tenant_id: int
    ) -> dict:
        flow = await SatisfactionFlowRepository.get_by_id(db, flow_id, tenant_id)
        if flow is None:
            raise NotFoundError("Satisfaction flow not found")
        version = await SatisfactionFlowVersionRepository.get_by_version_no(
            db, flow_id, version_no, tenant_id
        )
        if version is None:
            raise NotFoundError("Satisfaction flow version not found")
        return {
            "id": version.id,
            "version_no": version.version_no,
            "name_snapshot": version.name_snapshot,
            "description_snapshot": version.description_snapshot,
            "graph_json": version.graph_json,
            "settings": version.settings_json,
            "question_count": version.question_count,
            "comment": version.comment,
            "created_at": version.created_at,
            "created_by_actor_name": version.created_by_actor_name,
            "is_current": version.id == flow.current_version_id,
        }

    @staticmethod
    async def rollback(
        db: AsyncSession,
        flow_id: int,
        version_no: int,
        tenant_id: int,
        actor: dict,
    ) -> dict:
        source = await SatisfactionFlowVersionRepository.get_by_version_no(
            db, flow_id, version_no, tenant_id
        )
        if source is None:
            raise NotFoundError("Satisfaction flow version not found")
        draft = SatisfactionFlowSave(
            name=source.name_snapshot,
            description=source.description_snapshot,
            graph_json=SatisfactionFlowGraph.model_validate(source.graph_json),
            settings=SatisfactionFlowSettings.model_validate(source.settings_json),
            comment=f"Restored from V{source.version_no}",
        )
        return await SatisfactionFlowService.save(
            db, flow_id, tenant_id, actor, draft
        )
