"""Aliyun VOD client (vod20170321 SDK, lazily imported; sync SDK offloaded to a thread)."""
import asyncio
import json
import logging
from typing import Any

from app.libs.vod.base import BaseVodClient, VodPlayInfo, VodTranscodeEvent, VodUploadCredential

logger = logging.getLogger(__name__)

# VOD video statuses that mean "ready to play".
_READY_STATUSES = {"Normal", "Checking"}
_PROCESSING_STATUSES = {"Uploading", "UploadSucc", "Transcoding", "Blocked", "Preparing", "Audit"}
_FAILED_STATUSES = {"TranscodeFail", "UploadFail", "Deleted", "AuditFail"}


class AliyunVodClient(BaseVodClient):
    def __init__(
        self,
        *,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str,
        template_group_id: str = "",
    ) -> None:
        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret
        self._endpoint = endpoint
        self._template_group_id = template_group_id

    def _build_client(self) -> Any:
        # Lazy import so local/dev environments do not need the SDK installed.
        from alibabacloud_vod20170321.client import Client
        from alibabacloud_tea_openapi.models import Config

        config = Config(
            access_key_id=self._access_key_id,
            access_key_secret=self._access_key_secret,
            endpoint=self._endpoint,
        )
        return Client(config)

    async def create_upload_credential(self, *, title: str, filename: str) -> VodUploadCredential:
        from alibabacloud_vod20170321 import models as vod_models

        request = vod_models.CreateUploadVideoRequest(title=title, file_name=filename)
        if self._template_group_id:
            request.template_group_id = self._template_group_id
        response = await asyncio.to_thread(self._build_client().create_upload_video, request)
        body = response.body
        return VodUploadCredential(
            video_id=body.video_id,
            upload_address=body.upload_address,
            upload_auth=body.upload_auth,
        )

    async def refresh_upload_credential(self, *, video_id: str) -> VodUploadCredential:
        from alibabacloud_vod20170321 import models as vod_models

        request = vod_models.RefreshUploadVideoRequest(video_id=video_id)
        response = await asyncio.to_thread(self._build_client().refresh_upload_video, request)
        body = response.body
        return VodUploadCredential(
            video_id=video_id,
            upload_address=body.upload_address,
            upload_auth=body.upload_auth,
        )

    async def get_play_info(self, *, video_id: str) -> VodPlayInfo:
        from alibabacloud_vod20170321 import models as vod_models

        client = self._build_client()
        play_request = vod_models.GetPlayInfoRequest(video_id=video_id, formats="mp4,m3u8")
        video_request = vod_models.GetVideoInfoRequest(video_id=video_id)
        play_response, video_response = await asyncio.gather(
            asyncio.to_thread(client.get_play_info, play_request),
            asyncio.to_thread(client.get_video_info, video_request),
        )
        play_list = list(getattr(play_response.body, "play_info_list", None).play_info or [])
        # Prefer progressive mp4 so the native <video> element can play it everywhere.
        play_list.sort(key=lambda item: 0 if (getattr(item, "format", "") or "").lower() == "mp4" else 1)
        play_url = getattr(play_list[0], "play_url", None) if play_list else None

        video = getattr(video_response.body, "video", None)
        vod_status = getattr(video, "status", "") or ""
        if vod_status in _READY_STATUSES:
            status = "ok"
        elif vod_status in _FAILED_STATUSES:
            status = "failed"
        else:
            status = "processing"
        duration = getattr(video, "duration", None)
        return VodPlayInfo(
            video_id=video_id,
            play_url=play_url,
            duration_seconds=int(float(duration)) if duration else None,
            status=status,
        )

    async def submit_transcode(self, *, video_id: str) -> bool:
        from alibabacloud_vod20170321 import models as vod_models

        request = vod_models.SubmitTranscodeJobsRequest(video_id=video_id)
        if self._template_group_id:
            request.template_group_id = self._template_group_id
        try:
            await asyncio.to_thread(self._build_client().submit_transcode_jobs, request)
            return True
        except Exception:
            logger.exception("Aliyun SubmitTranscodeJobs failed for video %s", video_id)
            return False

    def parse_transcode_event(self, payload: dict[str, Any]) -> VodTranscodeEvent | None:
        """Parse one VOD event-notification item (HTTP callback body)."""
        # FileTranscodeComplete is the legacy name of StreamTranscodeComplete;
        # both may arrive depending on which events the console subscribes to.
        event_type = payload.get("EventType")
        if event_type not in {"FileTranscodeComplete", "StreamTranscodeComplete", "TranscodeComplete"}:
            return None
        data = payload.get("EventData") or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                data = {}
        video_id = data.get("VideoId") or payload.get("VideoId")
        if not video_id:
            return None
        status = str(data.get("Status") or payload.get("Status") or "").lower()
        duration = data.get("Duration") or payload.get("Duration")
        return VodTranscodeEvent(
            video_id=str(video_id),
            success=status in {"success", "succeed", "ok"},
            duration_seconds=int(float(duration)) if duration else None,
            raw=dict(payload),
        )
