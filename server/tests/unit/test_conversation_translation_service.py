"""Unit tests for conversation translation orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import BusinessError
from app.constants.lingomaster import (
    DEFAULT_AGENT_TRANSLATION_PROMPT,
    DEFAULT_VISITOR_TRANSLATION_PROMPT,
)
from app.libs.langdetect import LanguageDetection, LanguageDetectionError
from app.libs.llm import LLMProviderError
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.lingomaster import LingoMasterSettingsResponse
from app.schemas.permission import EffectivePrincipal
from app.services.conversation_service import ConversationService
from app.services.conversation_translation_service import (
    LANGUAGE_DECISION_MAX_TOKENS,
    ConversationTranslationService,
)
from app.services.lingomaster_settings_service import LingoMasterSettingsService


class SessionTracker:
    active = False
    opens = 0
    closes = 0


class FakeSessionContext:
    async def __aenter__(self):
        assert SessionTracker.active is False
        SessionTracker.active = True
        SessionTracker.opens += 1
        return SimpleNamespace()

    async def __aexit__(self, *_exc_info):
        SessionTracker.active = False
        SessionTracker.closes += 1


@pytest.fixture(autouse=True)
def _reset_session_tracker():
    SessionTracker.active = False
    SessionTracker.opens = 0
    SessionTracker.closes = 0


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=9,
        tenant_id=3,
        permissions=["chat.workspace.use"],
    )


def _conversation() -> SimpleNamespace:
    return SimpleNamespace(
        id=12,
        tenant_id=3,
        agent_id=9,
        lingomaster_settings={
            "visitor_language": "ja",
            "visitor_language_source": "detected",
            "agent_translation_enabled": True,
        },
    )


def _message(metadata: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=44,
        conversation_id=12,
        sender_type="agent",
        sender_id=9,
        content_type="text",
        content="原文",
        metadata_=metadata or {},
        is_recalled=False,
        created_at=datetime.now(timezone.utc),
        visitor_read_at=None,
        visitor_delivered_at=None,
        visitor_online_at_send=True,
    )


class TestConversationTranslationRules:
    def test_default_prompts_define_context_and_untrusted_text_rules(self) -> None:
        for prompt in (DEFAULT_VISITOR_TRANSLATION_PROMPT, DEFAULT_AGENT_TRANSLATION_PROMPT):
            assert "{{source_language}}" in prompt
            assert "{{target_language}}" in prompt
            assert "{{conversation_history}}" in prompt
            assert "{{message}}" in prompt
            assert "消解代词和省略" in prompt
            assert "使用所指对象的明确名称" in prompt
            assert "不可信的待翻译文本" in prompt
            assert "订单号、错误码、变量、占位符" in prompt

    def test_render_prompt_does_not_expand_variables_inside_content(self) -> None:
        rendered = ConversationTranslationService.render_prompt(
            "{{source_language}}|{{target_language}}|{{conversation_history}}|{{message}}",
            message="Keep {{source_language}} unchanged",
            conversation_history="Keep {{target_language}} unchanged",
            source_language="en",
            target_language="zh",
        )

        assert rendered == (
            "en|zh|Keep {{target_language}} unchanged|Keep {{source_language}} unchanged"
        )

    def test_normalize_and_compare_bcp47_primary_language(self) -> None:
        assert ConversationTranslationService.normalize_language_code("es") == "es-419"
        assert ConversationTranslationService.normalize_language_code("pt_pt") == "pt-PT"
        assert ConversationTranslationService.same_language("es-ES", "es-419") is True
        assert ConversationTranslationService.same_language("ja", "zh") is False

    def test_short_latin_text_is_not_detection_candidate(self) -> None:
        assert ConversationTranslationService.is_detection_candidate("ok") is False
        assert ConversationTranslationService.is_detection_candidate("https://example.com") is False
        assert ConversationTranslationService.is_detection_candidate("这是问题") is True
        assert ConversationTranslationService.is_detection_candidate("I need help with my order") is True

    def test_history_uses_original_public_text(self) -> None:
        history = ConversationTranslationService.history_text([
            SimpleNamespace(sender_type="visitor", content_type="text", content="こんにちは"),
            SimpleNamespace(sender_type="agent", content_type="rich_text", content="<p>您好</p>"),
        ])
        assert history == "[访客] こんにちは\n[客服] 您好"

    def test_visitor_projection_uses_translation_without_metadata(self) -> None:
        message = _message({
            "client_message_id": "client-1",
            "translation": {
                "status": "translated",
                "translated_text": "翻訳文",
                "source_language": "zh",
                "target_language": "ja",
                "direction": "agent_to_visitor",
            },
        })
        payload = ConversationService._message_response_payload(
            message,
            conversation_public_id="public-1",
            visitor_facing=True,
        )
        assert payload["content"] == "翻訳文"
        assert "translation" not in payload["metadata"]


class TestManagedAgentTranslation:
    def _patch_common(self, monkeypatch: pytest.MonkeyPatch, saved_message: object) -> None:
        monkeypatch.setattr(
            "app.services.conversation_translation_service.AsyncSessionLocal",
            lambda: FakeSessionContext(),
        )
        monkeypatch.setattr(ConversationRepository, "get_by_id", AsyncMock(return_value=_conversation()))
        monkeypatch.setattr(
            ConversationService,
            "_assert_conversation_send_access",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            ConversationTranslationService,
            "_agent_language",
            AsyncMock(return_value="zh"),
        )
        monkeypatch.setattr(
            LingoMasterSettingsService,
            "get_settings",
            AsyncMock(return_value=LingoMasterSettingsResponse(enabled=True)),
        )
        monkeypatch.setattr(MessageRepository, "get_translation_history", AsyncMock(return_value=[]))
        monkeypatch.setattr(ConversationService, "send_message", AsyncMock(return_value=saved_message))

    @pytest.mark.asyncio
    async def test_managed_send_closes_db_during_llm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        saved = _message()
        self._patch_common(monkeypatch, saved)
        active_during_llm: list[bool] = []
        llm_kwargs: list[dict] = []

        class Client:
            async def complete(self, *_args, **kwargs) -> str:
                active_during_llm.append(SessionTracker.active)
                llm_kwargs.append(kwargs)
                return "翻訳文"

        monkeypatch.setattr(
            "app.services.conversation_translation_service.create_llm_client",
            lambda: Client(),
        )

        result = await ConversationTranslationService.send_agent_message_managed(
            conversation_id=12,
            content_type="text",
            content="原文",
            principal=_principal(),
        )

        assert result is saved
        assert active_during_llm == [False]
        assert llm_kwargs[0]["reasoning_effort"] == "high"
        assert SessionTracker.opens == SessionTracker.closes == 2
        metadata = ConversationService.send_message.await_args.kwargs["metadata"]
        assert metadata["translation"]["translated_text"] == "翻訳文"

    @pytest.mark.asyncio
    async def test_translation_failure_does_not_save_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_common(monkeypatch, _message())

        class Client:
            async def complete(self, *_args, **_kwargs) -> str:
                assert SessionTracker.active is False
                raise LLMProviderError("provider failed")

        monkeypatch.setattr(
            "app.services.conversation_translation_service.create_llm_client",
            lambda: Client(),
        )

        with pytest.raises(BusinessError) as exc_info:
            await ConversationTranslationService.send_agent_message_managed(
                conversation_id=12,
                content_type="text",
                content="原文",
                principal=_principal(),
            )

        assert exc_info.value.code == "TRANSLATION_FAILED"
        ConversationService.send_message.assert_not_awaited()
        assert SessionTracker.opens == SessionTracker.closes == 1


class TestManagedVisitorTranslation:
    @pytest.mark.asyncio
    async def test_detection_and_translation_run_without_db_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        conversation = _conversation()
        conversation.lingomaster_settings["visitor_language"] = "en"
        conversation.visitor = SimpleNamespace(name="Visitor")
        message = SimpleNamespace(
            **{
                **_message().__dict__,
                "sender_type": "visitor",
                "sender_id": None,
                "content": "I need help with my order",
                "metadata_": {},
            }
        )
        outside_session_checks: list[bool] = []
        llm_kwargs: list[dict] = []
        pending_payloads: list[dict] = []

        class Detector:
            async def detect(self, _text: str) -> LanguageDetection:
                outside_session_checks.append(SessionTracker.active)
                return LanguageDetection(language="en", confidence=0.99)

        class Client:
            async def complete(self, *_args, **kwargs) -> str:
                outside_session_checks.append(SessionTracker.active)
                llm_kwargs.append(kwargs)
                return "我需要订单帮助"

        async def update_metadata(_db, item, metadata):
            item.metadata_ = metadata
            return item

        async def on_pending(result) -> None:
            assert SessionTracker.active is False
            pending_payloads.append(result.message_payload)

        monkeypatch.setattr(
            "app.services.conversation_translation_service.AsyncSessionLocal",
            lambda: FakeSessionContext(),
        )
        monkeypatch.setattr(MessageRepository, "get_by_id_for_tenant", AsyncMock(return_value=message))
        monkeypatch.setattr(ConversationRepository, "get_by_id", AsyncMock(return_value=conversation))
        monkeypatch.setattr(
            LingoMasterSettingsService,
            "get_settings",
            AsyncMock(return_value=LingoMasterSettingsResponse(enabled=True)),
        )
        monkeypatch.setattr(
            ConversationTranslationService,
            "_agent_language",
            AsyncMock(return_value="zh"),
        )
        monkeypatch.setattr(MessageRepository, "get_translation_history", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            MessageRepository,
            "get_recent_visitor_text_messages",
            AsyncMock(return_value=[message]),
        )
        monkeypatch.setattr(MessageRepository, "update_metadata", update_metadata)
        monkeypatch.setattr(
            ConversationService,
            "_message_response_payload",
            lambda *_args, **_kwargs: {
                "id": message.id,
                "metadata": dict(message.metadata_),
            },
        )
        monkeypatch.setattr(
            "app.services.conversation_translation_service.create_language_detector",
            lambda: Detector(),
        )
        monkeypatch.setattr(
            "app.services.conversation_translation_service.create_llm_client",
            lambda: Client(),
        )

        result = await ConversationTranslationService.process_visitor_message_managed(
            tenant_id=3,
            message_id=message.id,
            on_pending=on_pending,
        )

        assert result is not None
        assert outside_session_checks == [False, False]
        assert llm_kwargs[0]["reasoning_effort"] == "high"
        assert pending_payloads[0]["metadata"]["translation"]["status"] == "pending"
        assert SessionTracker.opens == SessionTracker.closes == 3
        assert message.metadata_["translation"]["translated_text"] == "我需要订单帮助"

    @pytest.mark.asyncio
    async def test_browser_language_uses_detected_language_when_llm_decision_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        conversation = _conversation()
        conversation.lingomaster_settings.update({
            "visitor_language": "zh-CN",
            "visitor_language_source": "browser",
        })
        conversation.visitor = SimpleNamespace(name="Visitor")
        message = SimpleNamespace(
            **{
                **_message().__dict__,
                "sender_type": "visitor",
                "sender_id": None,
                "content": "Necesito ayuda con mi pedido",
                "metadata_": {},
            }
        )
        decision_kwargs: list[dict] = []

        class Detector:
            async def detect(self, _text: str) -> LanguageDetection:
                return LanguageDetection(language="es", confidence=0.99)

        class Client:
            calls = 0

            async def complete(self, *_args, **kwargs) -> str:
                self.calls += 1
                if self.calls == 1:
                    decision_kwargs.append(kwargs)
                    raise LLMProviderError("LLM provider returned empty text")
                return "我需要订单帮助"

        async def update_settings(_db, item, data):
            item.lingomaster_settings = data
            return item

        async def update_metadata(_db, item, metadata):
            item.metadata_ = metadata
            return item

        client = Client()
        monkeypatch.setattr(
            "app.services.conversation_translation_service.AsyncSessionLocal",
            lambda: FakeSessionContext(),
        )
        monkeypatch.setattr(MessageRepository, "get_by_id_for_tenant", AsyncMock(return_value=message))
        monkeypatch.setattr(ConversationRepository, "get_by_id", AsyncMock(return_value=conversation))
        monkeypatch.setattr(
            ConversationRepository,
            "update_lingomaster_settings",
            update_settings,
        )
        monkeypatch.setattr(
            LingoMasterSettingsService,
            "get_settings",
            AsyncMock(return_value=LingoMasterSettingsResponse(enabled=True)),
        )
        monkeypatch.setattr(
            ConversationTranslationService,
            "_agent_language",
            AsyncMock(return_value="zh"),
        )
        monkeypatch.setattr(MessageRepository, "get_translation_history", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            MessageRepository,
            "get_recent_visitor_text_messages",
            AsyncMock(return_value=[message]),
        )
        monkeypatch.setattr(MessageRepository, "update_metadata", update_metadata)
        monkeypatch.setattr(
            ConversationService,
            "_message_response_payload",
            lambda *_args, **_kwargs: {"id": message.id},
        )
        monkeypatch.setattr(
            "app.services.conversation_translation_service.create_language_detector",
            lambda: Detector(),
        )
        monkeypatch.setattr(
            "app.services.conversation_translation_service.create_llm_client",
            lambda: client,
        )

        with caplog.at_level("WARNING", logger="app.services.conversation_translation_service"):
            result = await ConversationTranslationService.process_visitor_message_managed(
                tenant_id=3,
                message_id=message.id,
            )

        assert result is not None
        assert result.settings_update is not None
        assert result.settings_update.visitor_language == "es-419"
        assert result.settings_update.visitor_language_source == "detected"
        assert decision_kwargs[0]["max_tokens"] == LANGUAGE_DECISION_MAX_TOKENS
        assert decision_kwargs[0]["reasoning_effort"] == "high"
        assert conversation.lingomaster_settings["visitor_language"] == "es-419"
        assert conversation.lingomaster_settings["visitor_language_source"] == "detected"
        assert message.metadata_["translation"]["translated_text"] == "我需要订单帮助"
        assert "fallback_language=es-419" in caplog.text
        assert SessionTracker.opens == SessionTracker.closes == 4

    @pytest.mark.asyncio
    async def test_detection_failure_logs_searchable_skip_reason(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        conversation = _conversation()
        message = SimpleNamespace(
            **{
                **_message().__dict__,
                "sender_type": "visitor",
                "sender_id": None,
                "content": "Necesito ayuda con mi pedido",
                "metadata_": {},
            }
        )

        class Detector:
            async def detect(self, _text: str) -> LanguageDetection:
                raise LanguageDetectionError("fastText language model path is not configured")

        monkeypatch.setattr(
            "app.services.conversation_translation_service.AsyncSessionLocal",
            lambda: FakeSessionContext(),
        )
        monkeypatch.setattr(MessageRepository, "get_by_id_for_tenant", AsyncMock(return_value=message))
        monkeypatch.setattr(ConversationRepository, "get_by_id", AsyncMock(return_value=conversation))
        monkeypatch.setattr(
            LingoMasterSettingsService,
            "get_settings",
            AsyncMock(return_value=LingoMasterSettingsResponse(enabled=True)),
        )
        monkeypatch.setattr(
            ConversationTranslationService,
            "_agent_language",
            AsyncMock(return_value="en"),
        )
        monkeypatch.setattr(MessageRepository, "get_translation_history", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            MessageRepository,
            "get_recent_visitor_text_messages",
            AsyncMock(return_value=[message]),
        )
        monkeypatch.setattr(
            "app.services.conversation_translation_service.create_language_detector",
            lambda: Detector(),
        )

        with caplog.at_level("WARNING", logger="app.services.conversation_translation_service"):
            result = await ConversationTranslationService.process_visitor_message_managed(
                tenant_id=3,
                message_id=message.id,
            )

        assert result is None
        assert "lingomaster_visitor_translation_skipped" in caplog.text
        assert "tenant_id=3 conversation_id=12 message_id=44" in caplog.text
        assert "skip_reason=language_detection_failed" in caplog.text
        assert "fastText language model path is not configured" in caplog.text
