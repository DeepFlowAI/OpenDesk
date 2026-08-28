"""Language detector provider factory."""
from __future__ import annotations

from functools import lru_cache

from app.configs.settings import settings
from app.libs.langdetect.base import BaseLanguageDetector


@lru_cache(maxsize=4)
def create_language_detector(provider: str | None = None) -> BaseLanguageDetector:
    """Create the configured language detector."""
    name = (provider or settings.LANGUAGE_DETECTOR_PROVIDER).strip().lower()
    match name:
        case "fasttext":
            from app.libs.langdetect.providers.fasttext import FastTextLanguageDetector

            return FastTextLanguageDetector()
        case _:
            raise ValueError(f"Unsupported language detector provider: {name}")
