"""
Workspace queue API.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.db.deps import get_current_principal, get_db, get_redis, require_permission
from app.schemas.permission import EffectivePrincipal
from app.schemas.queue_workspace import (
    QueueAssignAndSendRequest,
    QueueAssignAndSendResponse,
    QueueAssignableAgentListResponse,
    QueueAssignRequest,
    QueueAssignSelfRequest,
    QueueAssignmentWorkspaceResponse,
    QueueWorkspaceCountResponse,
    QueueWorkspaceTaskDetail,
    QueueWorkspaceTaskListResponse,
)
from app.services.queue_workspace_service import QueueWorkspaceService

router = APIRouter(
    prefix="/workspace/queue",
    tags=["WorkspaceQueue"],
    dependencies=[Depends(require_permission("chat.workspace.use"))],
)


@router.get(
    "/tasks",
    response_model=QueueWorkspaceTaskListResponse,
    dependencies=[Depends(require_permission("chat.queue.view"))],
)
async def list_workspace_queue_tasks(
    queue_type: str | None = Query(None),
    queue_id: int | None = Query(None),
    q: str | None = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """List visible online-chat queue tasks for the workspace."""
    return await QueueWorkspaceService.list_tasks(
        db,
        principal,
        queue_type=queue_type,
        queue_id=queue_id,
        q=q,
    )


@router.get(
    "/tasks/count",
    response_model=QueueWorkspaceCountResponse,
    dependencies=[Depends(require_permission("chat.queue.view"))],
)
async def count_workspace_queue_tasks(
    queue_type: str | None = Query(None),
    queue_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Count visible online-chat queue tasks for workspace tab badges."""
    return await QueueWorkspaceService.count_tasks(
        db,
        principal,
        queue_type=queue_type,
        queue_id=queue_id,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=QueueWorkspaceTaskDetail,
    dependencies=[Depends(require_permission("chat.queue.view"))],
)
async def get_workspace_queue_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Get workspace queue task detail."""
    return await QueueWorkspaceService.get_detail(db, principal, task_id)


@router.get(
    "/assignable-agents",
    response_model=QueueAssignableAgentListResponse,
    dependencies=[Depends(require_permission("chat.queue.assign_other"))],
)
async def list_workspace_queue_assignable_agents(
    q: str | None = Query(None, max_length=100),
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """List agents that can receive workspace queue assignments."""
    return await QueueWorkspaceService.list_assignable_agents(db, r, principal, q=q)


@router.post(
    "/tasks/{task_id}/assign-self",
    response_model=QueueAssignmentWorkspaceResponse,
    dependencies=[Depends(require_permission("chat.queue.assign_self"))],
)
async def assign_workspace_queue_task_to_self(
    task_id: int,
    body: QueueAssignSelfRequest | None = None,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Assign a visible queue task to the current agent."""
    return await QueueWorkspaceService.assign_self(db, r, principal, task_id, body or QueueAssignSelfRequest())


@router.post(
    "/tasks/{task_id}/assign-self/send",
    response_model=QueueAssignAndSendResponse,
    dependencies=[Depends(require_permission("chat.queue.assign_self"))],
)
async def assign_workspace_queue_task_to_self_and_send(
    task_id: int,
    body: QueueAssignAndSendRequest,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Assign a visible queue task to the current agent and send a text reply."""
    return await QueueWorkspaceService.assign_self_and_send(db, r, principal, task_id, body)


@router.post(
    "/tasks/{task_id}/assign",
    response_model=QueueAssignmentWorkspaceResponse,
    dependencies=[Depends(require_permission("chat.queue.assign_other"))],
)
async def assign_workspace_queue_task(
    task_id: int,
    body: QueueAssignRequest,
    db: AsyncSession = Depends(get_db),
    r: aioredis.Redis = Depends(get_redis),
    principal: EffectivePrincipal = Depends(get_current_principal),
):
    """Assign a visible queue task to another agent."""
    return await QueueWorkspaceService.assign_to_agent(db, r, principal, task_id, body)
