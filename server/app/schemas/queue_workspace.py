"""
Workspace queue schemas.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.conversation import AgentBrief, ChannelBrief, GroupBrief, VisitorBrief
from app.schemas.message import MessageResponse


class QueueWorkspaceQueueBrief(BaseModel):
    queue_type: str
    queue_id: int
    name: str | None = None
    waiting_count: int = 0


class QueueWorkspaceTaskItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: Literal["queue_task"] = "queue_task"
    queue_task_id: int
    conversation_id: int | None = None
    conversation_public_id: str | None = None
    visitor: VisitorBrief | None = None
    channel: ChannelBrief | None = None
    group: GroupBrief | None = None
    queue: QueueWorkspaceQueueBrief
    priority: int
    status: str
    source_type: str
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    enqueued_at: datetime | None = None
    wait_seconds: int
    position_overall: int | None = None
    position_in_priority: int | None = None


class QueueWorkspaceTaskListResponse(BaseModel):
    items: list[QueueWorkspaceTaskItem]
    total: int
    visible_queues: list[QueueWorkspaceQueueBrief] = Field(default_factory=list)


class QueueWorkspaceCountResponse(BaseModel):
    total: int


class QueueWorkspaceTaskDetail(QueueWorkspaceTaskItem):
    messages: list[MessageResponse] = Field(default_factory=list)
    can_assign_self: bool
    can_assign_other: bool


class QueueAssignableAgent(BaseModel):
    id: int
    name: str
    display_name: str | None = None
    job_number: str | None = None
    avatar: str | None = None
    group_ids: list[int] = Field(default_factory=list)
    group_names: list[str] = Field(default_factory=list)
    online_status: str
    current_count: int
    max_concurrent: int
    selectable: bool


class QueueAssignableAgentListResponse(BaseModel):
    items: list[QueueAssignableAgent]
    total: int


class QueueAssignSelfRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class QueueAssignRequest(QueueAssignSelfRequest):
    agent_id: int = Field(gt=0)


class QueueAssignmentWorkspaceResponse(BaseModel):
    task: QueueWorkspaceTaskItem
    conversation_id: int | None = None
    assigned_agent: AgentBrief | None = None
    assigned_to_current_user: bool


class QueueAssignAndSendRequest(BaseModel):
    content: str = Field(..., max_length=5000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("Message content is required")
        return content


class QueueAssignAndSendResponse(QueueAssignmentWorkspaceResponse):
    message: MessageResponse | None = None
    message_sent: bool
