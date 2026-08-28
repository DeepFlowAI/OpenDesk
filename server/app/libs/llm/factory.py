"""LLM provider factory."""
from __future__ import annotations

from app.configs.settings import settings
from app.libs.llm.base import BaseLLMClient


def create_llm_client(provider: str | None = None) -> BaseLLMClient:
    """Create the configured provider-neutral LLM client."""
    name = (provider or settings.LLM_PROVIDER).strip().lower()
    match name:
        case "litellm":
            from app.libs.llm.providers.litellm import LiteLLMClient

            return LiteLLMClient()
        case _:
            raise ValueError(f"Unsupported LLM provider: {name}")
