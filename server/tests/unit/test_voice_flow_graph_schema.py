"""
Unit tests for voice flow graph schema (Pydantic discriminated unions).
"""
import pytest

from app.schemas.voice_flow_graph import (
    AssignQueueData,
    AssignQueueNode,
    AudioPrompt,
    CollectData,
    CollectInputCfg,
    CollectNode,
    ConditionData,
    ConditionGroup,
    ConditionItem,
    ConditionNode,
    Edge,
    HangupData,
    HangupNode,
    PlayData,
    PlayNode,
    StartNode,
    TtsPrompt,
    VoiceFlowGraph,
    default_graph,
)


class TestVoiceFlowGraphSchema:

    def test_default_graph_has_single_start(self):
        g = VoiceFlowGraph.model_validate(default_graph())
        assert len(g.nodes) == 1
        assert g.nodes[0].type == "start"

    def test_graph_requires_exactly_one_start(self):
        with pytest.raises(Exception):
            VoiceFlowGraph(nodes=[])
        with pytest.raises(Exception):
            VoiceFlowGraph(
                nodes=[
                    StartNode(id="s1", type="start"),
                    StartNode(id="s2", type="start"),
                ]
            )

    def test_play_node_with_tts_prompt(self):
        n = PlayNode(
            id="p1",
            type="play",
            data=PlayData(prompt=TtsPrompt(kind="tts", text="hello")),
        )
        assert n.data.prompt.kind == "tts"

    def test_play_node_with_audio_prompt(self):
        n = PlayNode(
            id="p1",
            type="play",
            data=PlayData(prompt=AudioPrompt(kind="audio", asset_id=99)),
        )
        assert n.data.prompt.kind == "audio"
        assert n.data.prompt.asset_id == 99

    def test_collect_input_single_requires_min_max_one(self):
        with pytest.raises(Exception):
            CollectInputCfg(mode="single", min_digits=2, max_digits=4)
        # Valid case
        cfg = CollectInputCfg(mode="single", min_digits=1, max_digits=1)
        assert cfg.mode == "single"

    def test_collect_input_multi_requires_max_ge_min(self):
        with pytest.raises(Exception):
            CollectInputCfg(mode="multi", min_digits=5, max_digits=3)

    def test_collect_node_variable_name_rule(self):
        # invalid: starts with digit
        with pytest.raises(Exception):
            CollectNode(
                id="c1",
                type="collect",
                data=CollectData(
                    prompt=TtsPrompt(kind="tts", text="x"),
                    input=CollectInputCfg(mode="multi", min_digits=1, max_digits=4),
                    output_variable="1var",
                ),
            )
        # valid
        n = CollectNode(
            id="c1",
            type="collect",
            data=CollectData(
                prompt=TtsPrompt(kind="tts", text="x"),
                input=CollectInputCfg(mode="multi", min_digits=1, max_digits=4),
                output_variable="user_input",
            ),
        )
        assert n.data.output_variable == "user_input"

    def test_condition_group_ids_must_be_unique(self):
        with pytest.raises(Exception):
            ConditionData(
                groups=[
                    ConditionGroup(
                        id="g1",
                        name="A",
                        logic="AND",
                        conditions=[ConditionItem(variable="x", operator="eq", value="1")],
                    ),
                    ConditionGroup(
                        id="g1",
                        name="B",
                        logic="OR",
                        conditions=[ConditionItem(variable="x", operator="eq", value="2")],
                    ),
                ]
            )

    def test_assign_queue_data(self):
        n = AssignQueueNode(
            id="q1",
            type="assign_queue",
            data=AssignQueueData(employee_group_id=1, timeout_seconds=30),
        )
        assert n.data.employee_group_id == 1

    def test_hangup_with_pre_play(self):
        n = HangupNode(
            id="h1",
            type="hangup",
            data=HangupData(pre_play=TtsPrompt(kind="tts", text="goodbye")),
        )
        assert n.data.pre_play.kind == "tts"

    def test_full_graph_roundtrip(self):
        graph = VoiceFlowGraph(
            nodes=[
                StartNode(id="s", type="start"),
                PlayNode(id="p", type="play",
                         data=PlayData(prompt=TtsPrompt(kind="tts", text="welcome"))),
                HangupNode(id="h", type="hangup"),
            ],
            edges=[
                Edge(id="e1", source="s", target="p", source_handle="next"),
                Edge(id="e2", source="p", target="h", source_handle="next"),
            ],
        )
        dumped = graph.model_dump()
        reloaded = VoiceFlowGraph.model_validate(dumped)
        assert len(reloaded.nodes) == 3
        assert len(reloaded.edges) == 2

    def test_unknown_node_type_rejected(self):
        with pytest.raises(Exception):
            VoiceFlowGraph.model_validate(
                {
                    "version": 1,
                    "nodes": [
                        {"id": "x", "type": "unknown_type", "data": {}}
                    ],
                }
            )
