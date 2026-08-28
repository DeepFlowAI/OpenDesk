"""Data access for outbound prescreen intent configuration."""
from __future__ import annotations

import math
from collections.abc import Sequence

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbound_prescreen import OutboundPrescreenIntent, OutboundPrescreenIntentExample


class OutboundPrescreenRepository:
    @staticmethod
    async def list_config(
        db: AsyncSession,
        tenant_id: int,
    ) -> tuple[list[OutboundPrescreenIntent], list[OutboundPrescreenIntentExample]]:
        intents = list(
            (
                await db.execute(
                    select(OutboundPrescreenIntent)
                    .where(OutboundPrescreenIntent.tenant_id == tenant_id)
                    .order_by(OutboundPrescreenIntent.is_system.desc(), OutboundPrescreenIntent.id.asc())
                )
            )
            .scalars()
            .all()
        )
        if not intents:
            return [], []
        examples = list(
            (
                await db.execute(
                    select(OutboundPrescreenIntentExample)
                    .where(
                        OutboundPrescreenIntentExample.tenant_id == tenant_id,
                        OutboundPrescreenIntentExample.intent_id.in_([item.id for item in intents]),
                    )
                    .order_by(OutboundPrescreenIntentExample.id.asc())
                )
            )
            .scalars()
            .all()
        )
        return intents, examples

    @staticmethod
    async def create_defaults(
        db: AsyncSession,
        tenant_id: int,
        defaults: Sequence[dict],
    ) -> None:
        for item in defaults:
            intent = OutboundPrescreenIntent(
                tenant_id=tenant_id,
                intent_key=item["intent_key"],
                name=item["name"],
                enabled=False,
                similarity_threshold=item["similarity_threshold"],
                is_system=True,
            )
            db.add(intent)
            await db.flush()
            for example_text in item["positive_examples"]:
                db.add(
                    OutboundPrescreenIntentExample(
                        tenant_id=tenant_id,
                        intent_id=intent.id,
                        example_type="positive",
                        text=example_text,
                        normalized_text=item["normalize"](example_text),
                        embedding=None,
                        embedding_model=item["embedding_model"],
                        content_hash=item["content_hash"](example_text),
                        embedding_status="pending",
                    )
                )
        await db.commit()

    @staticmethod
    async def reusable_embeddings(db: AsyncSession, tenant_id: int) -> dict[str, list[float]]:
        result = await db.execute(
            select(
                OutboundPrescreenIntentExample.content_hash,
                OutboundPrescreenIntentExample.embedding,
            ).where(
                OutboundPrescreenIntentExample.tenant_id == tenant_id,
                OutboundPrescreenIntentExample.embedding_status == "ready",
                OutboundPrescreenIntentExample.embedding.is_not(None),
            )
        )
        return {str(content_hash): list(embedding) for content_hash, embedding in result if embedding}

    @staticmethod
    async def replace_config(db: AsyncSession, tenant_id: int, intents: Sequence[dict]) -> None:
        await db.execute(
            delete(OutboundPrescreenIntent).where(OutboundPrescreenIntent.tenant_id == tenant_id)
        )
        await db.flush()
        for item in intents:
            intent = OutboundPrescreenIntent(
                tenant_id=tenant_id,
                intent_key=item["intent_key"],
                name=item["name"],
                enabled=item["enabled"],
                similarity_threshold=item["similarity_threshold"],
                is_system=item["is_system"],
            )
            db.add(intent)
            await db.flush()
            for example in item["examples"]:
                db.add(
                    OutboundPrescreenIntentExample(
                        tenant_id=tenant_id,
                        intent_id=intent.id,
                        **example,
                    )
                )
        await db.commit()

    @staticmethod
    async def match_candidates(
        db: AsyncSession,
        tenant_id: int,
        embedding: list[float],
    ) -> list[dict]:
        result = await db.execute(
            text(
                """
                SELECT DISTINCT ON (i.id, e.example_type)
                    i.intent_key,
                    i.name AS intent_name,
                    i.similarity_threshold,
                    e.example_type,
                    e.text AS example_text,
                    1 - (e.embedding <=> CAST(:embedding AS vector)) AS similarity
                FROM outbound_prescreen_intents AS i
                JOIN outbound_prescreen_intent_examples AS e ON e.intent_id = i.id
                WHERE i.tenant_id = :tenant_id
                  AND i.enabled = true
                  AND e.embedding_status = 'ready'
                  AND e.embedding IS NOT NULL
                ORDER BY i.id, e.example_type, e.embedding <=> CAST(:embedding AS vector), e.id
                """
            ),
            {
                "tenant_id": tenant_id,
                "embedding": OutboundPrescreenRepository._vector_literal(embedding),
            },
        )
        return [dict(row._mapping) for row in result]

    @staticmethod
    def _vector_literal(embedding: list[float]) -> str:
        values: list[str] = []
        for value in embedding:
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("Embedding vector contains non-finite values")
            values.append(f"{number:.8f}")
        return f"[{','.join(values)}]"
