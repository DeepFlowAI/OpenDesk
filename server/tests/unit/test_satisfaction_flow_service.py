"""Unit tests for call satisfaction flow validation and lifecycle logic."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from sqlalchemy.dialects import postgresql

from app.repositories.satisfaction_flow_repository import SatisfactionFlowRepository
from app.schemas.satisfaction_flow import SatisfactionFlowCreate
from app.schemas.satisfaction_flow_graph import (
    SatisfactionFlowGraph,
    default_satisfaction_graph,
)
from app.services.satisfaction_flow_service import SatisfactionFlowService


def _graph_data() -> dict:
    return default_satisfaction_graph()


class TestSatisfactionFlowValidation:
    def test_default_graph_is_valid(self) -> None:
        graph = SatisfactionFlowGraph.model_validate(_graph_data())

        result = SatisfactionFlowService.validate_graph(graph)

        assert result.ok is True
        assert result.errors == []

    def test_duplicate_dtmf_is_rejected_by_schema(self) -> None:
        data = _graph_data()
        question = next(node for node in data["nodes"] if node["type"] == "question")
        question["data"]["options"][1]["dtmf"] = question["data"]["options"][0]["dtmf"]

        with pytest.raises(PydanticValidationError, match="DTMF keys must be unique"):
            SatisfactionFlowGraph.model_validate(data)

    def test_duplicate_question_names_are_reported_per_node(self) -> None:
        data = _graph_data()
        question = next(node for node in data["nodes"] if node["type"] == "question")
        second = {
            **question,
            "id": "question-2",
            "position": {"x": 540, "y": 420},
        }
        data["nodes"].append(second)
        data["edges"].extend([
            {
                "id": "edge-question-2-answered",
                "source": "question-2",
                "target": "end",
                "source_handle": "answered",
            },
            {
                "id": "edge-question-2-no-input",
                "source": "question-2",
                "target": "end",
                "source_handle": "no_input",
            },
            {
                "id": "edge-question-2-no-match",
                "source": "question-2",
                "target": "end",
                "source_handle": "no_match",
            },
            {
                "id": "edge-question-2-error",
                "source": "question-2",
                "target": "end",
                "source_handle": "error",
            },
        ])

        result = SatisfactionFlowService.validate_graph(
            SatisfactionFlowGraph.model_validate(data)
        )

        duplicate_errors = [
            error for error in result.errors if error.code == "duplicate_question_name"
        ]
        assert {error.node_id for error in duplicate_errors} == {"question-1", "question-2"}

    def test_unreachable_node_and_cycle_are_reported(self) -> None:
        data = _graph_data()
        data["nodes"].append({
            "id": "orphan-end",
            "type": "end",
            "position": {"x": 900, "y": 400},
            "data": {"completion_type": "incomplete"},
        })
        data["edges"].append({
            "id": "edge-cycle",
            "source": "end",
            "target": "question-1",
            "source_handle": "invalid",
        })

        result = SatisfactionFlowService.validate_graph(
            SatisfactionFlowGraph.model_validate(data)
        )

        codes = {error.code for error in result.errors}
        assert "unreachable_node" in codes
        assert "cycle_detected" in codes
        assert "invalid_outlet" in codes


class TestSatisfactionFlowLifecycle:
    @pytest.mark.asyncio
    async def test_create_persists_disabled_v1_and_current_pointer(self) -> None:
        db = AsyncMock()
        flow = SimpleNamespace(
            id=12,
            name="满意度",
            description=None,
            enabled=False,
            current_version=None,
            created_at=None,
            updated_at=None,
        )
        version = SimpleNamespace(
            id=34,
            version_no=1,
            graph_json=_graph_data(),
            settings_json={
                "auto_transfer": False,
                "agent_invite": True,
                "inbound": True,
                "outbound": False,
            },
        )
        draft = SatisfactionFlowCreate(name="满意度")

        with (
            patch(
                "app.services.satisfaction_flow_service.SatisfactionFlowRepository.create",
                new=AsyncMock(return_value=flow),
            ) as create_flow,
            patch(
                "app.services.satisfaction_flow_service.SatisfactionFlowVersionRepository.create",
                new=AsyncMock(return_value=version),
            ) as create_version,
            patch(
                "app.services.satisfaction_flow_service.SatisfactionFlowRepository.update",
                new=AsyncMock(),
            ) as update_flow,
        ):
            result = await SatisfactionFlowService.create(
                db,
                tenant_id=7,
                actor={"actor_type": "employee", "actor_id": 9, "actor_name": "Agent"},
                draft=draft,
            )

        create_flow.assert_awaited_once()
        assert create_flow.await_args.args[1]["enabled"] is False
        assert create_version.await_args.args[1]["version_no"] == 1
        update_flow.assert_awaited_once_with(db, flow, {"current_version_id": 34})
        db.refresh.assert_awaited_once_with(flow, attribute_names=["updated_at"])
        db.commit.assert_awaited_once()
        assert result["current_version_no"] == 1


class TestSatisfactionFlowLocking:
    @pytest.mark.asyncio
    async def test_get_active_for_update_locks_only_the_flow_row(self) -> None:
        # The eager-loaded current version joins in as a LEFT OUTER JOIN, and
        # PostgreSQL rejects FOR UPDATE on the nullable side of one. Locking the
        # whole join here makes enabling a flow fail on every call.
        captured: dict[str, str] = {}

        class _RecordingSession:
            async def execute(self, query):
                captured["sql"] = str(query.compile(dialect=postgresql.dialect()))
                return SimpleNamespace(
                    unique=lambda: SimpleNamespace(scalar_one_or_none=lambda: None)
                )

        await SatisfactionFlowRepository.get_active(
            _RecordingSession(), tenant_id=7, for_update=True
        )

        assert "LEFT OUTER JOIN" in captured["sql"]
        assert "FOR UPDATE OF satisfaction_flows" in captured["sql"]
