"""Provider-neutral language detector factory."""

from app.libs.langdetect.base import BaseLanguageDetector, LanguageDetection, LanguageDetectionError
from app.libs.langdetect.factory import create_language_detector

__all__ = [
    "BaseLanguageDetector",
    "LanguageDetection",
    "LanguageDetectionError",
    "create_language_detector",
]
