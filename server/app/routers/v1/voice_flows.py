"""
Voice flow router — full CRUD + graph version + audio assets + system vars.
"""
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db, get_current_user
from app.repositories.voice_flow_system_variable_repository import (
    VoiceFlowSystemVariableRepository,
)
from app.schemas.voice_flow import (
    AudioAssetResponse,
    SystemVariableItem,
    SystemVariableListResponse,
    VoiceFlowCreate,
    VoiceFlowListResponse,
    VoiceFlowResponse,
    VoiceFlowSelectListResponse,
    VoiceFlowUpdate,
    VoiceFlowValidateRequest,
    VoiceFlowVersionDetail,
    VoiceFlowVersionListResponse,
    GraphValidationResult,
)
from app.services.audio_asset_service import AudioAssetService
from app.services.audit_actor_service import AuditActorService
from app.services.voice_flow_service import VoiceFlowService

router = APIRouter(prefix="/voice-flows", tags=["VoiceFlows"])


# ─────────────── Static / Lookup endpoints (declared first) ───────────────


@router.get("/select", response_model=VoiceFlowSelectListResponse)
async def list_voice_flows_for_select(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enabled, non-deleted flows for routing rule dropdown."""

    return await VoiceFlowService.list_for_select(db, current_user["tenant_id"])


@router.get("/system-variables", response_model=SystemVariableListResponse)
async def list_system_variables(db: AsyncSession = Depends(get_db)):
    """Read-only seed of `sys.*` variables — used by the variables reference popup."""

    rows = await VoiceFlowSystemVariableRepository.list_all(db)
    return {"items": [SystemVariableItem.model_validate(r) for r in rows]}


# ─────────────── Audio assets ───────────────


@router.post("/audio-assets", response_model=AudioAssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_audio_asset(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    actor = await AuditActorService.resolve_current_employee(
        db, tenant_id, current_user.get("user_id")
    )
    data = await file.read()
    return await AudioAssetService.upload(
        db,
        tenant_id,
        actor,
        filename=file.filename or "audio.bin",
        content_type=file.content_type,
        data=data,
    )


@router.get("/audio-assets/{asset_id}", response_model=AudioAssetResponse)
async def get_audio_asset(
    asset_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await AudioAssetService.get(db, asset_id, current_user["tenant_id"])


@router.delete("/audio-assets/{asset_id}")
async def delete_audio_asset(
    asset_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await AudioAssetService.delete(db, asset_id, current_user["tenant_id"])
    return {"message": "Deleted successfully"}


# ─────────────── Voice flow CRUD ───────────────


@router.get("", response_model=VoiceFlowListResponse)
async def list_voice_flows(
    page: int = 1,
    per_page: int = 10,
    keyword: str | None = None,
    include_deleted: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await VoiceFlowService.get_paginated(
        db, current_user["tenant_id"], page, per_page, keyword, include_deleted
    )


@router.post("", response_model=VoiceFlowResponse, status_code=status.HTTP_201_CREATED)
async def create_voice_flow(
    body: VoiceFlowCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    actor = await AuditActorService.resolve_current_employee(
        db, tenant_id, current_user.get("user_id")
    )
    return await VoiceFlowService.create(db, tenant_id, actor, body)


@router.get("/{flow_id}", response_model=VoiceFlowResponse)
async def get_voice_flow(
    flow_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await VoiceFlowService.get_by_id(db, flow_id, current_user["tenant_id"])


@router.put("/{flow_id}", response_model=VoiceFlowResponse)
async def update_voice_flow(
    flow_id: int,
    body: VoiceFlowUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    actor = await AuditActorService.resolve_current_employee(
        db, tenant_id, current_user.get("user_id")
    )
    return await VoiceFlowService.update(db, flow_id, tenant_id, actor, body)


@router.delete("/{flow_id}")
async def delete_voice_flow(
    flow_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await VoiceFlowService.delete(db, flow_id, current_user["tenant_id"])
    return {"message": "Deleted successfully"}


@router.post("/{flow_id}/validate", response_model=GraphValidationResult)
async def validate_voice_flow_graph(
    flow_id: int,
    body: VoiceFlowValidateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # flow_id is reserved for future contextual checks (e.g. referencing other flows).
    return await VoiceFlowService.validate(db, current_user["tenant_id"], body.graph_json)


# ─────────────── Versions ───────────────


@router.get("/{flow_id}/versions", response_model=VoiceFlowVersionListResponse)
async def list_voice_flow_versions(
    flow_id: int,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await VoiceFlowService.list_versions(
        db, flow_id, current_user["tenant_id"], min(limit, 200)
    )


@router.get(
    "/{flow_id}/versions/{version_no}",
    response_model=VoiceFlowVersionDetail,
)
async def get_voice_flow_version(
    flow_id: int,
    version_no: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await VoiceFlowService.get_version(
        db, flow_id, version_no, current_user["tenant_id"]
    )


@router.post(
    "/{flow_id}/rollback/{version_no}",
    response_model=VoiceFlowResponse,
)
async def rollback_voice_flow(
    flow_id: int,
    version_no: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = current_user["tenant_id"]
    actor = await AuditActorService.resolve_current_employee(
        db, tenant_id, current_user.get("user_id")
    )
    return await VoiceFlowService.rollback_to_version(
        db, flow_id, version_no, tenant_id, actor
    )
