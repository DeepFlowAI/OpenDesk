"""Mock VOD client for local development and tests (no provider calls)."""
import uuid
from typing import Any

from app.libs.vod.base import BaseVodClient, VodPlayInfo, VodTranscodeEvent, VodUploadCredential


class MockVodClient(BaseVodClient):
    """Always succeeds; videos are considered transcoded instantly."""

    async def create_upload_credential(self, *, title: str, filename: str) -> VodUploadCredential:
        video_id = f"MOCK-{uuid.uuid4().hex[:20]}"
        return VodUploadCredential(
            video_id=video_id,
            upload_address=f"mock://vod-upload/{video_id}",
            upload_auth="mock-auth",
        )

    async def refresh_upload_credential(self, *, video_id: str) -> VodUploadCredential:
        return VodUploadCredential(
            video_id=video_id,
            upload_address=f"mock://vod-upload/{video_id}",
            upload_auth="mock-auth",
        )

    async def get_play_info(self, *, video_id: str) -> VodPlayInfo:
        return VodPlayInfo(
            video_id=video_id,
            play_url=f"mock://vod-play/{video_id}",
            duration_seconds=None,
            status="ok",
        )

    async def submit_transcode(self, *, video_id: str) -> bool:
        return True

    def parse_transcode_event(self, payload: dict[str, Any]) -> VodTranscodeEvent | None:
        video_id = payload.get("video_id")
        if not video_id:
            return None
        return VodTranscodeEvent(
            video_id=str(video_id),
            success=bool(payload.get("success", True)),
            duration_seconds=payload.get("duration_seconds"),
            raw=dict(payload),
        )
