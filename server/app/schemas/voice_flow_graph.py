"""
Voice flow graph schemas — Pydantic v2 discriminated unions for the
node `data` and `prompt` fields. Strict on save / validate; permissive
on storage (graph_json is JSONB and may contain old shapes from older
versions — the runtime engine handles upgrades).
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ─────────────────────────── Prompt (TTS or audio) ───────────────────────────
# Used by play / collect / hangup nodes.

class TtsPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["tts"]
    text: str = Field(..., min_length=1, max_length=2000)


class AudioPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["audio"]
    asset_id: int


Prompt = Annotated[Union[TtsPrompt, AudioPrompt], Field(discriminator="kind")]


# ─────────────────────────── Node data variants ───────────────────────────

class StartData(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlayData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: Prompt


class CollectInputCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["single", "multi", "any"]
    min_digits: int = Field(1, ge=1, le=20)
    max_digits: int = Field(1, ge=1, le=20)
    terminator: Literal["#", "*"] | None = "#"
    skip_terminator_on_single: bool = True

    @model_validator(mode="after")
    def validate_range(self) -> "CollectInputCfg":
        if self.max_digits < self.min_digits:
            raise ValueError("max_digits must be ≥ min_digits")
        if self.mode == "single":
            if self.min_digits != 1 or self.max_digits != 1:
                raise ValueError("single mode requires min=max=1")
        return self


class CollectTimeoutCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_input_ms: int = Field(5000, ge=1000, le=30000)
    inter_digit_ms: int = Field(10000, ge=1000, le=15000)


class CollectRetryCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    no_input: int = Field(1, ge=0, le=5)
    no_match: int = Field(1, ge=0, le=5)


class CollectData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: Prompt
    barge_in_disabled: bool = False
    input: CollectInputCfg
    timeout: CollectTimeoutCfg = Field(default_factory=CollectTimeoutCfg)
    retry: CollectRetryCfg = Field(default_factory=CollectRetryCfg)
    output_variable: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=64)


# ── Condition node ──
# operator vocab is shared across variable types; allowed combinations enforced
# by the runtime evaluator. Keep schema permissive so future operators don't
# require a migration.
ConditionOperator = Literal[
    "eq", "neq",
    "any_eq", "any_neq",
    "is_empty", "is_not_empty",
    "time_in", "time_not_in",
]


class ConditionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variable: str = Field(..., max_length=64)
    operator: ConditionOperator
    # `value` is intentionally permissive: str | list[str] | int | None.
    # - eq/neq → str
    # - any_eq/any_neq → list[str]
    # - is_empty/is_not_empty → None
    # - time_in/time_not_in → int (service_hours.id)
    value: str | list[str] | int | None = None


class ConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    logic: Literal["AND", "OR"] = "AND"
    conditions: list[ConditionItem] = Field(..., min_length=1)


class ConditionData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groups: list[ConditionGroup] = Field(..., min_length=1)

    @field_validator("groups")
    @classmethod
    def unique_group_ids_and_names(cls, v: list[ConditionGroup]) -> list[ConditionGroup]:
        ids = [g.id for g in v]
        if len(set(ids)) != len(ids):
            raise ValueError("Condition group ids must be unique within a node")
        names = [g.name for g in v]
        if len(set(names)) != len(names):
            raise ValueError("Condition group names must be unique within a node")
        return v


class AssignQueueData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_group_id: int
    timeout_seconds: int | None = Field(None, ge=1, le=3600)


class HangupData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pre_play: Prompt | None = None


# ─────────────────────────── Node + Edge + Graph ───────────────────────────

class NodePosition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = 0
    y: float = 0


class _NodeBase(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    position: NodePosition = Field(default_factory=NodePosition)


class StartNode(_NodeBase):
    type: Literal["start"]
    data: StartData = Field(default_factory=StartData)


class PlayNode(_NodeBase):
    type: Literal["play"]
    data: PlayData


class CollectNode(_NodeBase):
    type: Literal["collect"]
    data: CollectData


class ConditionNode(_NodeBase):
    type: Literal["condition"]
    data: ConditionData


class AssignQueueNode(_NodeBase):
    type: Literal["assign_queue"]
    data: AssignQueueData


class HangupNode(_NodeBase):
    type: Literal["hangup"]
    data: HangupData = Field(default_factory=HangupData)


Node = Annotated[
    Union[StartNode, PlayNode, CollectNode, ConditionNode, AssignQueueNode, HangupNode],
    Field(discriminator="type"),
]


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1, max_length=64)
    source: str = Field(..., min_length=1, max_length=64)
    target: str = Field(..., min_length=1, max_length=64)
    # For play/start: "next"; for collect: "success|no_input|no_match|error";
    # for condition: group.id or "default"; for assign_queue: "next|timeout".
    source_handle: str = Field("next", min_length=1, max_length=64)


class GraphVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=64)
    source_node_id: str = Field(..., min_length=1, max_length=64)


class VoiceFlowGraph(BaseModel):
    """The full graph stored in voice_flow_versions.graph_json."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    nodes: list[Node]
    edges: list[Edge] = Field(default_factory=list)
    variables: list[GraphVariable] = Field(default_factory=list)

    @field_validator("nodes")
    @classmethod
    def must_have_single_start(cls, v: list[Node]) -> list[Node]:
        starts = [n for n in v if n.type == "start"]
        if len(starts) != 1:
            raise ValueError("Graph must contain exactly one start node")
        return v

    @field_validator("nodes")
    @classmethod
    def node_ids_unique(cls, v: list[Node]) -> list[Node]:
        ids = [n.id for n in v]
        if len(set(ids)) != len(ids):
            raise ValueError("Node ids must be unique")
        return v


def default_graph() -> dict:
    """The initial graph used when a voice flow is first created."""

    return VoiceFlowGraph(
        version=1,
        nodes=[StartNode(id="start", type="start")],
        edges=[],
        variables=[],
    ).model_dump()


# ─────────────────────────── Validation result ───────────────────────────

class GraphError(BaseModel):
    node_id: str | None = None
    field: str | None = None
    code: str
    message: str


class GraphValidationResult(BaseModel):
    ok: bool
    errors: list[GraphError] = Field(default_factory=list)
