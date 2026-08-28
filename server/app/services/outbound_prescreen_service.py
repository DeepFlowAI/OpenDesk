"""Outbound prescreen configuration and conservative semantic matching."""
from __future__ import annotations

import asyncio
import hashlib
import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.configs.settings import settings
from app.core.exceptions import ValidationError
from app.db.session import AsyncSessionLocal
from app.libs.embedding import create_embedding_client
from app.libs.embedding.base import BaseEmbeddingClient
from app.repositories.outbound_prescreen_repository import OutboundPrescreenRepository
from app.schemas.outbound_prescreen import (
    OutboundPrescreenConfigDraft,
    OutboundPrescreenConfigResponse,
    OutboundPrescreenDecision,
    OutboundPrescreenIntentResponse,
    OutboundPrescreenTestRequest,
)

MAX_INTENTS = 20
MAX_EXAMPLES_PER_TYPE = 200
MIN_ENABLED_POSITIVES = 5
EMBEDDING_BATCH_SIZE = 10
SAVE_EMBEDDING_TIMEOUT_SECONDS = 15.0
RUNTIME_EMBEDDING_TIMEOUT_SECONDS = 2.0
NEGATIVE_SAFETY_MARGIN = 0.03
AMBIGUITY_MARGIN = 0.03
MIN_COMMAND_VOICED_MS = 500

_TRAILING_PUNCTUATION = re.compile(r"[\s。！？，；：.!?,;:]+$")
_FILLERS = frozenset({"嗯", "啊", "喂", "哦", "奥", "呃", "诶", "hello", "hi"})


@dataclass(frozen=True)
class _PreparedExample:
    example_type: str
    text: str
    normalized_text: str
    content_hash: str
    embedding: list[float] | None


DEFAULT_INTENTS: tuple[dict, ...] = (
    {
        "intent_key": "explicit_rejection",
        "name": "明确拒绝",
        "similarity_threshold": Decimal("0.860"),
        "positive_examples": ["不需要", "没兴趣", "不用了谢谢", "我不考虑", "暂时不需要"],
    },
    {
        "intent_key": "not_convenient",
        "name": "暂不方便",
        "similarity_threshold": Decimal("0.860"),
        "positive_examples": ["现在很忙", "晚点再说", "现在不方便", "一会再联系", "我正在开会"],
    },
    {
        "intent_key": "do_not_contact",
        "name": "禁止再次联系",
        "similarity_threshold": Decimal("0.860"),
        "positive_examples": ["不要再打了", "别联系我", "把我删掉", "以后别打电话", "不要再骚扰我"],
    },
)


