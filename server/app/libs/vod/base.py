"""VOD (video-on-demand) provider client contract."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VodUploadCredential:
    """Credential that lets a browser upload one video straight to the provider."""

    video_id: str
    upload_address: str
    upload_auth: str


@dataclass
class VodPlayInfo:
    """Normalized playback info for one video."""

    video_id: str
    play_url: str | None = None
    duration_seconds: int | None = None
    status: str = "ok"  # ok | processing | failed


@dataclass
class VodTranscodeEvent:
    """Normalized transcode result parsed from a provider event callback."""

    video_id: str
    success: bool
    duration_seconds: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class BaseVodClient(ABC):
    """Provider-agnostic VOD client used by the learning center."""

    @abstractmethod
    async def create_upload_credential(self, *, title: str, filename: str) -> VodUploadCredential:
        """Create a fresh video entry and return the direct-upload credential."""

    @abstractmethod
    async def refresh_upload_credential(self, *, video_id: str) -> VodUploadCredential:
        """Refresh the upload credential for an interrupted upload."""

    @abstractmethod
    async def get_play_info(self, *, video_id: str) -> VodPlayInfo:
        """Return playback URL / status for one video."""

    @abstractmethod
    async def submit_transcode(self, *, video_id: str) -> bool:
        """(Re)submit a transcode job for one video. Returns acceptance."""

    @abstractmethod
    def parse_transcode_event(self, payload: dict[str, Any]) -> VodTranscodeEvent | None:
        """Parse one provider callback payload; ``None`` when the event is irrelevant."""
