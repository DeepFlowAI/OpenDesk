"""
VoiceSpeed client factory.
"""
from app.configs.settings import settings
from app.libs.voice_speed.base import BaseVoiceSpeedClient


def create_voice_speed_client() -> BaseVoiceSpeedClient:
    provider = settings.VOICE_SPEED_PROVIDER
    match provider:
        case "http":
            from app.libs.voice_speed.providers.http import HTTPVoiceSpeedClient
            return HTTPVoiceSpeedClient()
        case _:
            raise ValueError(f"Unsupported VoiceSpeed provider: {provider}")
