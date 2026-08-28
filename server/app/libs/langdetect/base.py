"""Provider-neutral language detection interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class LanguageDetectionError(RuntimeError):
    """Raised when a language detector cannot classify input text."""


@dataclass(frozen=True, slots=True)
class LanguageDetection:
    """Normalized language prediction."""

    language: str
    confidence: float


class BaseLanguageDetector(ABC):
    """Common interface for local or remote language detectors."""

    @abstractmethod
    async def detect(self, text: str) -> LanguageDetection:
        """Detect the dominant ISO language code for text."""
