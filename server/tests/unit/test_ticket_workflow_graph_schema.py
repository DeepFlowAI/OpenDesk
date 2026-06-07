"""
Unit tests for ticket workflow graph schemas.
"""
import pytest

from app.schemas.ticket_workflow_graph import (
    BranchData,
    BranchItem,
    BranchNode,
    Edge,
    TicketWorkflowGraph,
    TriggerNode,
    UpdateOperation,
    UpdateRecordData,
    UpdateRecordNode,
    WorkflowCondition,
    default_graph,
)


class TestTicketWorkflowGraphSchema:
    def test_default_graph_has_trigger_and_end(self):
        graph = TicketWorkflowGraph.model_validate(default_graph())
        assert [node.type for node in graph.nodes] == ["trigger", "end"]
        assert graph.edges[0].source == "trigger"

    def test_graph_requires_exactly_one_trigger(self):
        with pytest.raises(Exception):
            TicketWorkflowGraph(nodes=[])
        with pytest.raises(Exception):
            TicketWorkflowGraph(nodes=[
                TriggerNode(id="t1", type="trigger"),
                TriggerNode(id="t2", type="trigger"),
            ])

    def test_condition_requires_single_field_reference(self):
        with pytest.raises(Exception):
            WorkflowCondition(field_key="status", field_id=1, operator="eq", value="open")
        with pytest.raises(Exception):
            WorkflowCondition(operator="eq", value="open")
        condition = WorkflowCondition(field_key="status", operator="eq", value="open")
        assert condition.field_key == "status"

    def test_branch_requires_exactly_one_default(self):
        with pytest.raises(Exception):
            BranchData(branches=[
                BranchItem(id="a", name="A", is_default=False),
                BranchItem(id="b", name="B", is_default=False),
            ])
        data = BranchData(branches=[
            BranchItem(id="a", name="A", is_default=False),
            BranchItem(id="default", name="否则", is_default=True),
        ])
        node = BranchNode(id="b1", type="branch", data=data)
        assert node.data.branches[1].is_default is True

    def test_update_operation_requires_single_target_reference(self):
        with pytest.raises(Exception):
            UpdateOperation(target_field_key="priority", target_field_id=1, value="high")
        operation = UpdateOperation(target_field_key="priority", action="set", value="high")
        node = UpdateRecordNode(
            id="u1",
            type="update_record",
            data=UpdateRecordData(operations=[operation]),
        )
        assert node.data.operations[0].target_field_key == "priority"

    def test_full_graph_roundtrip(self):
        graph = TicketWorkflowGraph(
            nodes=[
                TriggerNode(id="trigger", type="trigger"),
                UpdateRecordNode(
                    id="u1",
                    type="update_record",
                    data=UpdateRecordData(
                        operations=[UpdateOperation(target_field_key="priority", action="set", value="high")]
                    ),
                ),
                {"id": "end", "type": "end", "data": {}},
            ],
            edges=[
                Edge(id="e1", source="trigger", target="u1", source_handle="next"),
                Edge(id="e2", source="u1", target="end", source_handle="next"),
            ],
        )
        reloaded = TicketWorkflowGraph.model_validate(graph.model_dump())
        assert len(reloaded.nodes) == 3
