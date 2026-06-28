"""
Knowledge recommendation repository.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import MessageContentType, MessageSenderType
from app.models.knowledge import KnowledgeDocument
from app.models.knowledge_recommendation import ConversationUserEmbedding
from app.models.message import Message
from app.repositories.knowledge_repository import KnowledgeDocumentRepository


class KnowledgeRecommendationRepository:
    @staticmethod
    async def get_conversation_embedding(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
    ) -> ConversationUserEmbedding | None:
        result = await db.execute(
            select(ConversationUserEmbedding).where(
                ConversationUserEmbedding.tenant_id == tenant_id,
                ConversationUserEmbedding.conversation_id == conversation_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_visitor_text_messages(
        db: AsyncSession,
        tenant_id: int,
        conversation_id: int,
        *,
        limit: int = 50,
    ) -> list[Message]:
        result = await db.execute(
            select(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation_id,
                Message.sender_type == MessageSenderType.VISITOR.value,
                Message.content_type.in_([MessageContentType.TEXT.value, MessageContentType.RICH_TEXT.value]),
                Message.is_recalled.is_(False),
            )
            .order_by(Message.id.desc())
            .limit(limit)
        )
        items = list(result.scalars().all())
        items.reverse()
        return items

    @staticmethod
    async def upsert_conversation_embedding_state(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        source_message_id: int | None,
        source_hash: str,
        status: str,
        embedding_model: str,
        embedding_version: str,
        embedding_error: str | None = None,
    ) -> None:
        stmt = insert(ConversationUserEmbedding).values(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            source_hash=source_hash,
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            embedding_status=status,
            embedding_error=embedding_error,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_conversation_user_embeddings_tenant_conversation",
            set_={
                "source_message_id": source_message_id,
                "source_hash": source_hash,
                "embedding_model": embedding_model,
                "embedding_version": embedding_version,
                "embedding_status": status,
                "embedding_error": embedding_error,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await db.execute(stmt)
        await db.commit()

    @staticmethod
    async def mark_conversation_embedding_ready(
        db: AsyncSession,
        *,
        tenant_id: int,
        conversation_id: int,
        source_message_id: int | None,
        source_hash: str,
        embedding: list[float],
        embedding_model: str,
        embedding_version: str,
    ) -> None:
        stmt = insert(ConversationUserEmbedding).values(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            source_hash=source_hash,
            embedding=embedding,
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            embedding_status="ready",
            embedding_error=None,
            embedded_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_conversation_user_embeddings_tenant_conversation",
            set_={
                "source_message_id": source_message_id,
                "source_hash": source_hash,
                "embedding": embedding,
                "embedding_model": embedding_model,
                "embedding_version": embedding_version,
                "embedding_status": "ready",
                "embedding_error": None,
                "embedded_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await db.execute(stmt)
        await db.commit()

    @staticmethod
    async def mark_document_embedding_pending(
        db: AsyncSession,
        *,
        tenant_id: int,
        document_id: int,
        embedding_model: str,
        embedding_version: str,
    ) -> None:
        await db.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.id == document_id)
            .values(
                embedding_status="pending",
                embedding_error=None,
                embedding_model=embedding_model,
                embedding_version=embedding_version,
            )
        )
        await db.commit()

    @staticmethod
    async def mark_document_embedding_ready(
        db: AsyncSession,
        *,
        tenant_id: int,
        document_id: int,
        embedding: list[float],
        embedding_model: str,
        embedding_version: str,
    ) -> None:
        await db.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.id == document_id)
            .values(
                embedding=embedding,
                embedding_model=embedding_model,
                embedding_version=embedding_version,
                embedding_status="ready",
                embedding_error=None,
                embedded_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    @staticmethod
    async def mark_document_embedding_failed(
        db: AsyncSession,
        *,
        tenant_id: int,
        document_id: int,
        embedding_model: str,
        embedding_version: str,
        error: str,
    ) -> None:
        await db.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.id == document_id)
            .values(
                embedding_status="failed",
                embedding_error=error[:1000],
                embedding_model=embedding_model,
                embedding_version=embedding_version,
            )
        )
        await db.commit()

    @staticmethod
    async def list_document_ids_needing_embedding(
        db: AsyncSession,
        tenant_id: int,
        *,
        embedding_version: str,
        limit: int,
    ) -> list[int]:
        result = await db.execute(
            select(KnowledgeDocument.id)
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.status == "published",
                # Documents whose embedding never succeeded (failed/pending), is
                # missing, or was built with an outdated model version are all
                # eligible for (re)generation. Previously failed documents are
                # retried so a transient embedding error does not permanently
                # disable recommendations for them.
                (
                    (KnowledgeDocument.embedding_status != "ready")
                    | (KnowledgeDocument.embedding.is_(None))
                    | (KnowledgeDocument.embedding_version != embedding_version)
                ),
            )
            .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
            .limit(limit)
        )
        return [int(item) for item in result.scalars().all()]

    @staticmethod
    async def recommend_documents(
        db: AsyncSession,
        tenant_id: int,
        embedding: list[float],
        *,
        limit: int,
    ) -> list[tuple[KnowledgeDocument, float]]:
        embedding_literal = KnowledgeRecommendationRepository._vector_literal(embedding)
        result = await db.execute(
            text(
                """
                SELECT id, embedding <=> CAST(:embedding AS vector) AS distance
                FROM knowledge_documents
                WHERE tenant_id = :tenant_id
                  AND status = 'published'
                  AND embedding_status = 'ready'
                  AND embedding IS NOT NULL
                  AND (
                    validity_type != 'scheduled'
                    OR (
                      valid_from IS NOT NULL
                      AND valid_to IS NOT NULL
                      AND valid_from <= now()
                      AND valid_to >= now()
                    )
                  )
                ORDER BY embedding <=> CAST(:embedding AS vector), updated_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {"tenant_id": tenant_id, "embedding": embedding_literal, "limit": limit},
        )
        rows = [(int(row.id), float(row.distance)) for row in result]
        documents_by_id = await KnowledgeDocumentRepository.get_by_ids(db, tenant_id, [item[0] for item in rows])
        return [(documents_by_id[document_id], distance) for document_id, distance in rows if document_id in documents_by_id]

    @staticmethod
    def _vector_literal(embedding: list[float]) -> str:
        values: list[str] = []
        for value in embedding:
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("Embedding vector contains non-finite values")
            values.append(f"{number:.8f}")
        return f"[{','.join(values)}]"
