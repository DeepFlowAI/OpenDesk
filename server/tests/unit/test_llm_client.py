"""Unit tests for the provider-neutral LLM client."""
from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.configs.settings import settings
from app.libs.llm.base import LLMProviderError
from app.libs.llm.factory import create_llm_client
from app.libs.llm.providers.litellm import LiteLLMClient


class TestLiteLLMClient:
    def test_factory_returns_litellm_client(self) -> None:
        assert isinstance(create_llm_client("litellm"), LiteLLMClient)

    def test_factory_rejects_unknown_provider(self) -> None:
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            create_llm_client("unknown")

    def test_router_configures_ordered_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, object] = {}

        class FakeRouter:
            def __init__(self, **kwargs: object) -> None:
                captured.update(kwargs)

        module = ModuleType("litellm")
        module.Router = FakeRouter  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "litellm", module)
        monkeypatch.setattr(settings, "LLM_PRIMARY_API_KEY", "primary-key")
        monkeypatch.setattr(settings, "LLM_BACKUP_API_KEY", "backup-key")

        _router, entry_model = LiteLLMClient()._build_router()

        assert entry_model == LiteLLMClient.PRIMARY_ALIAS
        assert captured["fallbacks"] == [
            {LiteLLMClient.PRIMARY_ALIAS: [LiteLLMClient.BACKUP_ALIAS]}
        ]
        assert len(captured["model_list"]) == 2  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_complete_returns_trimmed_text(self) -> None:
        client = LiteLLMClient()
        client._router = SimpleNamespace(
            acompletion=AsyncMock(
                return_value=SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=" translated "))]
                )
            )
        )
        client._entry_model = LiteLLMClient.PRIMARY_ALIAS

        result = await client.complete([{"role": "user", "content": "hello"}])

        assert result == "translated"
        client._router.acompletion.assert_awaited_once()
        assert "extra_body" not in client._router.acompletion.await_args.kwargs

    @pytest.mark.asyncio
    async def test_complete_can_enable_high_reasoning_for_one_request(self) -> None:
        client = LiteLLMClient()
        client._router = SimpleNamespace(
            acompletion=AsyncMock(
                return_value=SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="es"))]
                )
            )
        )
        client._entry_model = LiteLLMClient.PRIMARY_ALIAS

        result = await client.complete(
            [{"role": "user", "content": "language"}],
            reasoning_effort="high",
        )

        assert result == "es"
        assert "reasoning_effort" not in client._router.acompletion.await_args.kwargs
        assert client._router.acompletion.await_args.kwargs["extra_body"] == {
            "thinking": {"type": "enabled"},
            "enable_thinking": True,
            "reasoning_effort": "high",
        }

    @pytest.mark.asyncio
    async def test_complete_wraps_provider_error(self) -> None:
        client = LiteLLMClient()
        client._router = SimpleNamespace(acompletion=AsyncMock(side_effect=RuntimeError("secret")))
        client._entry_model = LiteLLMClient.PRIMARY_ALIAS

        with pytest.raises(
            LLMProviderError,
            match="LLM completion failed provider_error_type=RuntimeError",
        ):
            await client.complete([{"role": "user", "content": "hello"}])

    @pytest.mark.asyncio
    async def test_complete_rejects_empty_messages(self) -> None:
        with pytest.raises(LLMProviderError, match="At least one"):
            await LiteLLMClient().complete([])
