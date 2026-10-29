"""Final, idempotent satisfaction projection for call records."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.satisfaction_flow import SatisfactionFlowVersion
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.call_satisfaction_answer_repository import (
    CallSatisfactionAnswerRepository,
)
from app.repositories.call_satisfaction_execution_repository import (
    CallSatisfactionExecutionRepository,
)
from app.schemas.satisfaction_flow_graph import QuestionNode, SatisfactionFlowGraph


FINAL_RESULTS = frozenset({"completed", "partial", "unanswered", "failed"})


class CallSatisfactionProjectionService:
    """Project immutable final survey data onto its parent call record."""

    @staticmethod
    async def project(
        db: AsyncSession, *, call_record_id: int
    ) -> bool:
        record = await CallRecordRepository.lock_by_id(db, call_record_id)
        if record is None or record.lifecycle_status != "ended":
            return False
        if record.satisfaction_projected_at is not None:
            return True

        execution = await CallSatisfactionExecutionRepository.get_by_call_record_id(
            db, record.id
        )
        if record.ended_at is None:
            return False
        now = datetime.now(timezone.utc)
        if execution is None:
            patch = {
                "satisfaction_result": "not_surveyed",
                "satisfaction_answer_count": 0,
                "satisfaction_projected_at": now,
            }
        else:
            if execution.status not in FINAL_RESULTS:
                return False
            answers = await CallSatisfactionAnswerRepository.list_for_execution(
                db, execution.id
            )
            first = answers[0] if answers else None
            duration_ms = None
            if execution.started_at is not None and execution.ended_at is not None:
                duration_ms = max(
                    0,
                    int(
                        (
                            execution.ended_at.astimezone(timezone.utc)
                            - execution.started_at.astimezone(timezone.utc)
                        ).total_seconds()
                        * 1000
                    ),
                )
            patch = {
                "satisfaction_result": execution.status,
                "satisfaction_trigger_source": execution.trigger_source,
                "satisfaction_primary_option_id": first.option_id if first else None,
                "satisfaction_primary_option_label": (
                    first.option_label_snapshot if first else None
                ),
                "satisfaction_answer_count": len(answers),
                "satisfaction_duration_ms": duration_ms,
                "satisfaction_projected_at": now,
            }
        await CallRecordRepository.update(db, record, patch, commit=False)
        if execution is not None:
            from app.services.call_event_publisher import CallEventPublisher

            await CallEventPublisher.publish_satisfaction_completed(
                db, record, execution, first
            )
        await db.commit()
        return True

    @staticmethod
    async def detail(db: AsyncSession, *, call_record_id: int) -> dict | None:
        execution = await CallSatisfactionExecutionRepository.get_by_call_record_id(
            db, call_record_id
        )
        if execution is None:
            return None
        if execution.status not in FINAL_RESULTS:
            return None
        version = await db.get(
            SatisfactionFlowVersion, execution.satisfaction_flow_version_id
        )
        answers = await CallSatisfactionAnswerRepository.list_for_execution(
            db, execution.id
        )
        answers_by_question = {answer.question_node_id: answer for answer in answers}
        question_nodes: list[QuestionNode] = []
        if version is not None:
            graph = SatisfactionFlowGraph.model_validate(version.graph_json)
            question_nodes = [
                node for node in graph.nodes if isinstance(node, QuestionNode)
            ]
        question_results = []
        for node in question_nodes:
            answer = answers_by_question.get(node.id)
            question_results.append(
                {
                    "question_node_id": node.id,
                    "question_name": node.data.name,
                    "option_id": answer.option_id if answer else None,
                    "option_label": answer.option_label_snapshot if answer else None,
                    "answered_at": answer.answered_at if answer else None,
                }
            )
        return {
            "status": execution.status,
            "trigger_source": execution.trigger_source,
            "flow_name": execution.flow_name_snapshot,
            "flow_version_no": execution.flow_version_no,
            "started_at": execution.started_at,
            "ended_at": execution.ended_at,
            "duration_ms": (
                max(
                    0,
                    int((execution.ended_at - execution.started_at).total_seconds() * 1000),
                )
                if execution.started_at is not None and execution.ended_at is not None
                else None
            ),
            "agent_id": execution.agent_id_snapshot,
            "agent_name": execution.agent_name_snapshot,
            "queue_type": execution.queue_type_snapshot,
            "queue_id": execution.queue_id_snapshot,
            "queue_name": execution.queue_name_snapshot,
            "termination_reason": execution.termination_reason,
            "answers": question_results,
        }
