"""
Call center Open API router authenticated by tenant API keys.

Exposes call recordings and fresh, time-limited download links.
"""

from fastapi import APIRouter, Depends

from app.db.open_api_deps import get_open_api_context_short_session
from app.schemas.open_api import OpenApiContext
from app.schemas.open_call_recording import (
    OpenCallRecordingLinkResponse,
    OpenCallRecordingListResponse,
)
from app.services.open_call_recording_service import OpenCallRecordingService

router = APIRouter(prefix="/open/call-center", tags=["OpenCallCenter"])


@router.get(
    "/calls/{call_public_id}/recordings",
    response_model=OpenCallRecordingListResponse,
)
async def list_open_call_recordings(
    call_public_id: str,
    context: OpenApiContext = Depends(get_open_api_context_short_session),
):
    """List a call's recordings with freshly issued one-hour download links."""
    return await OpenCallRecordingService.list_for_call_managed(context, call_public_id)


@router.get(
    "/recordings/{recording_public_id}/download-url",
    response_model=OpenCallRecordingLinkResponse,
)
async def get_open_call_recording_download_url(
    recording_public_id: str,
    context: OpenApiContext = Depends(get_open_api_context_short_session),
):
    """Issue a fresh one-hour download link for one recording."""
    return await OpenCallRecordingService.get_download_url_managed(
        context, recording_public_id
    )
