"""
Unit tests for knowledge recommendation service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.configs.settings import settings
from app.schemas.knowledge import KnowledgeDocumentResponse
from app.services.knowledge_recommendation_service import KnowledgeRecommendationService, _ConversationSource


class TestKnowledgeRecommendationService:
    @pytest.mark.asyncio
    async def test_list_recommendations_without_conversation_returns_no_conversation(self) -> None:
        response = await KnowledgeRecommendationService.list_recommendations(
            AsyncMock(),
            1,
            conversation_id=None,
        )

        assert response.status == "no_conversation"
        assert response.items == []

    @pytest.mark.asyncio
    async def test_list_recommendations_without_visitor_text_returns_no_vector(self) -> None:
        db = AsyncMock()
        conversation = SimpleNamespace(id=10, tenant_id=1)

        with (
            patch(
                "app.services.knowledge_recommendation_service.ConversationRepository.get_by_id",
                new=AsyncMock(return_value=conversation),
            ),
            patch.object(KnowledgeRecommendationService, "schedule_document_embedding_backfill"),
            patch.object(KnowledgeRecommendationService, "_conversation_source", new=AsyncMock(return_value=None)),
            patch(
                "app.services.knowledge_recommendation_service.KnowledgeRecommendationRepository.upsert_conversation_embedding_state",
                new=AsyncMock(),
            ) as upsert_state,
        ):
            response = await KnowledgeRecommendationService.list_recommendations(
                db,
                1,
                conversation_id=10,
            )

        assert response.status == "no_vector"
        upsert_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_recommendations_with_ready_vector_returns_items(self) -> None:
        db = AsyncMock()
        now = datetime.now(timezone.utc)
        conversation = SimpleNamespace(id=10, tenant_id=1)
        state = SimpleNamespace(
            source_hash="abc",
            embedding_version=settings.knowledge_embedding_version,
            embedding_status="ready",
            embedding=[0.1] * settings.KNOWLEDGE_EMBEDDING_DIMENSION,
            embedded_at=now,
        )
        document = SimpleNamespace(id=1)
        response_item = KnowledgeDocumentResponse(
            id=1,
            tenant_id=1,
            directory_id=1,
            directory_path=[],
            title="退款说明",
            content_html="<p>退款</p>",
            status="published",
            display_status="published",
            validity_type="permanent",
            created_at=now,
            updated_at=now,
        )

        with (
            patch(
                "app.services.knowledge_recommendation_service.ConversationRepository.get_by_id",
                new=AsyncMock(return_value=conversation),
            ),
            patch.object(KnowledgeRecommendationService, "schedule_document_embedding_backfill"),
            patch.object(
                KnowledgeRecommendationService,
                "_conversation_source",
                new=AsyncMock(return_value=_ConversationSource(text="退款怎么处理", source_hash="abc", source_message_id=99)),
            ),
            patch(
                "app.services.knowledge_recommendation_service.KnowledgeRecommendationRepository.get_conversation_embedding",
                new=AsyncMock(return_value=state),
            ),
            patch(
                "app.services.knowledge_recommendation_service.KnowledgeRecommendationRepository.recommend_documents",
                new=AsyncMock(return_value=[(document, 0.2)]),
            ) as recommend_documents,
            patch(
                "app.services.knowledge_recommendation_service.KnowledgeDirectoryRepository.list_all",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(KnowledgeRecommendationService, "_document_response", return_value=response_item),
        ):
            response = await KnowledgeRecommendationService.list_recommendations(
                db,
                1,
                conversation_id=10,
            )

        assert response.status == "ready"
        assert len(response.items) == 1
        assert response.items[0].id == 1
        recommend_documents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_recommendations_failed_vector_waits_for_explicit_retry(self) -> None:
        db = AsyncMock()
        now = datetime.now(timezone.utc)
        conversation = SimpleNamespace(id=10, tenant_id=1)
        state = SimpleNamespace(
            source_hash="abc",
            embedding_version=settings.knowledge_embedding_version,
            embedding_status="failed",
            embedding=None,
            embedded_at=now,
            embedding_error="old embedding error",
        )

        with (
            patch(
                "app.services.knowledge_recommendation_service.ConversationRepository.get_by_id",
                new=AsyncMock(return_value=conversation),
            ),
            patch.object(KnowledgeRecommendationService, "schedule_document_embedding_backfill"),
            patch.object(KnowledgeRecommendationService, "schedule_conversation_embedding_refresh") as schedule_refresh,
            patch.object(
                KnowledgeRecommendationService,
                "_conversation_source",
                new=AsyncMock(return_value=_ConversationSource(text="退款怎么处理", source_hash="abc", source_message_id=99)),
            ),
            patch(
                "app.services.knowledge_recommendation_service.KnowledgeRecommendationRepository.get_conversation_embedding",
                new=AsyncMock(return_value=state),
            ),
        ):
            response = await KnowledgeRecommendationService.list_recommendations(
                db,
                1,
                conversation_id=10,
            )

        assert response.status == "failed"
        assert response.message == "old embedding error"
        schedule_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_recommendations_retry_failed_vector_schedules_refresh(self) -> None:
        db = AsyncMock()
        now = datetime.now(timezone.utc)
        conversation = SimpleNamespace(id=10, tenant_id=1)
        state = SimpleNamespace(
            source_hash="abc",
            embedding_version=settings.knowledge_embedding_version,
            embedding_status="failed",
            embedding=None,
            embedded_at=now,
            embedding_error="old embedding error",
        )

        with (
            patch(
                "app.services.knowledge_recommendation_service.ConversationRepository.get_by_id",
                new=AsyncMock(return_value=conversation),
            ),
            patch.object(KnowledgeRecommendationService, "schedule_document_embedding_backfill"),
            patch.object(KnowledgeRecommendationService, "schedule_conversation_embedding_refresh") as schedule_refresh,
            patch.object(
                KnowledgeRecommendationService,
                "_conversation_source",
                new=AsyncMock(return_value=_ConversationSource(text="退款怎么处理", source_hash="abc", source_message_id=99)),
            ),
            patch(
                "app.services.knowledge_recommendation_service.KnowledgeRecommendationRepository.get_conversation_embedding",
                new=AsyncMock(return_value=state),
            ),
        ):
            response = await KnowledgeRecommendationService.list_recommendations(
                db,
                1,
                conversation_id=10,
                retry_failed=True,
            )

        assert response.status == "updating"
        assert response.message is None
        schedule_refresh.assert_called_once_with(1, 10)
