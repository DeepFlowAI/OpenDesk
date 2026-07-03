"""
Unit tests for VoiceFlowService._validate_graph — focuses on structural checks
that don't depend on the database. External-ref validation (queue / asset /
service_hours) is covered by integration tests.
"""
import asyncio

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
    VoiceSpeedData,
    VoiceSpeedNode,
)
from app.services.voice_flow_service import (
    VoiceFlowService,
    _is_ancestor,
    _validate_variable_reachability,
)


def _err_codes(errors):
    return {e.code for e in errors}


def _validate(graph: VoiceFlowGraph):
    # _validate_graph only touches the DB when external refs (assets / queues /
    # service hours) are present, so a dummy db is fine for structural checks.
    return asyncio.run(VoiceFlowService._validate_graph(object(), 1, graph))


class TestVoiceSpeedNode:

    def _graph(self, *, agent_id="agt_1", handoff_target="q", self_loop=False):
        target = "vs" if self_loop else handoff_target
        nodes = [
            StartNode(id="s", type="start"),
            VoiceSpeedNode(id="vs", type="voicespeed", data=VoiceSpeedData(agent_id=agent_id)),
        ]
        if not self_loop:
            nodes.append(PlayNode(id="q", type="play", data=PlayData(prompt=TtsPrompt(kind="tts", text="bye"))))
        edges = [
            Edge(id="e0", source="s", target="vs"),
            Edge(id="e1", source="vs", target=target, source_handle="handoff"),
        ]
        if not self_loop:
            edges.append(Edge(id="e2", source="q", target="q", source_handle="next"))
        return VoiceFlowGraph(nodes=nodes, edges=edges)

    def test_valid_voicespeed_node(self):
        errors = _validate(self._graph())
        assert "missing_agent_id" not in _err_codes(errors)
        assert "missing_handoff_edge" not in _err_codes(errors)
        assert "self_handoff" not in _err_codes(errors)

    def test_missing_agent_id(self):
        errors = _validate(self._graph(agent_id=""))
        assert "missing_agent_id" in _err_codes(errors)

    def test_missing_handoff_edge(self):
        graph = VoiceFlowGraph(
            nodes=[
                StartNode(id="s", type="start"),
                VoiceSpeedNode(id="vs", type="voicespeed", data=VoiceSpeedData(agent_id="a")),
            ],
            edges=[Edge(id="e0", source="s", target="vs")],
        )
        errors = _validate(graph)
        assert "missing_handoff_edge" in _err_codes(errors)

    def test_self_handoff_rejected(self):
        errors = _validate(self._graph(self_loop=True))
        assert "self_handoff" in _err_codes(errors)

    def test_handoff_to_missing_node_rejected(self):
        graph = VoiceFlowGraph(
            nodes=[
                StartNode(id="s", type="start"),
                VoiceSpeedNode(id="vs", type="voicespeed", data=VoiceSpeedData(agent_id="a")),
            ],
            edges=[
                Edge(id="e0", source="s", target="vs"),
                Edge(id="e1", source="vs", target="ghost", source_handle="handoff"),
            ],
        )
        errors = _validate(graph)
        assert "edge_target_missing" in _err_codes(errors)


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
