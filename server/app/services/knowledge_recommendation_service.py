"""
Knowledge recommendation service.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import NotFoundError
from app.db.session import AsyncSessionLocal
from app.enums import MessageContentType
from app.libs.embedding import create_embedding_client
from app.models.knowledge import KnowledgeDocument
from app.models.message import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.knowledge_repository import KnowledgeDirectoryRepository, KnowledgeDocumentRepository
from app.repositories.knowledge_recommendation_repository import KnowledgeRecommendationRepository
from app.schemas.knowledge import (
    KnowledgeDocumentResponse,
    KnowledgeRecommendationResponse,
)
from app.services.knowledge_service import KnowledgeService, html_to_plain_text

logger = logging.getLogger(__name__)

CONVERSATION_EMBEDDING_EMPTY = "empty"


@dataclass(frozen=True)
class _ConversationSource:
    text: str
    source_hash: str
    source_message_id: int | None


class KnowledgeRecommendationService:
    @staticmethod
    def schedule_document_embedding_refresh(tenant_id: int, document_id: int) -> None:
        KnowledgeRecommendationService._schedule(
            KnowledgeRecommendationService.refresh_document_embedding_managed(tenant_id, document_id)
        )

    @staticmethod
    def schedule_conversation_embedding_refresh(tenant_id: int, conversation_id: int) -> None:
        KnowledgeRecommendationService._schedule(
            KnowledgeRecommendationService.refresh_conversation_embedding_managed(tenant_id, conversation_id)
        )

    @staticmethod
    def schedule_document_embedding_backfill(tenant_id: int, *, limit: int = 20) -> None:
        KnowledgeRecommendationService._schedule(
            KnowledgeRecommendationService.backfill_document_embeddings_managed(tenant_id, limit=limit)
        )

    @staticmethod
    async def list_recommendations(
        db: AsyncSession,
        tenant_id: int,
        *,
        conversation_id: int | None,
        limit: int | None = None,
        retry_failed: bool = False,
    ) -> KnowledgeRecommendationResponse:
        resolved_limit = max(1, min(limit or settings.KNOWLEDGE_RECOMMENDATION_LIMIT, 20))
        if conversation_id is None:
            return KnowledgeRecommendationService._response("no_conversation", resolved_limit)

        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != tenant_id:
            raise NotFoundError("Conversation not found")

        KnowledgeRecommendationService.schedule_document_embedding_backfill(tenant_id)
        source = await KnowledgeRecommendationService._conversation_source(db, tenant_id, conversation_id)
        if source is None:
            await KnowledgeRecommendationRepository.upsert_conversation_embedding_state(
                db,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                source_message_id=None,
                source_hash="",
                status=CONVERSATION_EMBEDDING_EMPTY,
                embedding_model=settings.KNOWLEDGE_EMBEDDING_MODEL,
                embedding_version=settings.knowledge_embedding_version,
            )
            logger.info(
                "knowledge_recommendation_no_vector tenant_id=%s conversation_id=%s reason=no_visitor_text",
                tenant_id,
                conversation_id,
            )
            return KnowledgeRecommendationService._response("no_vector", resolved_limit)

        state = await KnowledgeRecommendationRepository.get_conversation_embedding(db, tenant_id, conversation_id)
        refresh_needed = (
            state is None
            or state.source_hash != source.source_hash
            or state.embedding_version != settings.knowledge_embedding_version
        )
        retry_failed_needed = (
            retry_failed
            and state is not None
            and state.embedding_status == "failed"
            and not refresh_needed
        )
        if refresh_needed or retry_failed_needed:
            KnowledgeRecommendationService.schedule_conversation_embedding_refresh(tenant_id, conversation_id)

        if state is None or not state.embedding or state.embedding_status != "ready":
            status = (
                "failed"
                if state and state.embedding_status == "failed" and not refresh_needed and not retry_failed_needed
                else "updating"
            )
            logger.info(
                "knowledge_recommendation_vector_not_ready tenant_id=%s conversation_id=%s status=%s "
                "embedding_status=%s refresh_needed=%s retry_failed_needed=%s source_message_id=%s",
                tenant_id,
                conversation_id,
                status,
                state.embedding_status if state else None,
                refresh_needed,
                retry_failed_needed,
                source.source_message_id,
            )
            return KnowledgeRecommendationService._response(
                status,
                resolved_limit,
                vector_updated_at=state.embedded_at if state else None,
                message=state.embedding_error if status == "failed" and state else None,
            )

        try:
            rows = await KnowledgeRecommendationRepository.recommend_documents(
                db,
                tenant_id,
                state.embedding,
                limit=resolved_limit,
            )
        except Exception:
            logger.exception("knowledge_recommendation_query_failed tenant_id=%s conversation_id=%s", tenant_id, conversation_id)
            return KnowledgeRecommendationService._response("failed", resolved_limit)

        directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
        items = [
            KnowledgeRecommendationService._document_response(document, directories)
            for document, _distance in rows
        ]
        logger.info(
            "knowledge_recommendation_ready tenant_id=%s conversation_id=%s status=%s match_count=%s "
            "refresh_needed=%s source_message_id=%s",
            tenant_id,
            conversation_id,
            "updating" if refresh_needed else "ready",
            len(items),
            refresh_needed,
            source.source_message_id,
        )
        return KnowledgeRecommendationResponse(
            status="updating" if refresh_needed else "ready",
            items=items,
            limit=resolved_limit,
            vector_updated_at=state.embedded_at,
            message=None,
        )

    @staticmethod
    async def refresh_document_embedding_managed(tenant_id: int, document_id: int) -> None:
        embedding_model = settings.KNOWLEDGE_EMBEDDING_MODEL
        embedding_version = settings.knowledge_embedding_version
        try:
            async with AsyncSessionLocal() as db:
                document = await KnowledgeDocumentRepository.get_by_id(db, document_id)
                if not document or document.tenant_id != tenant_id:
                    return
                directories = await KnowledgeDirectoryRepository.list_all(db, tenant_id)
                source_text = KnowledgeRecommendationService._document_source(document, directories)
                await KnowledgeRecommendationRepository.mark_document_embedding_pending(
                    db,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    embedding_model=embedding_model,
                    embedding_version=embedding_version,
                )

            embedding = (await create_embedding_client().embed_texts([source_text]))[0]

            async with AsyncSessionLocal() as db:
                await KnowledgeRecommendationRepository.mark_document_embedding_ready(
                    db,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    embedding=embedding,
                    embedding_model=embedding_model,
                    embedding_version=embedding_version,
                )
            logger.info(
                "knowledge_document_embedding_ready tenant_id=%s document_id=%s embedding_version=%s",
                tenant_id,
                document_id,
                embedding_version,
            )
        except Exception as exc:
            logger.warning(
                "knowledge_document_embedding_refresh_failed tenant_id=%s document_id=%s error=%s",
                tenant_id,
                document_id,
                exc,
            )
            async with AsyncSessionLocal() as db:
                await KnowledgeRecommendationRepository.mark_document_embedding_failed(
                    db,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    embedding_model=embedding_model,
                    embedding_version=embedding_version,
                    error=str(exc),
                )

    @staticmethod
    async def refresh_conversation_embedding_managed(tenant_id: int, conversation_id: int) -> None:
        embedding_model = settings.KNOWLEDGE_EMBEDDING_MODEL
        embedding_version = settings.knowledge_embedding_version
        source_for_failure: _ConversationSource | None = None
        try:
            async with AsyncSessionLocal() as db:
                conversation = await ConversationRepository.get_by_id(db, conversation_id)
                if not conversation or conversation.tenant_id != tenant_id:
                    return
                source = await KnowledgeRecommendationService._conversation_source(db, tenant_id, conversation_id)
                if source is None:
                    await KnowledgeRecommendationRepository.upsert_conversation_embedding_state(
                        db,
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        source_message_id=None,
                        source_hash="",
                        status=CONVERSATION_EMBEDDING_EMPTY,
                        embedding_model=embedding_model,
                        embedding_version=embedding_version,
                    )
                    return
                source_for_failure = source
                await KnowledgeRecommendationRepository.upsert_conversation_embedding_state(
                    db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    source_message_id=source.source_message_id,
                    source_hash=source.source_hash,
                    status="pending",
                    embedding_model=embedding_model,
                    embedding_version=embedding_version,
                )

            embedding = (await create_embedding_client().embed_texts([source.text]))[0]

            async with AsyncSessionLocal() as db:
                await KnowledgeRecommendationRepository.mark_conversation_embedding_ready(
                    db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    source_message_id=source.source_message_id,
                    source_hash=source.source_hash,
                    embedding=embedding,
                    embedding_model=embedding_model,
                    embedding_version=embedding_version,
                )
            logger.info(
                "conversation_user_embedding_ready tenant_id=%s conversation_id=%s source_message_id=%s",
                tenant_id,
                conversation_id,
                source.source_message_id,
            )
        except Exception as exc:
            logger.warning(
                "conversation_user_embedding_refresh_failed tenant_id=%s conversation_id=%s error=%s",
                tenant_id,
                conversation_id,
                exc,
            )
            async with AsyncSessionLocal() as db:
                await KnowledgeRecommendationRepository.upsert_conversation_embedding_state(
                    db,
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    source_message_id=source_for_failure.source_message_id if source_for_failure else None,
                    source_hash=source_for_failure.source_hash if source_for_failure else "",
                    status="failed",
                    embedding_model=embedding_model,
                    embedding_version=embedding_version,
                    embedding_error=str(exc),
                )

    @staticmethod
    async def backfill_document_embeddings_managed(tenant_id: int, *, limit: int = 20) -> None:
        async with AsyncSessionLocal() as db:
            document_ids = await KnowledgeRecommendationRepository.list_document_ids_needing_embedding(
                db,
                tenant_id,
                embedding_version=settings.knowledge_embedding_version,
                limit=limit,
            )
        if document_ids:
            logger.info(
                "knowledge_document_embedding_backfill_start tenant_id=%s pending_count=%s",
                tenant_id,
                len(document_ids),
            )
        for document_id in document_ids:
            await KnowledgeRecommendationService.refresh_document_embedding_managed(tenant_id, document_id)

    @staticmethod
    async def _conversation_source(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
    ) -> _ConversationSource | None:
        messages = await KnowledgeRecommendationRepository.list_visitor_text_messages(db, tenant_id, conversation_id)
        parts = [KnowledgeRecommendationService._message_text(message) for message in messages]
        text = "\n".join(part for part in parts if part)
        text = text.strip()
        if not text:
            return None
        if len(text) > settings.KNOWLEDGE_EMBEDDING_TEXT_MAX_CHARS:
            text = text[-settings.KNOWLEDGE_EMBEDDING_TEXT_MAX_CHARS :]
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        source_message_id = messages[-1].id if messages else None
        return _ConversationSource(text=text, source_hash=source_hash, source_message_id=source_message_id)

    @staticmethod
    def _message_text(message: Message) -> str:
        if message.content_type == MessageContentType.RICH_TEXT.value:
            return html_to_plain_text(message.content)
        return (message.content or "").strip()

    @staticmethod
    def _document_source(document: KnowledgeDocument, directories: list) -> str:
        path = " / ".join(item.name for item in KnowledgeService._directory_path(directories, document.directory_id))
        text = "\n".join(part for part in [path, document.title, document.content_plain] if part)
        text = text.strip()
        if len(text) > settings.KNOWLEDGE_EMBEDDING_TEXT_MAX_CHARS:
            return text[: settings.KNOWLEDGE_EMBEDDING_TEXT_MAX_CHARS]
        return text

    @staticmethod
    def _document_response(
        document: KnowledgeDocument,
        directories: list,
    ) -> KnowledgeDocumentResponse:
        return KnowledgeService._document_response(
            document,
            KnowledgeService._directory_path(directories, document.directory_id),
        )

    @staticmethod
    def _response(
        status: str,
        limit: int,
        *,
        vector_updated_at: datetime | None = None,
        message: str | None = None,
    ) -> KnowledgeRecommendationResponse:
        return KnowledgeRecommendationResponse(
            status=status,
            items=[],
            limit=limit,
            vector_updated_at=vector_updated_at,
            message=message,
        )

    @staticmethod
    def _schedule(coro) -> None:
        try:
            asyncio.create_task(coro)
        except RuntimeError:
            coro.close()
            logger.debug("No running event loop; knowledge recommendation task skipped")
