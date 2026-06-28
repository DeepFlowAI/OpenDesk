"""
Abstract base class for VoiceSpeed clients.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


class VoiceSpeedClientError(Exception):
    """Raised when VoiceSpeed API calls fail."""


@dataclass(frozen=True)
class VoiceSpeedConnectionResult:
    ok: bool
    message: str


class BaseVoiceSpeedClient(ABC):

    @abstractmethod
    async def test_connection(self, base_url: str, api_key: str) -> VoiceSpeedConnectionResult:
        """Test whether VoiceSpeed accepts the provided API key."""
        ...
