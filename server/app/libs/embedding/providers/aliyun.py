"""
Aliyun DashScope embedding provider.
"""
from __future__ import annotations

from collections.abc import Sequence

import httpx

from app.configs.settings import settings
from app.libs.embedding.base import BaseEmbeddingClient, EmbeddingProviderError


class AliyunEmbeddingClient(BaseEmbeddingClient):
    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        inputs = [text.strip() for text in texts if text and text.strip()]
        if len(inputs) != len(texts):
            raise EmbeddingProviderError("Embedding input text is required")
        if not settings.ALIYUN_DASHSCOPE_API_KEY.strip():
            raise EmbeddingProviderError("Aliyun DashScope API key is not configured")

        payload: dict[str, object] = {
            "model": settings.KNOWLEDGE_EMBEDDING_MODEL,
            "input": inputs,
            "dimensions": settings.KNOWLEDGE_EMBEDDING_DIMENSION,
        }
        headers = {"Authorization": f"Bearer {settings.ALIYUN_DASHSCOPE_API_KEY}"}
        try:
            async with httpx.AsyncClient(timeout=settings.KNOWLEDGE_EMBEDDING_TIMEOUT_SECONDS) as client:
                response = await client.post(settings.ALIYUN_DASHSCOPE_EMBEDDING_URL, headers=headers, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise EmbeddingProviderError(f"Embedding provider returned {exc.response.status_code}: {detail}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingProviderError(f"Embedding provider request failed: {exc}") from exc

        data = body.get("data")
        if not isinstance(data, list) or len(data) != len(inputs):
            raise EmbeddingProviderError("Embedding provider returned an invalid response")

        ordered = sorted(data, key=lambda item: int(item.get("index", 0)) if isinstance(item, dict) else 0)
        vectors: list[list[float]] = []
        for item in ordered:
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise EmbeddingProviderError("Embedding provider returned an invalid vector")
            vector = [float(value) for value in item["embedding"]]
            if len(vector) != settings.KNOWLEDGE_EMBEDDING_DIMENSION:
                raise EmbeddingProviderError("Embedding provider returned an unexpected vector dimension")
            vectors.append(vector)
        return vectors
