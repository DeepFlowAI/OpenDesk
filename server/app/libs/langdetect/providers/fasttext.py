"""Facebook fastText lid.176 language detector."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.configs.settings import settings
from app.libs.langdetect.base import BaseLanguageDetector, LanguageDetection, LanguageDetectionError


class FastTextLanguageDetector(BaseLanguageDetector):
    """Lazily load and reuse the configured fastText language model."""

    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = (model_path or settings.FASTTEXT_LANGUAGE_MODEL_PATH).strip()
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if not self._model_path:
            raise LanguageDetectionError("fastText language model path is not configured")
        path = Path(self._model_path)
        if not path.is_file():
            raise LanguageDetectionError("fastText language model file does not exist")
        try:
            import fasttext
        except ImportError as exc:
            raise LanguageDetectionError("fastText is not installed") from exc
        try:
            self._model = fasttext.load_model(str(path))
        except Exception as exc:
            raise LanguageDetectionError("Failed to load fastText language model") from exc
        return self._model

    @staticmethod
    def _normalize_prediction(labels: object, probabilities: object) -> LanguageDetection:
        if isinstance(labels, (str, bytes)):
            raise LanguageDetectionError("fastText returned no language label")
        if isinstance(probabilities, (str, bytes)):
            raise LanguageDetectionError("fastText returned no confidence score")
        try:
            raw_label = labels[0]  # type: ignore[index]
        except (IndexError, KeyError, TypeError) as exc:
            raise LanguageDetectionError("fastText returned no language label") from exc
        if not isinstance(raw_label, str):
            raise LanguageDetectionError("fastText returned an invalid language label")
        language = raw_label.removeprefix("__label__").strip().lower().split("-", 1)[0]
        if len(language) not in {2, 3} or not language.isalpha():
            raise LanguageDetectionError("fastText returned an invalid language code")
        try:
            confidence = float(probabilities[0])  # type: ignore[index]
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise LanguageDetectionError("fastText returned an invalid confidence score") from exc
        if not 0.0 <= confidence <= 1.0:
            raise LanguageDetectionError("fastText returned an invalid confidence score")
        return LanguageDetection(language=language, confidence=confidence)

    def _predict(self, text: str) -> LanguageDetection:
        model = self._load_model()
        try:
            labels, probabilities = model.predict(text.replace("\n", " "), k=1)
        except Exception as exc:
            raise LanguageDetectionError("fastText language detection failed") from exc
        return self._normalize_prediction(labels, probabilities)

    async def detect(self, text: str) -> LanguageDetection:
        normalized = text.strip()
        if not normalized:
            raise LanguageDetectionError("Language detection text is required")
        return await asyncio.to_thread(self._predict, normalized)