class OutboundPrescreenService:
    @staticmethod
    def normalize_text(value: str) -> str:
        return _TRAILING_PUNCTUATION.sub("", value.strip()).strip().lower()

    @staticmethod
    def content_hash(value: str) -> str:
        normalized = OutboundPrescreenService.normalize_text(value)
        source = f"{settings.KNOWLEDGE_EMBEDDING_MODEL}:{normalized}"
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @staticmethod
    async def get_config_managed(tenant_id: int) -> OutboundPrescreenConfigResponse:
        async with AsyncSessionLocal() as db:
            intents, examples = await OutboundPrescreenRepository.list_config(db, tenant_id)
            if not intents:
                await OutboundPrescreenRepository.create_defaults(
                    db,
                    tenant_id,
                    [
                        {
                            **item,
                            "normalize": OutboundPrescreenService.normalize_text,
                            "content_hash": OutboundPrescreenService.content_hash,
                            "embedding_model": settings.KNOWLEDGE_EMBEDDING_MODEL,
                        }
                        for item in DEFAULT_INTENTS
                    ],
                )
                intents, examples = await OutboundPrescreenRepository.list_config(db, tenant_id)
        return OutboundPrescreenService._config_response(intents, examples)

    @staticmethod
    async def save_config_managed(
        tenant_id: int,
        draft: OutboundPrescreenConfigDraft,
        *,
        embedding_client: BaseEmbeddingClient | None = None,
    ) -> OutboundPrescreenConfigResponse:
        normalized = OutboundPrescreenService._normalize_and_validate_draft(draft, require_enabled=True)

        async with AsyncSessionLocal() as db:
            reusable = await OutboundPrescreenRepository.reusable_embeddings(db, tenant_id)

        prepared = OutboundPrescreenService._prepared_config(normalized, reusable)
        missing = [example for item in prepared for example in item["examples"] if example.embedding is None]
        if missing:
            client = embedding_client or create_embedding_client()
            vectors = await OutboundPrescreenService._embed(
                client,
                [example.normalized_text for example in missing],
                timeout_seconds=SAVE_EMBEDDING_TIMEOUT_SECONDS,
            )
            vector_by_hash = {example.content_hash: vector for example, vector in zip(missing, vectors, strict=True)}
        else:
            vector_by_hash = {}

        rows: list[dict] = []
        for item in prepared:
            rows.append(
                {
                    **{key: item[key] for key in ("intent_key", "name", "enabled", "similarity_threshold", "is_system")},
                    "examples": [
                        {
                            "example_type": example.example_type,
                            "text": example.text,
                            "normalized_text": example.normalized_text,
                            "embedding": example.embedding or vector_by_hash[example.content_hash],
                            "embedding_model": settings.KNOWLEDGE_EMBEDDING_MODEL,
                            "content_hash": example.content_hash,
                            "embedding_status": "ready",
                        }
                        for example in item["examples"]
                    ],
                }
            )

        async with AsyncSessionLocal() as db:
            await OutboundPrescreenRepository.replace_config(db, tenant_id, rows)
            intents, examples = await OutboundPrescreenRepository.list_config(db, tenant_id)
        return OutboundPrescreenService._config_response(intents, examples)

    @staticmethod
    async def test_draft(
        request: OutboundPrescreenTestRequest,
        *,
        embedding_client: BaseEmbeddingClient | None = None,
    ) -> OutboundPrescreenDecision:
        eligibility = OutboundPrescreenService._eligibility_failure(
            request.text,
            voiced_ms=request.voiced_ms,
            voice_match=request.voice_match,
        )
        if eligibility:
            return eligibility
        normalized = OutboundPrescreenService._normalize_and_validate_draft(
            request.config, require_enabled=False
        )
        enabled = [item for item in normalized if item["enabled"]]
        if not enabled:
            return OutboundPrescreenDecision(result="uncertain", auto_hangup=False, reason="no_enabled_intent")
        texts = [OutboundPrescreenService.normalize_text(request.text)]
        refs: list[tuple[str, str, str]] = []
        for item in enabled:
            for example_type in ("positive", "negative"):
                for example in item[f"{example_type}_examples"]:
                    refs.append((item["intent_key"], example_type, example))
                    texts.append(example)
        vectors = await OutboundPrescreenService._embed(
            embedding_client or create_embedding_client(),
            texts,
            timeout_seconds=SAVE_EMBEDDING_TIMEOUT_SECONDS,
        )
        query = vectors[0]
        best: dict[tuple[str, str], tuple[str, float]] = {}
        for ref, vector in zip(refs, vectors[1:], strict=True):
            key = (ref[0], ref[1])
            score = OutboundPrescreenService._cosine_similarity(query, vector)
            if key not in best or score > best[key][1]:
                best[key] = (ref[2], score)
        candidates = OutboundPrescreenService._draft_candidates(enabled, best)
        return OutboundPrescreenService.select_decision(candidates)

    @staticmethod
    async def classify_managed(
        tenant_id: int,
        text_value: str,
        *,
        voiced_ms: int | None,
        voice_match: bool | None,
        embedding_client: BaseEmbeddingClient | None = None,
    ) -> OutboundPrescreenDecision:
        eligibility = OutboundPrescreenService._eligibility_failure(
            text_value, voiced_ms=voiced_ms, voice_match=voice_match
        )
        if eligibility:
            return eligibility
        try:
            vector = (
                await OutboundPrescreenService._embed(
                    embedding_client or create_embedding_client(),
                    [OutboundPrescreenService.normalize_text(text_value)],
                    timeout_seconds=RUNTIME_EMBEDDING_TIMEOUT_SECONDS,
                )
            )[0]
            async with AsyncSessionLocal() as db:
                rows = await OutboundPrescreenRepository.match_candidates(db, tenant_id, vector)
            return OutboundPrescreenService.select_decision(
                OutboundPrescreenService._repository_candidates(rows)
            )
        except Exception:  # noqa: BLE001
            return OutboundPrescreenDecision(
                result="uncertain", auto_hangup=False, reason="classification_unavailable"
            )

    @staticmethod
    async def classify_snapshot(
        snapshot: Sequence[dict],
        text_value: str,
        *,
        voiced_ms: int | None,
        voice_match: bool | None,
        embedding_client: BaseEmbeddingClient | None = None,
    ) -> OutboundPrescreenDecision:
        """Classify against the immutable session snapshot without a DB session."""
        eligibility = OutboundPrescreenService._eligibility_failure(
            text_value, voiced_ms=voiced_ms, voice_match=voice_match
        )
        if eligibility:
            return eligibility
        lexical = OutboundPrescreenService._lexical_candidates(snapshot, text_value)
        if lexical:
            return OutboundPrescreenService.select_decision(lexical)
        try:
            query = (
                await OutboundPrescreenService._embed(
                    embedding_client or create_embedding_client(),
                    [OutboundPrescreenService.normalize_text(text_value)],
                    timeout_seconds=RUNTIME_EMBEDDING_TIMEOUT_SECONDS,
                )
            )[0]
            candidates: list[dict] = []
            for intent in snapshot:
                best: dict[str, tuple[str, float]] = {}
                for example in intent.get("examples", []):
                    vector = example.get("embedding")
                    if not vector:
                        continue
                    score = OutboundPrescreenService._cosine_similarity(query, vector)
                    example_type = str(example.get("example_type"))
                    if example_type not in best or score > best[example_type][1]:
                        best[example_type] = (str(example.get("text") or ""), score)
                positive = best.get("positive")
                if positive is None:
                    continue
                negative = best.get("negative")
                candidates.append(
                    {
                        "intent_key": intent.get("intent_key"),
                        "intent_name": intent.get("name"),
                        "threshold": float(intent.get("similarity_threshold", 1.0)),
                        "matched_positive": positive[0],
                        "positive_similarity": positive[1],
                        "matched_negative": negative[0] if negative else None,
                        "negative_similarity": negative[1] if negative else None,
                    }
                )
            return OutboundPrescreenService.select_decision(candidates)
        except Exception:  # noqa: BLE001
            return OutboundPrescreenDecision(
                result="uncertain", auto_hangup=False, reason="classification_unavailable"
            )

    @staticmethod
    def select_decision(candidates: Sequence[dict]) -> OutboundPrescreenDecision:
        ranked = sorted(candidates, key=lambda item: item.get("positive_similarity") or -1.0, reverse=True)
        if not ranked:
            return OutboundPrescreenDecision(result="uncertain", auto_hangup=False, reason="no_enabled_intent")
        top = ranked[0]
        positive = float(top.get("positive_similarity") or 0.0)
        threshold = float(top["threshold"])
        if positive < threshold:
            return OutboundPrescreenService._decision_from(top, False, "below_threshold")
        negative = top.get("negative_similarity")
        if negative is not None and float(negative) >= positive - NEGATIVE_SAFETY_MARGIN:
            return OutboundPrescreenService._decision_from(top, False, "negative_example_veto")
        if len(ranked) > 1:
            runner_up = float(ranked[1].get("positive_similarity") or 0.0)
            if positive - runner_up < AMBIGUITY_MARGIN:
                return OutboundPrescreenService._decision_from(top, False, "ambiguous_intents")
        return OutboundPrescreenService._decision_from(top, True, None)

    @staticmethod
    def _normalize_and_validate_draft(
        draft: OutboundPrescreenConfigDraft,
        *,
        require_enabled: bool,
    ) -> list[dict]:
        if len(draft.intents) > MAX_INTENTS:
            raise ValidationError("最多可创建 20 个预筛意图")
        names: set[str] = set()
        keys: set[str] = set()
        normalized: list[dict] = []
        for raw in draft.intents:
            name_key = OutboundPrescreenService.normalize_text(raw.name)
            if name_key in names:
                raise ValidationError("已存在同名预筛意图，请更换名称")
            names.add(name_key)
            intent_key = raw.intent_key or f"custom_{uuid.uuid4().hex}"
            if intent_key in keys:
                raise ValidationError("预筛意图标识重复")
            keys.add(intent_key)
            positives = OutboundPrescreenService._normalize_examples(raw.positive_examples)
            negatives = OutboundPrescreenService._normalize_examples(raw.negative_examples)
            if raw.enabled and len(positives) < MIN_ENABLED_POSITIVES:
                raise ValidationError("启用的预筛意图至少需要 5 条相似表达")
            normalized.append(
                {
                    "intent_key": intent_key,
                    "name": raw.name.strip(),
                    "enabled": raw.enabled,
                    "similarity_threshold": Decimal(str(raw.similarity_threshold)),
                    "is_system": raw.is_system,
                    "positive_examples": positives,
                    "negative_examples": negatives,
                }
            )
        if require_enabled and not any(item["enabled"] for item in normalized):
            raise ValidationError("至少保留一个启用的预筛意图")
        return normalized

    @staticmethod
    def _normalize_examples(values: Sequence[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = OutboundPrescreenService.normalize_text(value)
            if not normalized or normalized in seen:
                continue
            if not 2 <= len(normalized) <= 50:
                raise ValidationError("每条预筛表达需为 2–50 个字符")
            seen.add(normalized)
            result.append(normalized)
        if len(result) > MAX_EXAMPLES_PER_TYPE:
            raise ValidationError("每个意图的相似表达或反例最多 200 条")
        return result

    @staticmethod
    def _prepared_config(items: Sequence[dict], reusable: dict[str, list[float]]) -> list[dict]:
        result: list[dict] = []
        for item in items:
            examples: list[_PreparedExample] = []
            for example_type in ("positive", "negative"):
                for text_value in item[f"{example_type}_examples"]:
                    content_hash = OutboundPrescreenService.content_hash(text_value)
                    examples.append(
                        _PreparedExample(
                            example_type=example_type,
                            text=text_value,
                            normalized_text=text_value,
                            content_hash=content_hash,
                            embedding=reusable.get(content_hash),
                        )
                    )
            result.append({**item, "examples": examples})
        return result

    @staticmethod
    async def _embed(
        client: BaseEmbeddingClient,
        texts: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> list[list[float]]:
        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = list(texts[start : start + EMBEDDING_BATCH_SIZE])
            vectors = await asyncio.wait_for(client.embed_texts(batch), timeout=timeout_seconds)
            if len(vectors) != len(batch):
                raise ValidationError("Embedding 服务返回的向量数量不正确")
            for vector in vectors:
                if len(vector) != settings.KNOWLEDGE_EMBEDDING_DIMENSION:
                    raise ValidationError("Embedding 服务返回的向量维度不正确")
                if not all(math.isfinite(float(value)) for value in vector):
                    raise ValidationError("Embedding 服务返回了无效向量")
                all_vectors.append([float(value) for value in vector])
        return all_vectors

    @staticmethod
    def _eligibility_failure(
        text_value: str,
        *,
        voiced_ms: int | None,
        voice_match: bool | None,
    ) -> OutboundPrescreenDecision | None:
        normalized = OutboundPrescreenService.normalize_text(text_value)
        if not normalized or normalized in _FILLERS:
            return OutboundPrescreenDecision(result="uncertain", auto_hangup=False, reason="insufficient_text")
        if voice_match is False:
            return OutboundPrescreenDecision(result="uncertain", auto_hangup=False, reason="voice_mismatch")
        if voiced_ms is not None and voiced_ms < MIN_COMMAND_VOICED_MS:
            return OutboundPrescreenDecision(result="uncertain", auto_hangup=False, reason="insufficient_voiced_ms")
        return None

    @staticmethod
    def _draft_candidates(enabled: Sequence[dict], best: dict[tuple[str, str], tuple[str, float]]) -> list[dict]:
        return [
            {
                "intent_key": item["intent_key"],
                "intent_name": item["name"],
                "threshold": float(item["similarity_threshold"]),
                "matched_positive": best.get((item["intent_key"], "positive"), (None, None))[0],
                "positive_similarity": best.get((item["intent_key"], "positive"), (None, None))[1],
                "matched_negative": best.get((item["intent_key"], "negative"), (None, None))[0],
                "negative_similarity": best.get((item["intent_key"], "negative"), (None, None))[1],
            }
            for item in enabled
        ]

    @staticmethod
    def _repository_candidates(rows: Sequence[dict]) -> list[dict]:
        grouped: dict[str, dict] = {}
        for row in rows:
            item = grouped.setdefault(
                str(row["intent_key"]),
                {
                    "intent_key": str(row["intent_key"]),
                    "intent_name": str(row["intent_name"]),
                    "threshold": float(row["similarity_threshold"]),
                    "matched_positive": None,
                    "positive_similarity": None,
                    "matched_negative": None,
                    "negative_similarity": None,
                },
            )
            prefix = "positive" if row["example_type"] == "positive" else "negative"
            item[f"matched_{prefix}"] = str(row["example_text"])
            item[f"{prefix}_similarity"] = float(row["similarity"])
        return list(grouped.values())

    @staticmethod
    def _lexical_candidates(snapshot: Sequence[dict], text_value: str) -> list[dict]:
        """Return configured positive examples contained in normalized speech.

        This deterministic layer complements semantic matching for short command
        phrases and is shared by every snapshot consumer. Punctuation and case
        are handled by the same normalization used when examples are stored.
        """
        normalized = OutboundPrescreenService.normalize_text(text_value)
        candidates: list[dict] = []
        for intent in snapshot:
            for example in intent.get("examples", []):
                if example.get("example_type") != "positive":
                    continue
                example_text = OutboundPrescreenService.normalize_text(
                    str(example.get("text") or "")
                )
                if not example_text or example_text not in normalized:
                    continue
                candidates.append(
                    {
                        "intent_key": intent.get("intent_key"),
                        "intent_name": intent.get("name"),
                        "threshold": float(intent.get("similarity_threshold", 1.0)),
                        "matched_positive": example_text,
                        "positive_similarity": 1.0,
                        "matched_negative": None,
                        "negative_similarity": None,
                    }
                )
                break
        return candidates

    @staticmethod
    def _decision_from(item: dict, auto_hangup: bool, reason: str | None) -> OutboundPrescreenDecision:
        return OutboundPrescreenDecision(
            result="matched" if auto_hangup else "uncertain",
            auto_hangup=auto_hangup,
            intent_key=item.get("intent_key"),
            intent_name=item.get("intent_name"),
            similarity=item.get("positive_similarity"),
            threshold=item.get("threshold"),
            matched_positive=item.get("matched_positive"),
            matched_negative=item.get("matched_negative"),
            negative_similarity=item.get("negative_similarity"),
            reason=reason,
        )

    @staticmethod
    def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)

    @staticmethod
    def _config_response(intents: Sequence, examples: Sequence) -> OutboundPrescreenConfigResponse:
        by_intent: dict[int, dict[str, list[str]]] = {}
        ready_by_intent: dict[int, bool] = {}
        for example in examples:
            bucket = by_intent.setdefault(example.intent_id, {"positive": [], "negative": []})
            bucket[example.example_type].append(example.text)
            ready_by_intent[example.intent_id] = ready_by_intent.get(example.intent_id, True) and bool(
                example.embedding_status == "ready" and example.embedding
            )
        return OutboundPrescreenConfigResponse(
            intents=[
                OutboundPrescreenIntentResponse(
                    id=intent.id,
                    intent_key=intent.intent_key,
                    name=intent.name,
                    enabled=intent.enabled,
                    similarity_threshold=float(intent.similarity_threshold),
                    is_system=intent.is_system,
                    positive_examples=by_intent.get(intent.id, {}).get("positive", []),
                    negative_examples=by_intent.get(intent.id, {}).get("negative", []),
                    embeddings_ready=ready_by_intent.get(intent.id, False),
                    created_at=intent.created_at,
                    updated_at=intent.updated_at,
                )
                for intent in intents
            ]
        )
