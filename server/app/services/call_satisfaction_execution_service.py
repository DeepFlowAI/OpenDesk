"""Managed persistence for version-locked call satisfaction executions."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.models.call_event import CallEvent
from app.models.employee import Employee
from app.models.satisfaction_flow import SatisfactionFlowVersion
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.call_satisfaction_answer_repository import (
    CallSatisfactionAnswerRepository,
)
from app.repositories.call_satisfaction_execution_repository import (
    CallSatisfactionExecutionRepository,
)
from app.repositories.satisfaction_flow_repository import SatisfactionFlowRepository
from app.schemas.satisfaction_flow_graph import QuestionNode, SatisfactionFlowGraph
from app.services.call_satisfaction_projection_service import (
    CallSatisfactionProjectionService,
)
from app.services.call_trajectory_service import CallTrajectoryService


logger = logging.getLogger(__name__)

FINAL_STATUSES = frozenset({"completed", "partial", "unanswered", "failed"})
TRIGGER_SOURCES = frozenset({"auto_transfer", "agent_invite"})


@dataclass(frozen=True)
class PreparedSatisfactionExecution:
    execution_id: int
    tenant_id: int
    call_record_id: int
    call_id: str
    flow_id: int
    flow_version_id: int
    flow_name: str
    flow_version_no: int
    graph: dict
    settings: dict
    status: str
    created: bool
    agent_id: int | None = None
    agent_name: str | None = None


class CallSatisfactionExecutionService:
    """Open short sessions around writes and hold none during media waits."""

    @staticmethod
    async def _prepared_response(db, execution, *, created: bool):
        version = await db.get(
            SatisfactionFlowVersion, execution.satisfaction_flow_version_id
        )
        record = await CallRecordRepository.get_by_id_unscoped(
            db, execution.call_record_id
        )
        if version is None or record is None:
            raise NotFoundError("Satisfaction execution dependencies not found")
        return PreparedSatisfactionExecution(
            execution_id=execution.id,
            tenant_id=execution.tenant_id,
            call_record_id=record.id,
            call_id=record.root_call_id or record.call_id,
            flow_id=execution.satisfaction_flow_id,
            flow_version_id=version.id,
            flow_name=execution.flow_name_snapshot,
            flow_version_no=execution.flow_version_no,
            agent_id=execution.agent_id_snapshot,
            agent_name=execution.agent_name_snapshot,
            graph=dict(version.graph_json),
            settings=dict(version.settings_json),
            status=execution.status,
            created=created,
        )

    @staticmethod
    async def prepare_managed(
        *, tenant_id: int, call_id: str, trigger_source: str
    ) -> PreparedSatisfactionExecution:
        """Lock the active flow version and idempotently create an execution."""

        if trigger_source not in TRIGGER_SOURCES:
            raise ValidationError("Invalid satisfaction trigger source")

        created = False
        async with AsyncSessionLocal() as db:
            record = await CallRecordRepository.get_by_call_id(db, call_id, tenant_id)
            if record is None:
                raise NotFoundError("Call record not found")
            record_id = record.id
            existing = await CallSatisfactionExecutionRepository.get_by_call_record_id(
                db, record.id
            )
            if existing is not None:
                return await CallSatisfactionExecutionService._prepared_response(
                    db, existing, created=False
                )

            flow = await SatisfactionFlowRepository.get_active(db, tenant_id)
            if flow is None or flow.current_version is None:
                raise ConflictError("No active satisfaction flow is available")
            version = flow.current_version
            settings = dict(version.settings_json)
            if not settings.get(trigger_source, False):
                raise ConflictError("The satisfaction trigger is disabled")
            if not settings.get(record.direction, False):
                raise ConflictError("The satisfaction flow does not allow this direction")

            agent_name = None
            if record.last_serving_agent_id is not None:
                employee = await db.get(Employee, record.last_serving_agent_id)
                if employee is not None and employee.tenant_id == tenant_id:
                    agent_name = employee.display_name or employee.name or employee.username

            queue_name = None
            if record.last_queue_type and record.last_queue_id is not None:
                queue_name = (
                    await db.execute(
                        select(CallEvent.queue_name_snapshot)
                        .where(
                            CallEvent.call_record_id == record.id,
                            CallEvent.queue_type == record.last_queue_type,
                            CallEvent.queue_id == record.last_queue_id,
                            CallEvent.queue_name_snapshot.is_not(None),
                        )
                        .order_by(desc(CallEvent.sequence_no))
                        .limit(1)
                    )
                ).scalar_one_or_none()

            try:
                execution = await CallSatisfactionExecutionRepository.create(
                    db,
                    {
                        "tenant_id": tenant_id,
                        "call_record_id": record.id,
                        "satisfaction_flow_id": flow.id,
                        "satisfaction_flow_version_id": version.id,
                        "trigger_source": trigger_source,
                        "status": "preparing",
                        "flow_name_snapshot": version.name_snapshot,
                        "flow_version_no": version.version_no,
                        "agent_id_snapshot": record.last_serving_agent_id,
                        "agent_name_snapshot": agent_name,
                        "queue_type_snapshot": record.last_queue_type,
                        "queue_id_snapshot": record.last_queue_id,
                        "queue_name_snapshot": queue_name,
                    },
                    commit=False,
                )
                await db.commit()
                await db.refresh(execution)
                created = True
            except IntegrityError:
                await db.rollback()
                execution = (
                    await CallSatisfactionExecutionRepository.get_by_call_record_id(
                        db, record_id
                    )
                )
                if execution is None:
                    raise

            prepared = await CallSatisfactionExecutionService._prepared_response(
                db, execution, created=created
            )

        if created:
            await CallTrajectoryService.append_for_call_id_best_effort(
                tenant_id=tenant_id,
                call_id=prepared.call_id,
                event_id=f"opendesk:satisfaction-preparing:{prepared.execution_id}",
                event_type="satisfaction_preparing",
                event_category="ivr",
                actor_type="agent",
                actor_id=str(prepared.agent_id) if prepared.agent_id is not None else None,
                actor_name_snapshot=prepared.agent_name,
                source="opendesk",
                target_type="satisfaction_flow_version",
                target_id=str(prepared.flow_version_id),
                target_name_snapshot=prepared.flow_name,
                result="started",
                details={
                    "execution_id": prepared.execution_id,
                    "trigger_source": trigger_source,
                    "flow_version_no": prepared.flow_version_no,
                },
            )
        return prepared

    @staticmethod
    async def mark_started_managed(execution_id: int) -> None:
        execution = None
        async with AsyncSessionLocal() as db:
            execution = await CallSatisfactionExecutionRepository.lock_by_id(
                db, execution_id
            )
            if execution is None:
                raise NotFoundError("Satisfaction execution not found")
            if execution.status == "preparing":
                execution.status = "in_progress"
                execution.started_at = datetime.now(timezone.utc)
                await db.commit()

    @staticmethod
    async def record_answer_managed(
        *, execution_id: int, question_node_id: str, digit: str
    ) -> dict | None:
        """Map transient DTMF to an option and persist only the option snapshot."""

        if len(digit) != 1 or digit not in "0123456789":
            return None

        created = False
        call_id = None
        answer = None
        execution = None
        async with AsyncSessionLocal() as db:
            execution = await CallSatisfactionExecutionRepository.lock_by_id(
                db, execution_id
            )
            if execution is None:
                raise NotFoundError("Satisfaction execution not found")
            if execution.status != "in_progress":
                return None
            existing = await CallSatisfactionAnswerRepository.get_by_question(
                db, execution_id, question_node_id
            )
            if existing is not None:
                return {
                    "question_node_id": existing.question_node_id,
                    "question_name": existing.question_name_snapshot,
                    "option_id": existing.option_id,
                    "option_label": existing.option_label_snapshot,
                    "created": False,
                }

            version = await db.get(
                SatisfactionFlowVersion, execution.satisfaction_flow_version_id
            )
            if version is None:
                raise NotFoundError("Satisfaction flow version not found")
            graph = SatisfactionFlowGraph.model_validate(version.graph_json)
            question = next(
                (
                    node
                    for node in graph.nodes
                    if isinstance(node, QuestionNode) and node.id == question_node_id
                ),
                None,
            )
            if question is None:
                raise ValidationError("Question is not part of the locked flow version")
            option = next(
                (item for item in question.data.options if item.dtmf == digit), None
            )
            if option is None:
                return None

            answer = await CallSatisfactionAnswerRepository.create(
                db,
                {
                    "tenant_id": execution.tenant_id,
                    "execution_id": execution.id,
                    "question_node_id": question.id,
                    "question_name_snapshot": question.data.name,
                    "question_order": execution.answer_count + 1,
                    "option_id": option.id,
                    "option_label_snapshot": option.label,
                    "answered_at": datetime.now(timezone.utc),
                },
                commit=False,
            )
            execution.answer_count += 1
            await db.commit()
            created = True
            record = await CallRecordRepository.get_by_id_unscoped(
                db, execution.call_record_id
            )
            call_id = (record.root_call_id or record.call_id) if record else None

        if created and call_id and answer is not None:
            await CallTrajectoryService.append_for_call_id_best_effort(
                tenant_id=execution.tenant_id,
                call_id=call_id,
                event_id=(
                    f"opendesk:satisfaction-answer:{execution_id}:"
                    f"{question_node_id}"
                ),
                event_type="satisfaction_question_answered",
                event_category="ivr",
                actor_type="customer",
                source="opendesk",
                target_type="satisfaction_question",
                target_id=question_node_id,
                target_name_snapshot=answer.question_name_snapshot,
                result="succeeded",
                details={
                    "execution_id": execution_id,
                    "question_name": answer.question_name_snapshot,
                },
            )
        return {
            "question_node_id": answer.question_node_id,
            "question_name": answer.question_name_snapshot,
            "option_id": answer.option_id,
            "option_label": answer.option_label_snapshot,
            "created": created,
        }

    @staticmethod
    async def finalize_managed(
        *, execution_id: int, status: str, reason: str
    ) -> str:
        if status not in FINAL_STATUSES:
            raise ValidationError("Invalid satisfaction final status")

        changed = False
        call_id = None
        execution = None
        async with AsyncSessionLocal() as db:
            execution = await CallSatisfactionExecutionRepository.lock_by_id(
                db, execution_id
            )
            if execution is None:
                raise NotFoundError("Satisfaction execution not found")
            if execution.status in FINAL_STATUSES:
                return execution.status
            if execution.status not in {"preparing", "in_progress"}:
                raise ConflictError("Satisfaction execution cannot be finalized")
            execution.status = status
            execution.termination_reason = reason[:64]
            execution.ended_at = datetime.now(timezone.utc)
            changed = True
            await db.commit()
            record = await CallRecordRepository.get_by_id_unscoped(
                db, execution.call_record_id
            )
            call_id = (record.root_call_id or record.call_id) if record else None

        if changed and call_id:
            await CallTrajectoryService.append_for_call_id_best_effort(
                tenant_id=execution.tenant_id,
                call_id=call_id,
                event_id=f"opendesk:satisfaction-final:{execution_id}",
                event_type="satisfaction_completed",
                event_category="ivr",
                actor_type="system",
                source="opendesk",
                target_type="satisfaction_execution",
                target_id=str(execution_id),
                target_name_snapshot=execution.flow_name_snapshot,
                result=status,
                reason_code=reason[:48],
                details={
                    "execution_id": execution_id,
                    "status": status,
                    "answer_count": execution.answer_count,
                },
            )
        if changed:
            await CallSatisfactionExecutionService._project_best_effort(
                execution.call_record_id
            )
        return status

    @staticmethod
    async def _project_best_effort(call_record_id: int) -> None:
        """Publish the finished survey onto its call record.

        The call record also projects when it closes, but a survey can outlive
        the call it belongs to: the customer hangs up, the record closes while
        this execution is still running, and it reaches a final status only a
        beat later. Without this second attempt such a record would carry no
        trace of a survey that really ran. Projection is idempotent, so the
        two paths are free to race.
        """
        try:
            async with AsyncSessionLocal() as db:
                await CallSatisfactionProjectionService.project(
                    db, call_record_id=call_record_id
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to project call satisfaction call_record_id=%s",
                call_record_id,
            )

    @staticmethod
    async def mark_failed_managed(*, execution_id: int, reason: str) -> str:
        return await CallSatisfactionExecutionService.finalize_managed(
            execution_id=execution_id,
            status="failed",
            reason=reason,
        )
