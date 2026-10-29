"""Open API: list call recordings and issue fresh download links."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.exceptions import ConflictError, NotFoundError, RateLimitedError
from app.db.redis import redis_client
from app.db.session import AsyncSessionLocal
from app.libs.storage.factory import create_storage_client
from app.models.call_recording import CallRecording
from app.models.call_recording_link_audit import CallRecordingLinkAudit
from app.repositories.open_call_recording_repository import OpenCallRecordingRepository
from app.schemas.open_api import OpenApiContext
from app.schemas.open_call_recording import (
    OpenCallRecordingItem,
    OpenCallRecordingLinkResponse,
    OpenCallRecordingListResponse,
)
from app.services.call_event_publisher import (
    RECORDING_LINK_TTL_SECONDS,
    public_recording_phase,
)

logger = logging.getLogger(__name__)

LINKS_PER_MINUTE = 60
_RATE_KEY = "open_call_recording_links:{api_key_id}:{minute}"
_REDIS_TIMEOUT_SECONDS = 0.5


def _parse_public_id(value: str, message: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise NotFoundError(message) from exc


def _signable(recording: CallRecording) -> bool:
    return recording.status != "failed" and bool(recording.storage_key)


class OpenCallRecordingService:
    @staticmethod
    async def _consume_rate_limit(context: OpenApiContext, count: int) -> None:
        """Count issued links per API key per minute; Redis outages fail open."""
        if count <= 0:
            return
        key = _RATE_KEY.format(
            api_key_id=context.api_key_id, minute=int(time.time() // 60)
        )
        try:
            client = redis_client.client
            used = await asyncio.wait_for(
                client.incrby(key, count), timeout=_REDIS_TIMEOUT_SECONDS
            )
            if used == count:
                await asyncio.wait_for(
                    client.expire(key, 120), timeout=_REDIS_TIMEOUT_SECONDS
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "open recording link rate limit unavailable api_key_id=%s error_type=%s",
                context.api_key_id,
                type(exc).__name__,
            )
            return
        if int(used) > LINKS_PER_MINUTE:
            raise RateLimitedError("Too many recording link requests")

    @staticmethod
    async def _sign(storage_key: str) -> tuple[str, datetime]:
        issued_at = datetime.now(timezone.utc)
        url = await create_storage_client().get_temporary_url(
            storage_key, expires_seconds=RECORDING_LINK_TTL_SECONDS
        )
        return url, issued_at + timedelta(seconds=RECORDING_LINK_TTL_SECONDS)

    @staticmethod
    async def _write_audits(
        context: OpenApiContext, call_public_id: UUID, recording_public_ids: list[UUID]
    ) -> None:
        if not recording_public_ids:
            return
        async with AsyncSessionLocal() as db:
            OpenCallRecordingRepository.add_audits(
                db,
                [
                    CallRecordingLinkAudit(
                        tenant_id=context.tenant_id,
                        api_key_id=context.api_key_id,
                        api_key_name=context.api_key_name,
                        call_public_id=call_public_id,
                        recording_public_id=recording_public_id,
                    )
                    for recording_public_id in recording_public_ids
                ],
            )
            await db.commit()

    @staticmethod
    async def list_for_call_managed(
        context: OpenApiContext, call_public_id: str
    ) -> OpenCallRecordingListResponse:
        call_uuid = _parse_public_id(call_public_id, "Call not found")
        async with AsyncSessionLocal() as db:
            call = await OpenCallRecordingRepository.get_call(
                db, tenant_id=context.tenant_id, call_public_id=call_uuid
            )
            if call is None:
                raise NotFoundError("Call not found")
            recordings = await OpenCallRecordingRepository.list_for_call(db, call.id)

        signable = [item for item in recordings if _signable(item)]
        await OpenCallRecordingService._consume_rate_limit(context, len(signable))

        items: list[OpenCallRecordingItem] = []
        for recording in recordings:
            url = expires_at = None
            if _signable(recording):
                url, expires_at = await OpenCallRecordingService._sign(recording.storage_key)
            items.append(
                OpenCallRecordingItem(
                    public_id=recording.public_id,
                    phase=public_recording_phase(recording.phase),
                    status=recording.status,
                    started_at=recording.started_at,
                    ended_at=recording.ended_at,
                    duration_ms=recording.duration_ms,
                    download_url=url,
                    download_url_expires_at=expires_at,
                    failure_reason=(
                        "recording_failed" if recording.status == "failed" else None
                    ),
                )
            )
        await OpenCallRecordingService._write_audits(
            context, call_uuid, [item.public_id for item in signable]
        )
        return OpenCallRecordingListResponse(call_public_id=call_uuid, items=items)

    @staticmethod
    async def get_download_url_managed(
        context: OpenApiContext, recording_public_id: str
    ) -> OpenCallRecordingLinkResponse:
        recording_uuid = _parse_public_id(recording_public_id, "Recording not found")
        async with AsyncSessionLocal() as db:
            found = await OpenCallRecordingRepository.get_recording(
                db, tenant_id=context.tenant_id, recording_public_id=recording_uuid
            )
        if found is None:
            raise NotFoundError("Recording not found")
        recording, call_public_id = found
        if not _signable(recording):
            raise ConflictError("Recording file is not available")

        await OpenCallRecordingService._consume_rate_limit(context, 1)
        url, expires_at = await OpenCallRecordingService._sign(recording.storage_key)
        await OpenCallRecordingService._write_audits(
            context, call_public_id, [recording_uuid]
        )
        return OpenCallRecordingLinkResponse(
            public_id=recording_uuid,
            call_public_id=call_public_id,
            download_url=url,
            download_url_expires_at=expires_at,
        )
