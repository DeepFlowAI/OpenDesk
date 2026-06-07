"""
Ticket workflow graph schemas.

The graph is intentionally compact and mirrors the product scope:
trigger, branch, update_record, and end nodes.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ConditionLogic = Literal["AND", "OR"]
EventType = Literal["create", "update"]
ValueScope = Literal["current", "before"]
UpdateAction = Literal["set", "clear"]


class WorkflowCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: int | None = Field(None, gt=0)
    field_key: str | None = Field(None, min_length=1, max_length=64)
    value_scope: ValueScope | None = "current"
    operator: str = Field(..., min_length=1, max_length=64)
    value: Any = None

    @model_validator(mode="after")
    def validate_ref(self) -> "WorkflowCondition":
        if (self.field_id is None) == (self.field_key is None):
            raise ValueError("Exactly one of field_id or field_key is required")
        return self


class TriggerData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_types: list[EventType] = Field(default_factory=lambda: ["create", "update"])
    condition_logic: ConditionLogic = "AND"
    conditions: list[WorkflowCondition] = Field(default_factory=list)

    @field_validator("event_types")
    @classmethod
    def unique_event_types(cls, v: list[EventType]) -> list[EventType]:
        if not v:
            raise ValueError("At least one event type is required")
        if len(set(v)) != len(v):
            raise ValueError("Event types must be unique")
        return v


class BranchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=80)
    is_default: bool = False
    condition_logic: ConditionLogic = "AND"
    conditions: list[WorkflowCondition] = Field(default_factory=list)


class BranchData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branches: list[BranchItem] = Field(..., min_length=2)

    @field_validator("branches")
    @classmethod
    def validate_branches(cls, v: list[BranchItem]) -> list[BranchItem]:
        ids = [b.id for b in v]
        if len(set(ids)) != len(ids):
            raise ValueError("Branch ids must be unique")
        defaults = [b for b in v if b.is_default]
        if len(defaults) != 1:
            raise ValueError("Exactly one default branch is required")
        return v


class UpdateOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_field_id: int | None = Field(None, gt=0)
    target_field_key: str | None = Field(None, min_length=1, max_length=64)
    action: UpdateAction = "set"
    value: Any = None

    @model_validator(mode="after")
    def validate_ref(self) -> "UpdateOperation":
        if (self.target_field_id is None) == (self.target_field_key is None):
            raise ValueError("Exactly one of target_field_id or target_field_key is required")
        if self.action == "clear":
            self.value = None
        return self


class UpdateRecordData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[UpdateOperation] = Field(..., min_length=1, max_length=20)


class EndData(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NodePosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = 0
    y: float = 0


class _NodeBase(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    position: NodePosition = Field(default_factory=NodePosition)


class TriggerNode(_NodeBase):
    type: Literal["trigger"]
    data: TriggerData = Field(default_factory=TriggerData)


class BranchNode(_NodeBase):
    type: Literal["branch"]
    data: BranchData


class UpdateRecordNode(_NodeBase):
    type: Literal["update_record"]
    data: UpdateRecordData


class EndNode(_NodeBase):
    type: Literal["end"]
    data: EndData = Field(default_factory=EndData)


Node = Annotated[
    Union[TriggerNode, BranchNode, UpdateRecordNode, EndNode],
    Field(discriminator="type"),
]


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=64)
    source: str = Field(..., min_length=1, max_length=64)
    target: str = Field(..., min_length=1, max_length=64)
    source_handle: str = Field("next", min_length=1, max_length=64)


class TicketWorkflowGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    nodes: list[Node]
    edges: list[Edge] = Field(default_factory=list)

    @field_validator("nodes")
    @classmethod
    def validate_node_ids(cls, v: list[Node]) -> list[Node]:
        ids = [n.id for n in v]
        if len(set(ids)) != len(ids):
            raise ValueError("Node ids must be unique")
        triggers = [n for n in v if n.type == "trigger"]
        if len(triggers) != 1:
            raise ValueError("Graph must contain exactly one trigger node")
        ends = [n for n in v if n.type == "end"]
        if not ends:
            raise ValueError("Graph must contain at least one end node")
        return v


class GraphError(BaseModel):
    node_id: str | None = None
    field: str | None = None
    code: str
    message: str


class GraphValidationResult(BaseModel):
    ok: bool
    errors: list[GraphError] = Field(default_factory=list)


def default_graph() -> dict:
    return TicketWorkflowGraph(
        version=1,
        nodes=[
            TriggerNode(id="trigger", type="trigger", position=NodePosition(x=0, y=0)),
            EndNode(id="end", type="end", position=NodePosition(x=0, y=220)),
        ],
        edges=[
            Edge(id="edge-trigger-end", source="trigger", target="end", source_handle="next"),
        ],
    ).model_dump()
