"""Unit tests for outbound prescreen configuration and matching."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.configs.settings import settings
from app.core.exceptions import ValidationError
from app.libs.embedding.base import BaseEmbeddingClient
from app.schemas.outbound_prescreen import (
    OutboundPrescreenConfigDraft,
    OutboundPrescreenIntentDraft,
    OutboundPrescreenTestRequest,
)
from app.services.outbound_prescreen_service import OutboundPrescreenService


def _vector(axis: int = 0) -> list[float]:
    values = [0.0] * settings.KNOWLEDGE_EMBEDDING_DIMENSION
    values[axis] = 1.0
    return values


def _draft(*, enabled: bool = True) -> OutboundPrescreenConfigDraft:
    return OutboundPrescreenConfigDraft(
        intents=[
            OutboundPrescreenIntentDraft(
                intent_key="explicit_rejection",
                name="明确拒绝",
                enabled=enabled,
                similarity_threshold=0.86,
                is_system=True,
                positive_examples=["不需要", "没兴趣", "不考虑", "不用了谢谢", "暂时不需要"],
                negative_examples=["不是不需要，我是现在没空"],
            )
        ]
    )


class _ConstantEmbeddingClient(BaseEmbeddingClient):
    def __init__(self, value: list[float] | None = None) -> None:
        self.value = value or _vector()

    async def embed_texts(self, texts) -> list[list[float]]:
        return [list(self.value) for _ in texts]


class _SemanticEmbeddingClient(BaseEmbeddingClient):
    async def embed_texts(self, texts) -> list[list[float]]:
        return [_vector(1 if "不是" in text else 0) for text in texts]


class _LimitedBatchEmbeddingClient(BaseEmbeddingClient):
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    async def embed_texts(self, texts) -> list[list[float]]:
        assert len(texts) <= 10
        self.batch_sizes.append(len(texts))
        return [_vector() for _ in texts]


class TestOutboundPrescreenService:
    def test_normalize_text_trims_spaces_and_trailing_punctuation(self) -> None:
        assert OutboundPrescreenService.normalize_text("  不需要！！ ") == "不需要"

    def test_enabled_intent_with_too_few_examples_is_rejected(self) -> None:
        draft = _draft()
        draft.intents[0].positive_examples = ["不需要"]

        with pytest.raises(ValidationError, match="至少需要 5 条"):
            OutboundPrescreenService._normalize_and_validate_draft(draft, require_enabled=True)

    def test_duplicate_normalized_names_are_rejected(self) -> None:
        first = _draft().intents[0]
        second = first.model_copy(update={"intent_key": "other", "name": "明确拒绝！"})

        with pytest.raises(ValidationError, match="同名"):
            OutboundPrescreenService._normalize_and_validate_draft(
                OutboundPrescreenConfigDraft(intents=[first, second]),
                require_enabled=True,
            )

    def test_select_decision_returns_match_above_threshold(self) -> None:
        result = OutboundPrescreenService.select_decision(
            [
                {
                    "intent_key": "reject",
                    "intent_name": "明确拒绝",
                    "threshold": 0.86,
                    "matched_positive": "不需要",
                    "positive_similarity": 0.93,
                    "matched_negative": None,
                    "negative_similarity": None,
                }
            ]
        )

        assert result.auto_hangup is True
        assert result.intent_key == "reject"
        assert result.result == "matched"

    def test_select_decision_negative_example_vetoes_match(self) -> None:
        result = OutboundPrescreenService.select_decision(
            [
                {
                    "intent_key": "reject",
                    "intent_name": "明确拒绝",
                    "threshold": 0.86,
                    "matched_positive": "不需要",
                    "positive_similarity": 0.92,
                    "matched_negative": "不是不需要，我是现在没空",
                    "negative_similarity": 0.90,
                }
            ]
        )

        assert result.auto_hangup is False
        assert result.reason == "negative_example_veto"

    def test_select_decision_ambiguous_intents_are_uncertain(self) -> None:
        candidates = [
            {
                "intent_key": key,
                "intent_name": key,
                "threshold": 0.86,
                "matched_positive": key,
                "positive_similarity": score,
                "matched_negative": None,
                "negative_similarity": None,
            }
            for key, score in (("first", 0.91), ("second", 0.89))
        ]

        result = OutboundPrescreenService.select_decision(candidates)

        assert result.auto_hangup is False
        assert result.reason == "ambiguous_intents"

    @pytest.mark.asyncio
    async def test_test_draft_weak_voice_is_conservatively_rejected(self) -> None:
        result = await OutboundPrescreenService.test_draft(
            OutboundPrescreenTestRequest(
                config=_draft(),
                text="不需要",
                voiced_ms=120,
                voice_match=True,
            ),
            embedding_client=_ConstantEmbeddingClient(),
        )

        assert result.auto_hangup is False
        assert result.reason == "insufficient_voiced_ms"

    @pytest.mark.asyncio
    async def test_test_draft_exact_semantic_match_returns_auto_hangup(self) -> None:
        result = await OutboundPrescreenService.test_draft(
            OutboundPrescreenTestRequest(
                config=_draft(),
                text="不需要",
                voiced_ms=800,
                voice_match=True,
            ),
            embedding_client=_SemanticEmbeddingClient(),
        )

        assert result.auto_hangup is True
        assert result.intent_key == "explicit_rejection"

    @pytest.mark.asyncio
    async def test_embedding_requests_are_split_at_provider_batch_limit(self) -> None:
        client = _LimitedBatchEmbeddingClient()

        vectors = await OutboundPrescreenService._embed(
            client,
            [f"测试表达{index}" for index in range(15)],
            timeout_seconds=15.0,
        )

        assert client.batch_sizes == [10, 5]
        assert len(vectors) == 15

    @pytest.mark.asyncio
    async def test_session_snapshot_is_classified_without_database_access(self) -> None:
        snapshot = [
            {
                "intent_key": "explicit_rejection",
                "name": "明确拒绝",
                "similarity_threshold": 0.86,
                "examples": [
                    {"example_type": "positive", "text": "不需要", "embedding": _vector()},
                    {"example_type": "negative", "text": "可以", "embedding": _vector(1)},
                ],
            }
        ]

        with patch(
            "app.services.outbound_prescreen_service.AsyncSessionLocal",
            side_effect=AssertionError("snapshot classification must not query DB"),
        ):
            result = await OutboundPrescreenService.classify_snapshot(
                snapshot,
                "不需要",
                voiced_ms=900,
                voice_match=True,
                embedding_client=_ConstantEmbeddingClient(),
            )

        assert result.auto_hangup is True
        assert result.intent_key == "explicit_rejection"

    @pytest.mark.asyncio
    async def test_snapshot_uses_normalized_configured_phrase_inside_utterance(self) -> None:
        snapshot = [
            {
                "intent_key": "explicit_rejection",
                "name": "明确拒绝",
                "similarity_threshold": 0.86,
                "examples": [
                    {"example_type": "positive", "text": "不需要", "embedding": _vector()},
                ],
            }
        ]

        class FailingEmbeddingClient(BaseEmbeddingClient):
            async def embed_texts(self, texts):
                raise AssertionError("lexical match must precede embedding")

        result = await OutboundPrescreenService.classify_snapshot(
            snapshot,
            "，我不需要。",
            voiced_ms=900,
            voice_match=True,
            embedding_client=FailingEmbeddingClient(),
        )

        assert result.auto_hangup is True
        assert result.intent_key == "explicit_rejection"
        assert result.similarity == 1.0

    @pytest.mark.asyncio
    async def test_save_does_not_hold_db_session_during_embedding(self) -> None:
        state = {"active_sessions": 0}

        class SessionContext:
            async def __aenter__(self):
                state["active_sessions"] += 1
                return SimpleNamespace()

            async def __aexit__(self, exc_type, exc, tb):
                state["active_sessions"] -= 1

        class CheckingEmbeddingClient(BaseEmbeddingClient):
            async def embed_texts(self, texts) -> list[list[float]]:
                assert state["active_sessions"] == 0
                return [_vector() for _ in texts]

        now = datetime.now(timezone.utc)
        intent = SimpleNamespace(
            id=1,
            intent_key="explicit_rejection",
            name="明确拒绝",
            enabled=True,
            similarity_threshold=0.86,
            is_system=True,
            created_at=now,
            updated_at=now,
        )
        example = SimpleNamespace(
            intent_id=1,
            example_type="positive",
            text="不需要",
            embedding_status="ready",
            embedding=_vector(),
        )

        with (
            patch("app.services.outbound_prescreen_service.AsyncSessionLocal", side_effect=lambda: SessionContext()),
            patch(
                "app.services.outbound_prescreen_service.OutboundPrescreenRepository.reusable_embeddings",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.services.outbound_prescreen_service.OutboundPrescreenRepository.replace_config",
                new=AsyncMock(),
            ),
            patch(
                "app.services.outbound_prescreen_service.OutboundPrescreenRepository.list_config",
                new=AsyncMock(return_value=([intent], [example])),
            ),
        ):
            response = await OutboundPrescreenService.save_config_managed(
                1,
                _draft(),
                embedding_client=CheckingEmbeddingClient(),
            )

        assert state["active_sessions"] == 0
        assert response.intents[0].embeddings_ready is True
