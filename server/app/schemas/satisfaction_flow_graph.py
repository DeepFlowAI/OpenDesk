"""Strict graph schema for call satisfaction surveys."""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AutoTtsPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["auto_tts"]
    text: str = Field(..., min_length=1, max_length=1000)


class TtsPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["tts"]
    text: str = Field(..., min_length=1, max_length=1000)


class AudioPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["audio"]
    asset_id: int = Field(..., gt=0)


Prompt = Annotated[
    Union[AutoTtsPrompt, TtsPrompt, AudioPrompt], Field(discriminator="kind")
]


class StartData(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlayData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: Prompt


class QuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    dtmf: str = Field(..., pattern=r"^[0-9]$")
    label: str = Field(..., min_length=1, max_length=30)

    @field_validator("label")
    @classmethod
    def strip_label(cls, value: str) -> str:
        return value.strip()


class QuestionRetry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    no_input: int = Field(1, ge=0, le=5)
    no_match: int = Field(1, ge=0, le=5)
    no_input_prompt: Prompt | None = None
    no_match_prompt: Prompt | None = None

    @model_validator(mode="after")
    def validate_prompts(self) -> "QuestionRetry":
        if self.enabled and self.no_input > 0 and self.no_input_prompt is None:
            raise ValueError("no_input_prompt is required when no-input retry is enabled")
        if self.enabled and self.no_match > 0 and self.no_match_prompt is None:
            raise ValueError("no_match_prompt is required when no-match retry is enabled")
        return self


class QuestionData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=50)
    required: bool = True
    prompt: Prompt
    barge_in_disabled: bool = False
    options: list[QuestionOption] = Field(..., min_length=2, max_length=10)
    timeout_seconds: int = Field(8, ge=1, le=30)
    retry: QuestionRetry

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("options")
    @classmethod
    def unique_options(cls, options: list[QuestionOption]) -> list[QuestionOption]:
        ids = [option.id for option in options]
        keys = [option.dtmf for option in options]
        labels = [option.label for option in options]
        if len(ids) != len(set(ids)):
            raise ValueError("Option ids must be unique within a question")
        if len(keys) != len(set(keys)):
            raise ValueError("DTMF keys must be unique within a question")
        if len(labels) != len(set(labels)):
            raise ValueError("Option labels must be unique within a question")
        return options


ConditionOperator = Literal["eq", "neq", "is_answered"]


class SatisfactionCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_node_id: str = Field(..., min_length=1, max_length=64)
    operator: ConditionOperator
    option_id: str | None = Field(None, max_length=64)

    @model_validator(mode="after")
    def validate_option(self) -> "SatisfactionCondition":
        if self.operator in {"eq", "neq"} and not self.option_id:
            raise ValueError("option_id is required for eq/neq")
        if self.operator == "is_answered" and self.option_id is not None:
            raise ValueError("option_id is not allowed for is_answered")
        return self


class ConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    logic: Literal["AND", "OR"] = "AND"
    conditions: list[SatisfactionCondition] = Field(..., min_length=1)


class ConditionData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groups: list[ConditionGroup] = Field(..., min_length=1)

    @field_validator("groups")
    @classmethod
    def unique_groups(cls, groups: list[ConditionGroup]) -> list[ConditionGroup]:
        ids = [group.id for group in groups]
        names = [group.name for group in groups]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise ValueError("Condition group ids and names must be unique")
        return groups


class EndData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pre_play: Prompt | None = None
    completion_type: Literal["completed", "incomplete"] = "completed"


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = 0
    y: float = 0


class NodeBase(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    position: Position = Field(default_factory=Position)


class StartNode(NodeBase):
    type: Literal["start"]
    data: StartData = Field(default_factory=StartData)


class PlayNode(NodeBase):
    type: Literal["play"]
    data: PlayData


class QuestionNode(NodeBase):
    type: Literal["question"]
    data: QuestionData


class ConditionNode(NodeBase):
    type: Literal["condition"]
    data: ConditionData


class EndNode(NodeBase):
    type: Literal["end"]
    data: EndData = Field(default_factory=EndData)


Node = Annotated[
    Union[StartNode, PlayNode, QuestionNode, ConditionNode, EndNode],
    Field(discriminator="type"),
]


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64)
    source: str = Field(..., min_length=1, max_length=64)
    target: str = Field(..., min_length=1, max_length=64)
    source_handle: str = Field("next", min_length=1, max_length=64)


class SatisfactionFlowGraph(BaseModel):
    """Versioned graph stored as JSONB after structural validation."""

    model_config = ConfigDict(extra="forbid")
    version: int = 1
    nodes: list[Node]
    edges: list[Edge] = Field(default_factory=list)

    @field_validator("nodes")
    @classmethod
    def validate_nodes(cls, nodes: list[Node]) -> list[Node]:
        ids = [node.id for node in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Node ids must be unique")
        if sum(node.type == "start" for node in nodes) != 1:
            raise ValueError("Graph must contain exactly one start node")
        return nodes

    @field_validator("edges")
    @classmethod
    def unique_edges(cls, edges: list[Edge]) -> list[Edge]:
        ids = [edge.id for edge in edges]
        if len(ids) != len(set(ids)):
            raise ValueError("Edge ids must be unique")
        return edges


class GraphError(BaseModel):
    node_id: str | None = None
    field: str | None = None
    code: str
    message: str


class GraphValidationResult(BaseModel):
    ok: bool
    errors: list[GraphError] = Field(default_factory=list)


def default_satisfaction_graph() -> dict:
    """Return the editable start-question-end three-level preset."""

    retry = QuestionRetry(
        enabled=True,
        no_input=1,
        no_match=1,
        no_input_prompt=TtsPrompt(kind="tts", text="未收到您的输入，请重新选择。"),
        no_match_prompt=TtsPrompt(kind="tts", text="输入无效，请按提示重新选择。"),
    )
    graph = SatisfactionFlowGraph(
        nodes=[
            StartNode(id="start", type="start", position=Position(x=80, y=240)),
            QuestionNode(
                id="question-1",
                type="question",
                position=Position(x=360, y=240),
                data=QuestionData(
                    name="服务满意度",
                    prompt=AutoTtsPrompt(
                        kind="auto_tts",
                        text="请评价本次服务。满意请按 3，一般请按 2，不满意请按 1。",
                    ),
                    options=[
                        QuestionOption(id="satisfied", dtmf="3", label="满意"),
                        QuestionOption(id="neutral", dtmf="2", label="一般"),
                        QuestionOption(id="dissatisfied", dtmf="1", label="不满意"),
                    ],
                    retry=retry,
                ),
            ),
            EndNode(
                id="end",
                type="end",
                position=Position(x=700, y=240),
                data=EndData(
                    pre_play=TtsPrompt(kind="tts", text="感谢您的评价，祝您生活愉快。"),
                    completion_type="completed",
                ),
            ),
        ],
        edges=[
            Edge(id="edge-start", source="start", target="question-1", source_handle="next"),
            Edge(id="edge-answered", source="question-1", target="end", source_handle="answered"),
            Edge(id="edge-no-input", source="question-1", target="end", source_handle="no_input"),
            Edge(id="edge-no-match", source="question-1", target="end", source_handle="no_match"),
            Edge(id="edge-error", source="question-1", target="end", source_handle="error"),
        ],
    )
    return graph.model_dump()
