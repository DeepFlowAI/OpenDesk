"""
Schemas for manual outbound task APIs.
"""
from datetime import datetime
from html import unescape
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.enums import FieldType


OutboundTaskStatus = Literal["draft", "active", "paused", "completed", "archived"]
OutboundTargetStatus = Literal["pending", "calling", "redial", "completed", "do_not_call", "invalid_number"]
OutboundScriptNodeType = Literal["start", "script", "branch", "end"]

SCRIPT_MAX_NODES = 100
SCRIPT_MAX_DEPTH = 20


def _plain_text_length(value: str | None) -> int:
    if not value:
        return 0
    text = re.sub(r"<[^>]*>", "", value)
    return len(unescape(text).replace("\u200b", "").strip())


class OutboundScriptPosition(BaseModel):
    x: float = 0
    y: float = 0


class OutboundScriptBranch(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=40)
    next_node_id: str = Field(min_length=1, max_length=64)

    @field_validator("id", "label", "next_node_id")
    @classmethod
    def strip_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Branch ID, label, and next step are required")
        return value


class OutboundScriptNode(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: OutboundScriptNodeType
    title: str = Field(default="", max_length=80)
    content: str | None = None
    agent_tip: str | None = None
    next_node_id: str | None = Field(default=None, max_length=64)
    branches: list[OutboundScriptBranch] = Field(default_factory=list)
    position: OutboundScriptPosition = Field(default_factory=OutboundScriptPosition)

    @field_validator("id")
    @classmethod
    def strip_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Script node ID is required")
        return value

    @field_validator("title", "next_node_id")
    @classmethod
    def strip_optional_value(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_content(self) -> "OutboundScriptNode":
        if self.type != "start" and not self.title:
            raise ValueError("Script step title is required")
        content_length = _plain_text_length(self.content)
        if self.type == "script" and content_length == 0:
            raise ValueError("Script step content is required")
        if content_length > 5000:
            raise ValueError("Script step content must be at most 5000 characters")
        if _plain_text_length(self.agent_tip) > 1000:
            raise ValueError("Agent tip must be at most 1000 characters")
        return self


class OutboundScript(BaseModel):
    version: Literal[1] = 1
    nodes: list[OutboundScriptNode] = Field(min_length=1, max_length=SCRIPT_MAX_NODES)

    @model_validator(mode="after")
    def validate_tree(self) -> "OutboundScript":
        node_by_id = {node.id: node for node in self.nodes}
        if len(node_by_id) != len(self.nodes):
            raise ValueError("Script node IDs must be unique")

        starts = [node for node in self.nodes if node.type == "start"]
        if len(starts) != 1:
            raise ValueError("Outbound script must contain exactly one start node")

        incoming = {node.id: 0 for node in self.nodes}
        adjacency: dict[str, list[str]] = {node.id: [] for node in self.nodes}
        for node in self.nodes:
            targets: list[str]
            if node.type in {"start", "script"}:
                if not node.next_node_id:
                    raise ValueError(f'Script step "{node.title or "Start"}" must have a next step')
                if node.branches:
                    raise ValueError("Only branch steps may contain branch options")
                targets = [node.next_node_id]
            elif node.type == "branch":
                if node.next_node_id:
                    raise ValueError("Branch steps must use branch option connections")
                if not 2 <= len(node.branches) <= 8:
                    raise ValueError(f'Script step "{node.title}" must contain 2 to 8 branch options')
                labels = [branch.label.casefold() for branch in node.branches]
                if len(labels) != len(set(labels)):
                    raise ValueError(f'Script step "{node.title}" contains duplicate branch labels')
                branch_ids = [branch.id for branch in node.branches]
                if len(branch_ids) != len(set(branch_ids)):
                    raise ValueError(f'Script step "{node.title}" contains duplicate branch IDs')
                targets = [branch.next_node_id for branch in node.branches]
            else:
                if node.next_node_id or node.branches:
                    raise ValueError("End steps cannot have a next step")
                targets = []

            for target_id in targets:
                if target_id not in node_by_id:
                    raise ValueError(f'Script step "{node.title or "Start"}" references a missing next step')
                adjacency[node.id].append(target_id)
                incoming[target_id] += 1

        start = starts[0]
        if incoming[start.id] != 0:
            raise ValueError("The start node cannot have a parent")
        if any(count > 1 for count in incoming.values()):
            raise ValueError("Outbound script does not support merged branches")

        visited: set[str] = set()
        active: set[str] = set()

        def visit(node_id: str, depth: int) -> None:
            if depth > SCRIPT_MAX_DEPTH:
                raise ValueError(f"Outbound script supports at most {SCRIPT_MAX_DEPTH} levels")
            if node_id in active:
                raise ValueError("Outbound script does not support cycles")
            if node_id in visited:
                return
            active.add(node_id)
            for child_id in adjacency[node_id]:
                visit(child_id, depth + 1)
            active.remove(node_id)
            visited.add(node_id)

        visit(start.id, 1)
        if len(visited) != len(self.nodes):
            raise ValueError("All script steps must be reachable from the start node")
        return self


class OutboundTaskField(BaseModel):
    key: str
    name: str
    field_type: FieldType
    required: bool = False
    agent_editable: bool = False
    show_in_list: bool = False
    enabled: bool = True
    type_config: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field key is required")
        if len(value) > 64:
            raise ValueError("Field key must be at most 64 characters")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Field name is required")
        if len(value) > 64:
            raise ValueError("Field name must be at most 64 characters")
        return value


class OutboundTemplateBase(BaseModel):
    name: str
    description: str | None = None
    fields: list[OutboundTaskField] = Field(default_factory=list)
    script: OutboundScript | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        if len(value) > 80:
            raise ValueError("Name must be at most 80 characters")
        return value

    @model_validator(mode="after")
    def validate_field_keys(self) -> "OutboundTemplateBase":
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Field keys must be unique")
        return self


class OutboundTemplateCreate(OutboundTemplateBase):
    pass


class OutboundTemplateUpdate(OutboundTemplateBase):
    expected_updated_at: datetime | None = None


class OutboundTemplateScriptUpdate(BaseModel):
    script: OutboundScript | None = None
    expected_updated_at: datetime | None = None


class OutboundTemplateScriptResponse(BaseModel):
    template_id: int
    name: str
    script: OutboundScript | None = None
    updated_at: datetime | None = None

    @computed_field
    @property
    def has_script(self) -> bool:
        return self.script is not None


class OutboundTemplateResponse(OutboundTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @computed_field
    @property
    def has_script(self) -> bool:
        return self.script is not None


class OutboundTemplateSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    name: str
    description: str | None = None
    fields: list[OutboundTaskField] = Field(default_factory=list)
    has_script: bool
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OutboundTaskBase(BaseModel):
    name: str
    description: str | None = None
    owner_id: int | None = None
    starts_at: datetime | None = None
    due_at: datetime | None = None
    allow_self_claim: bool = False
    default_redial_interval_minutes: int | None = None
    assignment_mode: str = "manual"
    assignee_scope_ids: list[int] = Field(default_factory=list)
    fields: list[OutboundTaskField] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        if len(value) > 80:
            raise ValueError("Name must be at most 80 characters")
        return value

    @model_validator(mode="after")
    def validate_times(self) -> "OutboundTaskBase":
        if self.starts_at and self.due_at and self.due_at < self.starts_at:
            raise ValueError("Due time must not be earlier than start time")
        return self


class OutboundTaskCreate(OutboundTaskBase):
    template_id: int
    publish: bool = False


class OutboundTaskUpdate(OutboundTaskBase):
    name: str | None = None


class OutboundTaskStats(BaseModel):
    total_targets: int = 0
    pending_targets: int = 0
    completed_targets: int = 0
    call_count: int = 0
    answered_count: int = 0


class OutboundTaskResponse(OutboundTaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    template_id: int | None = None
    template_name: str
    status: OutboundTaskStatus
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    script_snapshot: OutboundScript | None = None
    stats: OutboundTaskStats = Field(default_factory=OutboundTaskStats)

    @computed_field
    @property
    def has_script(self) -> bool:
        return self.script_snapshot is not None


class OutboundTaskSummaryResponse(OutboundTaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    template_id: int | None = None
    template_name: str
    status: OutboundTaskStatus
    created_by_id: int | None = None
    updated_by_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    has_script: bool
    stats: OutboundTaskStats = Field(default_factory=OutboundTaskStats)


class OutboundTargetCreate(BaseModel):
    phone_number: str
    user_id: int | None = None
    assignee_id: int | None = None
    field_values: dict[str, Any] = Field(default_factory=dict)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Phone number is required")
        if len(value) > 64:
            raise ValueError("Phone number must be at most 64 characters")
        return value


class OutboundTargetBulkCreateRequest(BaseModel):
    targets: list[OutboundTargetCreate] = Field(min_length=1, max_length=5000)


class OutboundTargetUpdate(BaseModel):
    phone_number: str | None = None
    user_id: int | None = None
    assignee_id: int | None = None
    status: OutboundTargetStatus | None = None
    field_values: dict[str, Any] | None = None
    next_follow_up_at: datetime | None = None


class OutboundTargetExecutionUpdate(BaseModel):
    status: OutboundTargetStatus | None = None
    field_values: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> "OutboundTargetExecutionUpdate":
        if self.status is None and self.field_values is None:
            raise ValueError("At least one change is required")
        return self


class OutboundTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    task_id: int
    phone_number: str
    user_id: int | None = None
    user_name: str | None = None
    assignee_id: int | None = None
    status: OutboundTargetStatus
    field_values: dict[str, Any]
    call_count: int
    answered_count: int
    last_called_at: datetime | None = None
    last_call_result: str | None = None
    next_follow_up_at: datetime | None = None
    total_talk_duration_ms: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OutboundTargetBulkCreateResponse(BaseModel):
    created: int
    items: list[OutboundTargetResponse]


class OutboundTargetTaskContextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    fields: list[OutboundTaskField] = Field(default_factory=list)
    has_script: bool


class OutboundTargetWithTaskResponse(OutboundTargetResponse):
    task: OutboundTargetTaskContextResponse


class OutboundRecordCreate(BaseModel):
    call_record_id: int | None = None
    started_at: datetime | None = None
    duration_ms: int | None = None
    answered: bool = False
    result: str | None = None
    notes: str | None = None
    target_status: OutboundTargetStatus = "completed"
    next_follow_up_at: datetime | None = None
    field_values: dict[str, Any] = Field(default_factory=dict)


class OutboundRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    task_id: int
    target_id: int
    call_record_id: int | None = None
    agent_id: int | None = None
    phone_number: str
    started_at: datetime
    duration_ms: int | None = None
    answered: bool
    result: str | None = None
    notes: str | None = None
    field_values: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MyOutboundTaskItem(BaseModel):
    id: int
    name: str
    status: str
    due_at: datetime | None = None
    my_total: int
    my_completed: int


class MyOutboundTaskListResponse(BaseModel):
    items: list[MyOutboundTaskItem]


class MyOutboundTargetRecordItem(BaseModel):
    id: int
    source: Literal["manual", "personal_auto"]
    started_at: datetime
    answered: bool
    result: str | None = None
    duration_ms: int | None = None
    agent_id: int | None = None
    agent_name: str | None = None
    call_record_id: int | None = None
    call_record_public_id: str | None = None
    can_view_detail: bool


class MyOutboundTargetRecordsResponse(BaseModel):
    items: list[MyOutboundTargetRecordItem]


class BulkAssignRequest(BaseModel):
    target_ids: list[int]
    assignee_id: int | None = None
    overwrite: bool = False


class BulkAssignResponse(BaseModel):
    updated: int


class BulkDeleteRequest(BaseModel):
    target_ids: list[int] = Field(min_length=1, max_length=5000)

    @field_validator("target_ids")
    @classmethod
    def validate_target_ids(cls, value: list[int]) -> list[int]:
        if any(target_id <= 0 for target_id in value):
            raise ValueError("Target IDs must be positive integers")
        return list(dict.fromkeys(value))


class BulkDeleteResponse(BaseModel):
    deleted: int


class OutboundTargetImportError(BaseModel):
    row_number: int
    phone_number: str | None = None
    reason: str


class OutboundTargetImportResponse(BaseModel):
    total: int
    created: int
    failed: int
    errors: list[OutboundTargetImportError] = Field(default_factory=list)


class PaginatedOutboundTemplates(BaseModel):
    items: list[OutboundTemplateSummaryResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedOutboundTasks(BaseModel):
    items: list[OutboundTaskSummaryResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedOutboundTargets(BaseModel):
    items: list[OutboundTargetResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedOutboundTargetsWithTask(BaseModel):
    items: list[OutboundTargetWithTaskResponse]
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedOutboundRecords(BaseModel):
    items: list[OutboundRecordResponse]
    total: int
    page: int
    per_page: int
    pages: int
