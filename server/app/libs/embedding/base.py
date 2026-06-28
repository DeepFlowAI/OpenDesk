"""
Embedding provider interfaces.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider cannot return vectors."""


class BaseEmbeddingClient(ABC):
    @abstractmethod
    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector for each input text."""
