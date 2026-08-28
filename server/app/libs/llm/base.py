"""Provider-neutral LLM interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Literal


class LLMProviderError(RuntimeError):
    """Raised when no configured LLM deployment can complete a request."""


class BaseLLMClient(ABC):
    """Common interface for text completion providers."""

    @abstractmethod
    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout: float | None = None,
        reasoning_effort: Literal["high", "max"] | None = None,
    ) -> str:
        """Return the assistant text for an OpenAI-compatible message list."""
