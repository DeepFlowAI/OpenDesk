"""
Embedding provider factory.
"""
from __future__ import annotations

from app.configs.settings import settings
from app.libs.embedding.base import BaseEmbeddingClient


def create_embedding_client(provider: str | None = None) -> BaseEmbeddingClient:
    name = (provider or settings.KNOWLEDGE_EMBEDDING_PROVIDER).strip().lower()
    match name:
        case "aliyun" | "dashscope":
            from app.libs.embedding.providers.aliyun import AliyunEmbeddingClient

            return AliyunEmbeddingClient()
        case _:
            raise ValueError(f"Unsupported embedding provider: {name}")
