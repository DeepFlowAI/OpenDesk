"""
Staff app telemetry — authenticated batch ingest for the admin/workspace UI.
"""
from fastapi import APIRouter, Depends

from app.db.deps import get_optional_current_user
from app.schemas.telemetry import TelemetryBatchRequest, TelemetryBatchResponse
from app.services.telemetry_service import TelemetryService

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])


@router.post("/events", response_model=TelemetryBatchResponse)
async def post_app_telemetry_events(
    body: TelemetryBatchRequest,
    current_user: dict | None = Depends(get_optional_current_user),
):
    """Batch-ingest staff app telemetry events (auth lifecycle, UI diagnostics)."""
    return await TelemetryService.ingest_app(body=body, user_payload=current_user)
