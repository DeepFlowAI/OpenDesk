"""LiteLLM Router implementation with ordered primary and backup deployments."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from app.configs.settings import settings
from app.libs.llm.base import BaseLLMClient, LLMProviderError


class LiteLLMClient(BaseLLMClient):
    """Route completions through configured primary and backup deployments."""

    PRIMARY_ALIAS = "opendesk-primary"
    BACKUP_ALIAS = "opendesk-backup"

    def __init__(self) -> None:
        self._router: Any | None = None
        self._entry_model: str | None = None

    def _build_router(self) -> tuple[Any, str]:
        try:
            from litellm import Router
        except ImportError as exc:
            raise LLMProviderError("LiteLLM is not installed") from exc

        primary_key = settings.LLM_PRIMARY_API_KEY.strip()
        backup_key = (settings.LLM_BACKUP_API_KEY or settings.ALIYUN_DASHSCOPE_API_KEY).strip()
        model_list: list[dict[str, object]] = []
        fallbacks: list[dict[str, list[str]]] = []

        if primary_key:
            model_list.append(
                {
                    "model_name": self.PRIMARY_ALIAS,
                    "litellm_params": {
                        "model": settings.LLM_PRIMARY_MODEL,
                        "api_key": primary_key,
                        "api_base": settings.LLM_PRIMARY_API_BASE,
                    },
                }
            )
        if backup_key:
            model_list.append(
                {
                    "model_name": self.BACKUP_ALIAS,
                    "litellm_params": {
                        "model": settings.LLM_BACKUP_MODEL,
                        "api_key": backup_key,
                        "api_base": settings.LLM_BACKUP_API_BASE,
                    },
                }
            )

        if not model_list:
            raise LLMProviderError("No LLM API key is configured")
        entry_model = self.PRIMARY_ALIAS if primary_key else self.BACKUP_ALIAS
        if primary_key and backup_key:
            fallbacks.append({self.PRIMARY_ALIAS: [self.BACKUP_ALIAS]})

        router = Router(
            model_list=model_list,
            fallbacks=fallbacks,
            num_retries=settings.LLM_MAX_RETRIES,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        return router, entry_model

    def _ensure_router(self) -> tuple[Any, str]:
        if self._router is None or self._entry_model is None:
            self._router, self._entry_model = self._build_router()
        return self._router, self._entry_model

    @staticmethod
    def _response_text(response: Any) -> str:
        try:
            choice = response.choices[0]
            message = choice.message
            content = message.content
        except (AttributeError, IndexError, KeyError, TypeError):
            try:
                content = response["choices"][0]["message"]["content"]
            except (IndexError, KeyError, TypeError) as exc:
                raise LLMProviderError("LLM provider returned an invalid response") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("LLM provider returned empty text")
        return content.strip()

    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout: float | None = None,
        reasoning_effort: Literal["high", "max"] | None = None,
    ) -> str:
        normalized = [dict(message) for message in messages]
        if not normalized:
            raise LLMProviderError("At least one LLM message is required")
        router, entry_model = self._ensure_router()
        kwargs: dict[str, object] = {
            "model": entry_model,
            "messages": normalized,
            "temperature": temperature,
            "timeout": timeout or settings.LLM_TIMEOUT_SECONDS,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if reasoning_effort is not None:
            kwargs["extra_body"] = {
                "thinking": {"type": "enabled"},
                "enable_thinking": True,
                "reasoning_effort": reasoning_effort,
            }
        try:
            response = await router.acompletion(**kwargs)
        except Exception as exc:
            raise LLMProviderError(
                f"LLM completion failed provider_error_type={type(exc).__name__}"
            ) from exc
        return self._response_text(response)
