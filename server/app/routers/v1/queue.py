"""
Unified queue engine API.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.deps import get_current_user, get_db, get_redis
from app.schemas.queue import (
    QueueAdminAssignRequest,
    QueueDispatchRequest,
    QueueDispatchResponse,
    QueueEnqueueRequest,
    QueueEnqueueResponse,
    QueuePolicyListResponse,
    QueuePolicyResponse,
    QueuePolicyUpsert,
    QueuePositionResponse,
    QueuePullRequest,
    QueueStateResponse,
    QueueTaskActionRequest,
    QueueTaskResponse,
)
from app.services.queue_service import QueuePolicyService, QueueTaskService

router = APIRouter(prefix="/queue", tags=["Queue"])


@router.get("/policies", response_model=QueuePolicyListResponse)
async def list_queue_policies(
    channel: str | None = None,
    scope_type: str | None = None,
    scope_id: int | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List queue policies for the current tenant."""
    return await QueuePolicyService.list_policies(
        db,
        current_user["tenant_id"],
        channel=channel,
        scope_type=scope_type,
        scope_id=scope_id,
    )


@router.put("/policies", response_model=QueuePolicyResponse)
async def upsert_queue_policy(
    body: QueuePolicyUpsert,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a queue policy."""
    return await QueuePolicyService.upsert_policy(db, current_user["tenant_id"], body)


@router.post("/tasks/enqueue", response_model=QueueEnqueueResponse)
async def enqueue_queue_task(
    body: QueueEnqueueRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enqueue a task into an employee-group or employee queue."""
    return await QueueTaskService.enqueue_task(db, current_user["tenant_id"], body)


@router.get("/tasks/{task_id}", response_model=QueueTaskResponse)
async def get_queue_task(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get queue task detail."""
    return await QueueTaskService.get_task(db, current_user["tenant_id"], task_id)


@router.get("/tasks/{task_id}/position", response_model=QueuePositionResponse)
async def get_queue_task_position(
    task_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get queue task position."""
    return await QueueTaskService.get_position_for_task(db, current_user["tenant_id"], task_id)


@router.post("/tasks/{task_id}/cancel", response_model=QueueTaskResponse)
async def cancel_queue_task(
    task_id: int,
    body: QueueTaskActionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an active queue task."""
    return await QueueTaskService.cancel_task(db, current_user["tenant_id"], task_id, body)


@router.post("/tasks/{task_id}/timeout", response_model=QueueTaskResponse)
async def timeout_queue_task(
    task_id: int,
    body: QueueTaskActionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark an active queue task as timed out."""
    return await QueueTaskService.timeout_task(db, current_user["tenant_id"], task_id, body)


@router.post("/tasks/{task_id}/admin-assign", response_model=QueueTaskResponse)
async def admin_assign_queue_task(
    task_id: int,
    body: QueueAdminAssignRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Force assign an online-chat queue task to an agent."""
    return await QueueTaskService.admin_assign(
        db,
        r,
        current_user["tenant_id"],
        current_user["user_id"],
        task_id,
        body,
    )


@router.post("/tasks/pull", response_model=QueueTaskResponse)
async def pull_queue_task(
    body: QueuePullRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Pull the next online-chat task from queues available to the agent."""
    return await QueueTaskService.pull_next(
        db,
        r,
        current_user["tenant_id"],
        current_user["user_id"],
        body,
    )


@router.get("/state", response_model=QueueStateResponse)
async def get_queue_state(
    channel: str,
    queue_type: str,
    queue_id: int,
    task_id: int | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Get queue status and priority distribution."""
    return await QueueTaskService.state(
        db,
        r,
        current_user["tenant_id"],
        channel=channel,
        queue_type=queue_type,
        queue_id=queue_id,
        task_id=task_id,
    )


@router.post("/dispatch", response_model=QueueDispatchResponse)
async def dispatch_queue(
    body: QueueDispatchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
):
    """Trigger automatic dispatch for one queue."""
    return await QueueTaskService.dispatch(db, r, current_user["tenant_id"], body)
