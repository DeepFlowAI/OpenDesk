"""
VOD provider transcode-event callback.

The VOD provider (e.g. Aliyun event notification) posts transcode results here;
access is guarded by a shared token (settings.ALIYUN_VOD_CALLBACK_TOKEN) instead
of tenant auth, since the caller is the provider.
"""
import hmac
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import NotFoundError
from app.db.deps import get_db
from app.services.learning_admin_service import LearningMaterialAdminService

router = APIRouter(tags=["Learning Callback"])


@router.post("/learning/vod/callback/{provider}")
async def vod_transcode_callback(
    provider: str,
    token: str = Query(default=""),
    payload: dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
) -> dict:
    expected = settings.ALIYUN_VOD_CALLBACK_TOKEN or ""
    if not expected or not hmac.compare_digest(token, expected):
        raise NotFoundError()
    if provider != settings.VOD_PROVIDER:
        raise NotFoundError()
    received = await LearningMaterialAdminService.handle_vod_event(db, provider=provider, payload=payload)
    return {"received": 1 if received else 0}
