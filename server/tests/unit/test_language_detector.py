"""Unit tests for the fastText language detector adapter."""
from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pytest

from app.libs.langdetect.base import LanguageDetection, LanguageDetectionError
from app.libs.langdetect.factory import create_language_detector
from app.libs.langdetect.providers.fasttext import FastTextLanguageDetector


class TestFastTextLanguageDetector:
    def test_factory_returns_fasttext_detector(self) -> None:
        assert isinstance(create_language_detector("fasttext"), FastTextLanguageDetector)

    def test_factory_reuses_detector_instance(self) -> None:
        assert create_language_detector("fasttext") is create_language_detector("fasttext")

    def test_factory_rejects_unknown_provider(self) -> None:
        with pytest.raises(ValueError, match="Unsupported language detector"):
            create_language_detector("unknown")

    def test_normalize_prediction_returns_iso_language(self) -> None:
        result = FastTextLanguageDetector._normalize_prediction(
            ("__label__JA",),
            np.asarray([0.875]),
        )
        assert result == LanguageDetection(language="ja", confidence=0.875)

    def test_normalize_prediction_rejects_bad_score(self) -> None:
        with pytest.raises(LanguageDetectionError, match="confidence"):
            FastTextLanguageDetector._normalize_prediction(("__label__en",), (1.5,))

    @pytest.mark.asyncio
    async def test_detect_uses_loaded_model(self) -> None:
        detector = FastTextLanguageDetector(model_path="unused.bin")
        detector._model = Mock(predict=Mock(return_value=(("__label__zh",), (0.91,))))

        result = await detector.detect("你好")

        assert result == LanguageDetection(language="zh", confidence=0.91)
        detector._model.predict.assert_called_once_with("你好", k=1)

    @pytest.mark.asyncio
    async def test_detect_rejects_empty_text(self) -> None:
        with pytest.raises(LanguageDetectionError, match="text is required"):
            await FastTextLanguageDetector(model_path="unused.bin").detect("  ")

    @pytest.mark.asyncio
    async def test_detect_reports_missing_model_file(self, tmp_path) -> None:
        detector = FastTextLanguageDetector(model_path=str(tmp_path / "missing.bin"))

        with pytest.raises(LanguageDetectionError, match="does not exist"):
            await detector.detect("hello world")
