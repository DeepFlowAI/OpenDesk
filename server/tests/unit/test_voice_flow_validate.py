"""
Unit tests for VoiceFlowService._validate_graph — focuses on structural checks
that don't depend on the database. External-ref validation (queue / asset /
service_hours) is covered by integration tests.
"""
import pytest

from app.schemas.voice_flow_graph import (
    CollectData,
    CollectInputCfg,
    CollectNode,
    ConditionData,
    ConditionGroup,
    ConditionItem,
    ConditionNode,
    Edge,
    PlayData,
    PlayNode,
    StartNode,
    TtsPrompt,
    VoiceFlowGraph,
)
from app.services.voice_flow_service import (
    _is_ancestor,
    _validate_variable_reachability,
)


def _err_codes(errors):
    return {e.code for e in errors}


class TestVariableReachability:

    def test_sys_variable_always_ok(self):
        graph = VoiceFlowGraph(
            nodes=[
                StartNode(id="s", type="start"),
                ConditionNode(
                    id="c", type="condition",
                    data=ConditionData(groups=[
                        ConditionGroup(
                            id="g1", name="VIP", logic="AND",
                            conditions=[ConditionItem(
                                variable="sys.caller_number", operator="eq", value="10086"
                            )],
                        ),
                    ]),
                ),
            ],
            edges=[Edge(id="e1", source="s", target="c")],
        )
        errors = []
        _validate_variable_reachability(graph, errors)
        assert errors == []

    def test_undeclared_variable_reported(self):
        graph = VoiceFlowGraph(
            nodes=[
                StartNode(id="s", type="start"),
                ConditionNode(
                    id="c", type="condition",
                    data=ConditionData(groups=[
                        ConditionGroup(
                            id="g1", name="X", logic="AND",
                            conditions=[ConditionItem(
                                variable="ghost", operator="eq", value="x"
                            )],
                        ),
                    ]),
                ),
            ],
            edges=[Edge(id="e1", source="s", target="c")],
        )
        errors = []
        _validate_variable_reachability(graph, errors)
        assert "variable_not_produced" in _err_codes(errors)

    def test_variable_not_reachable_when_collect_downstream(self):
        # collect node comes AFTER the condition, so its variable is not
        # available at the condition node.
        graph = VoiceFlowGraph(
            nodes=[
                StartNode(id="s", type="start"),
                ConditionNode(
                    id="c", type="condition",
                    data=ConditionData(groups=[
                        ConditionGroup(
                            id="g1", name="X", logic="AND",
                            conditions=[ConditionItem(
                                variable="my_input", operator="eq", value="1"
                            )],
                        ),
                    ]),
                ),
                CollectNode(
                    id="k", type="collect",
                    data=CollectData(
                        prompt=TtsPrompt(kind="tts", text="enter"),
                        input=CollectInputCfg(mode="single", min_digits=1, max_digits=1),
                        output_variable="my_input",
                    ),
                ),
            ],
            edges=[
                Edge(id="e1", source="s", target="c"),
                Edge(id="e2", source="c", target="k", source_handle="default"),
            ],
        )
        errors = []
        _validate_variable_reachability(graph, errors)
        assert "variable_not_reachable" in _err_codes(errors)

    def test_variable_reachable_when_collect_upstream(self):
        graph = VoiceFlowGraph(
            nodes=[
                StartNode(id="s", type="start"),
                CollectNode(
                    id="k", type="collect",
                    data=CollectData(
                        prompt=TtsPrompt(kind="tts", text="enter"),
                        input=CollectInputCfg(mode="single", min_digits=1, max_digits=1),
                        output_variable="my_input",
                    ),
                ),
                ConditionNode(
                    id="c", type="condition",
                    data=ConditionData(groups=[
                        ConditionGroup(
                            id="g1", name="X", logic="AND",
                            conditions=[ConditionItem(
                                variable="my_input", operator="eq", value="1"
                            )],
                        ),
                    ]),
                ),
            ],
            edges=[
                Edge(id="e1", source="s", target="k"),
                Edge(id="e2", source="k", target="c", source_handle="success"),
            ],
        )
        errors = []
        _validate_variable_reachability(graph, errors)
        assert errors == []


class TestAncestorBFS:

    def test_direct(self):
        rev = {"b": ["a"]}
        assert _is_ancestor("a", "b", rev) is True

    def test_chain(self):
        rev = {"c": ["b"], "b": ["a"]}
        assert _is_ancestor("a", "c", rev) is True

    def test_unreachable(self):
        rev = {"b": ["x"]}
        assert _is_ancestor("a", "b", rev) is False

    def test_self_not_ancestor(self):
        rev = {"a": ["b"]}
        assert _is_ancestor("a", "a", rev) is False
