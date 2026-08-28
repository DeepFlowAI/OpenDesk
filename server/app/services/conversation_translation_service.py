"""Conversation-level language detection and translation orchestration."""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.core.exceptions import BusinessError, NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.enums import MessageContentType, MessageSenderType
from app.libs.langdetect import LanguageDetectionError, create_language_detector
from app.libs.llm import LLMProviderError, create_llm_client
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.conversation_translation import (
    ConversationTranslationSettingsResponse,
    ConversationTranslationSettingsUpdate,
)
from app.schemas.permission import EffectivePrincipal
from app.services.lingomaster_settings_service import LingoMasterSettingsService
from app.services.system_settings_service import SystemSettingsService


TRANSLATION_METADATA_KEY = "translation"
TRANSLATABLE_CONTENT_TYPES = {
    MessageContentType.TEXT.value,
    MessageContentType.RICH_TEXT.value,
}
LANGUAGE_DECISION_MAX_TOKENS = 256
LANGUAGE_DECISION_SYSTEM_PROMPT = (
    "You are a language classifier. Your entire response must be exactly one "
    "lowercase ISO 639-1 code such as es. Never include words, labels, punctuation, "
    "Markdown, or explanation."
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VisitorMessageTranslationResult:
    """Realtime updates produced while processing a visitor message."""

    conversation: object
    message_payload: dict[str, Any] | None = None
    settings_update: ConversationTranslationSettingsResponse | None = None


class ConversationTranslationService:
    """Coordinate conversation state, detection, prompts, and LLM calls."""

    _language_decision_locks: dict[int, asyncio.Lock] = {}

    @staticmethod
    def normalize_language_code(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().replace("_", "-")
        if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?", normalized):
            return None
        language, *region = normalized.split("-", 1)
        language = language.lower()
        if not region:
            return {"es": "es-419", "pt": "pt-BR"}.get(language, language)
        return f"{language}-{region[0].upper()}"

    @staticmethod
    def same_language(left: str | None, right: str | None) -> bool:
        left_code = ConversationTranslationService.normalize_language_code(left)
        right_code = ConversationTranslationService.normalize_language_code(right)
        return bool(left_code and right_code and left_code.split("-", 1)[0] == right_code.split("-", 1)[0])

    @staticmethod
    def plain_text(content_type: str, content: str) -> str:
        if content_type != MessageContentType.RICH_TEXT.value:
            return content.strip()
        text = re.sub(r"<[^>]*>", " ", content)
        return re.sub(r"\s+", " ", unescape(text).replace("\xa0", " ")).strip()

    @staticmethod
    def is_detection_candidate(text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            return False
        if re.fullmatch(r"(?:https?://|www\.)\S+", normalized, flags=re.I):
            return False
        if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            return False
        cjk_count = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", normalized))
        if cjk_count:
            return True
        letters = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]", normalized)
        words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", normalized)
        if not letters:
            return False
        return not (
            len(letters) < settings.LANGUAGE_DETECTION_MIN_LATIN_LETTERS
            and len(words) < settings.LANGUAGE_DETECTION_MIN_LATIN_WORDS
        )

    @staticmethod
    def render_prompt(
        template: str,
        *,
        message: str,
        conversation_history: str,
        source_language: str,
        target_language: str,
    ) -> str:
        values = {
            "message": message,
            "conversation_history": conversation_history,
            "source_language": source_language,
            "target_language": target_language,
        }
        return re.sub(
            r"\{\{(message|conversation_history|source_language|target_language)\}\}",
            lambda match: values[match.group(1)],
            template,
        )

    @staticmethod
    def history_text(messages: list[object]) -> str:
        lines: list[str] = []
        for message in messages:
            text = ConversationTranslationService.plain_text(message.content_type, message.content)
            if not text:
                continue
            sender = "访客" if message.sender_type == MessageSenderType.VISITOR.value else "客服"
            lines.append(f"[{sender}] {text}")
        return "\n".join(lines)

    @staticmethod
    def _raw_state(conversation: object) -> dict[str, Any]:
        raw = getattr(conversation, "lingomaster_settings", None)
        return dict(raw) if isinstance(raw, dict) else {}

    @staticmethod
    async def _agent_language(db: AsyncSession, tenant_id: int, agent_id: int | None) -> str:
        system = await SystemSettingsService.get_settings(db, tenant_id)
        if agent_id is None:
            return system.default_language
        employee = await EmployeeRepository.get_by_id(db, agent_id)
        value = getattr(employee, "default_language", None) if employee else None
        if not value or value == "system":
            value = system.default_language
        return ConversationTranslationService.normalize_language_code(value) or "en"

    @staticmethod
    async def get_settings(
        db: AsyncSession,
        conversation_id: int,
        principal: EffectivePrincipal,
    ) -> ConversationTranslationSettingsResponse:
        from app.services.conversation_service import ConversationService

        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != principal.tenant_id:
            raise NotFoundError("Conversation not found")
        await ConversationService._assert_conversation_view_access(db, principal, conversation)
        global_settings = await LingoMasterSettingsService.get_settings(db, principal.tenant_id)
        agent_language = await ConversationTranslationService._agent_language(
            db,
            principal.tenant_id,
            conversation.agent_id or principal.user_id,
        )
        return ConversationTranslationService._state_response(conversation, global_settings.enabled, agent_language)

    @staticmethod
    def _state_response(
        conversation: object,
        global_enabled: bool,
        agent_language: str,
    ) -> ConversationTranslationSettingsResponse:
        raw = ConversationTranslationService._raw_state(conversation)
        visitor_preference = raw.get("visitor_translation_enabled", True) is not False
        agent_preference = raw.get("agent_translation_enabled", True) is not False
        mode = raw.get("visitor_target_mode") if raw.get("visitor_target_mode") in {"agent", "fixed"} else "agent"
        fixed_target = ConversationTranslationService.normalize_language_code(raw.get("visitor_target_language"))
        resolved_target = fixed_target if mode == "fixed" else agent_language
        updated_at = raw.get("updated_at")
        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at)
            except ValueError:
                updated_at = None
        return ConversationTranslationSettingsResponse(
            global_enabled=global_enabled,
            visitor_language=ConversationTranslationService.normalize_language_code(raw.get("visitor_language")),
            visitor_language_source=raw.get("visitor_language_source")
            if raw.get("visitor_language_source") in {"browser", "detected", "manual"}
            else None,
            visitor_language_locked=raw.get("visitor_language_locked") is True,
            visitor_translation_enabled=global_enabled and visitor_preference,
            agent_translation_enabled=global_enabled and agent_preference,
            visitor_translation_preference=visitor_preference,
            agent_translation_preference=agent_preference,
            visitor_target_mode=mode,
            visitor_target_language=fixed_target,
            resolved_visitor_target_language=resolved_target,
            agent_language=agent_language,
            updated_by=raw.get("updated_by") if isinstance(raw.get("updated_by"), int) else None,
            updated_at=updated_at if isinstance(updated_at, datetime) else None,
        )

    @staticmethod
    async def update_settings(
        db: AsyncSession,
        conversation_id: int,
        principal: EffectivePrincipal,
        data: ConversationTranslationSettingsUpdate,
    ) -> ConversationTranslationSettingsResponse:
        from app.services.conversation_service import ConversationService

        conversation = await ConversationRepository.get_by_id(db, conversation_id)
        if not conversation or conversation.tenant_id != principal.tenant_id:
            raise NotFoundError("Conversation not found")
        await ConversationService._assert_conversation_send_access(
            db,
            principal,
            conversation,
            MessageContentType.TEXT.value,
        )
        raw = ConversationTranslationService._raw_state(conversation)
        changes = data.model_dump(exclude_unset=True)
        if "visitor_translation_enabled" in changes:
            raw["visitor_translation_enabled"] = data.visitor_translation_enabled
        if "agent_translation_enabled" in changes:
            raw["agent_translation_enabled"] = data.agent_translation_enabled
        if data.visitor_language_mode == "manual":
            language = ConversationTranslationService.normalize_language_code(data.visitor_language)
            if not language:
                raise ValidationError("Invalid visitor language")
            raw.update({
                "visitor_language": language,
                "visitor_language_source": "manual",
                "visitor_language_locked": True,
            })
        elif data.visitor_language_mode == "auto":
            raw["visitor_language_locked"] = False
            if raw.get("visitor_language_source") == "manual":
                raw["visitor_language_source"] = "detected"
        if data.visitor_target_mode is not None:
            raw["visitor_target_mode"] = data.visitor_target_mode
            raw["visitor_target_language"] = (
                ConversationTranslationService.normalize_language_code(data.visitor_target_language)
                if data.visitor_target_mode == "fixed"
                else None
            )
            if data.visitor_target_mode == "fixed" and not raw["visitor_target_language"]:
                raise ValidationError("Invalid visitor target language")
        raw["updated_by"] = principal.user_id
        raw["updated_at"] = datetime.now(timezone.utc).isoformat()
        conversation = await ConversationRepository.update_lingomaster_settings(db, conversation, raw)
        global_settings = await LingoMasterSettingsService.get_settings(db, principal.tenant_id)
        agent_language = await ConversationTranslationService._agent_language(
            db,
            principal.tenant_id,
            conversation.agent_id or principal.user_id,
        )
        return ConversationTranslationService._state_response(conversation, global_settings.enabled, agent_language)

    @staticmethod
    async def set_browser_language_prior_managed(
        tenant_id: int,
        conversation_id: int,
        locale: str | None,
    ) -> None:
        language = ConversationTranslationService.normalize_language_code(locale)
        if not language:
            return
        async with AsyncSessionLocal() as db:
            conversation = await ConversationRepository.get_by_id(db, conversation_id)
            if not conversation or conversation.tenant_id != tenant_id:
                return
            raw = ConversationTranslationService._raw_state(conversation)
            if raw.get("visitor_language") or raw.get("visitor_language_locked") is True:
                return
            raw.update({
                "visitor_language": language,
                "visitor_language_source": "browser",
                "visitor_language_locked": False,
            })
            await ConversationRepository.update_lingomaster_settings(db, conversation, raw)

    @staticmethod
    async def send_agent_message_managed(
        *,
        conversation_id: int,
        content_type: str,
        content: str,
        principal: EffectivePrincipal,
        quoted_message_id: int | None = None,
        client_message_id: str | None = None,
    ) -> object:
        from app.services.conversation_service import ConversationService

        message_metadata = {"client_message_id": client_message_id} if client_message_id else {}
        prompt: str | None = None
        source_language: str | None = None
        target_language: str | None = None
        async with AsyncSessionLocal() as db:
            conversation = await ConversationRepository.get_by_id(db, conversation_id)
            if not conversation or conversation.tenant_id != principal.tenant_id:
                raise NotFoundError("Conversation not found")
            await ConversationService._assert_conversation_send_access(db, principal, conversation, content_type)
            if client_message_id:
                existing = await MessageRepository.get_by_client_message_id(
                    db,
                    principal.tenant_id,
                    conversation_id,
                    client_message_id,
                    sender_type=MessageSenderType.AGENT.value,
                    sender_id=principal.user_id,
                )
                if existing is not None:
                    return existing
            normalized_content = ConversationService.validate_message_content(content_type, content)
            state = ConversationTranslationService._state_response(
                conversation,
                (await LingoMasterSettingsService.get_settings(db, principal.tenant_id)).enabled,
                await ConversationTranslationService._agent_language(db, principal.tenant_id, principal.user_id),
            )
            if (
                content_type in TRANSLATABLE_CONTENT_TYPES
                and state.agent_translation_enabled
                and state.visitor_language
                and not ConversationTranslationService.same_language(state.agent_language, state.visitor_language)
            ):
                config = await LingoMasterSettingsService.get_settings(db, principal.tenant_id)
                history = await MessageRepository.get_translation_history(db, conversation_id)
                source_language = state.agent_language
                target_language = state.visitor_language
                prompt = ConversationTranslationService.render_prompt(
                    config.agent_prompt,
                    message=ConversationTranslationService.plain_text(content_type, normalized_content),
                    conversation_history=ConversationTranslationService.history_text(history),
                    source_language=source_language,
                    target_language=target_language,
                )
                logger.info(
                    "lingomaster_agent_translation_started tenant_id=%s conversation_id=%s "
                    "agent_id=%s source_language=%s target_language=%s",
                    principal.tenant_id,
                    conversation_id,
                    principal.user_id,
                    source_language,
                    target_language,
                )
            else:
                return await ConversationService.send_message(
                    db,
                    conversation_id=conversation_id,
                    sender_type=MessageSenderType.AGENT.value,
                    sender_id=principal.user_id,
                    content_type=content_type,
                    content=content,
                    tenant_id=principal.tenant_id,
                    metadata=message_metadata,
                    principal=principal,
                    quoted_message_id=quoted_message_id,
                )

        try:
            translated = await create_llm_client().complete(
                [{"role": "user", "content": prompt or ""}],
                temperature=0.0,
                timeout=settings.LLM_TIMEOUT_SECONDS,
                reasoning_effort="high",
            )
        except LLMProviderError as exc:
            logger.warning(
                "lingomaster_agent_translation_failed tenant_id=%s conversation_id=%s "
                "agent_id=%s source_language=%s target_language=%s error=%s",
                principal.tenant_id,
                conversation_id,
                principal.user_id,
                source_language,
                target_language,
                exc,
            )
            raise BusinessError(
                "Translation failed. Message was not sent",
                status_code=502,
                code="TRANSLATION_FAILED",
            ) from exc

        message_metadata[TRANSLATION_METADATA_KEY] = {
            "status": "translated",
            "source_language": source_language,
            "target_language": target_language,
            "translated_text": translated,
            "direction": "agent_to_visitor",
        }
        async with AsyncSessionLocal() as db:
            if client_message_id:
                existing = await MessageRepository.get_by_client_message_id(
                    db,
                    principal.tenant_id,
                    conversation_id,
                    client_message_id,
                    sender_type=MessageSenderType.AGENT.value,
                    sender_id=principal.user_id,
                )
                if existing is not None:
                    return existing
            message = await ConversationService.send_message(
                db,
                conversation_id=conversation_id,
                sender_type=MessageSenderType.AGENT.value,
                sender_id=principal.user_id,
                content_type=content_type,
                content=content,
                tenant_id=principal.tenant_id,
                metadata=message_metadata,
                principal=principal,
                quoted_message_id=quoted_message_id,
            )
            logger.info(
                "lingomaster_agent_translation_completed tenant_id=%s conversation_id=%s "
                "message_id=%s agent_id=%s source_language=%s target_language=%s status=translated",
                principal.tenant_id,
                conversation_id,
                getattr(message, "id", None),
                principal.user_id,
                source_language,
                target_language,
            )
            return message

    @staticmethod
    async def get_agent_message_payload_managed(
        message_id: int,
        principal: EffectivePrincipal,
    ) -> dict[str, Any]:
        from app.services.conversation_agent_display_setting_service import ConversationAgentDisplaySettingService
        from app.services.conversation_service import ConversationService

        async with AsyncSessionLocal() as db:
            message = await MessageRepository.get_by_id_for_tenant(db, principal.tenant_id, message_id)
            if message is None:
                raise NotFoundError("Message not found")
            employee = await EmployeeRepository.get_by_id(db, principal.user_id)
            display_mode = await ConversationAgentDisplaySettingService.get_display_mode(db, principal.tenant_id)
            return ConversationService._message_response_payload(
                message,
                conversation_id=message.conversation_id,
                sender_name=ConversationService.agent_display_name(employee, display_mode) if employee else None,
                sender_avatar=employee.avatar if employee else None,
                viewer_agent_id=principal.user_id,
            )

    @staticmethod
    async def process_visitor_message_managed(
        *,
        tenant_id: int,
        message_id: int,
        on_pending: Callable[[VisitorMessageTranslationResult], Awaitable[None]] | None = None,
    ) -> VisitorMessageTranslationResult | None:
        from app.services.conversation_service import ConversationService

        async with AsyncSessionLocal() as db:
            message = await MessageRepository.get_by_id_for_tenant(db, tenant_id, message_id)
            if message is None:
                logger.warning(
                    "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                    "message_id=%s skip_reason=message_not_found",
                    tenant_id,
                    None,
                    message_id,
                )
                return None
            conversation_id = message.conversation_id
            if message.sender_type != MessageSenderType.VISITOR.value:
                logger.info(
                    "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                    "message_id=%s skip_reason=not_visitor_message sender_type=%s",
                    tenant_id,
                    conversation_id,
                    message_id,
                    message.sender_type,
                )
                return None
            if message.content_type not in TRANSLATABLE_CONTENT_TYPES:
                logger.info(
                    "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                    "message_id=%s skip_reason=unsupported_content_type content_type=%s",
                    tenant_id,
                    conversation_id,
                    message_id,
                    message.content_type,
                )
                return None
            conversation = await ConversationRepository.get_by_id(db, conversation_id)
            if conversation is None:
                logger.warning(
                    "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                    "message_id=%s skip_reason=conversation_not_found",
                    tenant_id,
                    conversation_id,
                    message_id,
                )
                return None
            config = await LingoMasterSettingsService.get_settings(db, tenant_id)
            agent_language = await ConversationTranslationService._agent_language(db, tenant_id, conversation.agent_id)
            state = ConversationTranslationService._state_response(conversation, config.enabled, agent_language)
            if not state.global_enabled or not (state.visitor_translation_enabled or state.agent_translation_enabled):
                logger.info(
                    "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                    "message_id=%s skip_reason=translation_disabled global_enabled=%s "
                    "visitor_enabled=%s agent_enabled=%s",
                    tenant_id,
                    conversation_id,
                    message_id,
                    state.global_enabled,
                    state.visitor_translation_enabled,
                    state.agent_translation_enabled,
                )
                return None
            text = ConversationTranslationService.plain_text(message.content_type, message.content)
            if not ConversationTranslationService.is_detection_candidate(text):
                logger.info(
                    "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                    "message_id=%s skip_reason=not_detection_candidate content_type=%s",
                    tenant_id,
                    conversation_id,
                    message_id,
                    message.content_type,
                )
                return None
            history = await MessageRepository.get_translation_history(
                db,
                conversation.id,
                before_message_id=message.id,
            )
            recent = await MessageRepository.get_recent_visitor_text_messages(
                db,
                conversation.id,
                limit=settings.LANGUAGE_DECISION_RECENT_VISITOR_MESSAGES,
            )

        try:
            detection = await create_language_detector().detect(text)
        except (LanguageDetectionError, ValueError) as exc:
            logger.warning(
                "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                "message_id=%s skip_reason=language_detection_failed detector_provider=%s error=%s",
                tenant_id,
                conversation_id,
                message_id,
                settings.LANGUAGE_DETECTOR_PROVIDER,
                exc,
            )
            return None
        if detection.confidence < settings.LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD:
            logger.info(
                "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                "message_id=%s skip_reason=low_detection_confidence detected_language=%s "
                "confidence=%.3f threshold=%.3f",
                tenant_id,
                conversation_id,
                message_id,
                detection.language,
                detection.confidence,
                settings.LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD,
            )
            return None
        source_language = ConversationTranslationService.normalize_language_code(detection.language)
        if source_language is None:
            logger.warning(
                "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                "message_id=%s skip_reason=invalid_detected_language detected_language=%s",
                tenant_id,
                conversation_id,
                message_id,
                detection.language,
            )
            return None

        decided_language = source_language
        if (
            state.visitor_language
            and not state.visitor_language_locked
            and not ConversationTranslationService.same_language(source_language, state.visitor_language)
        ):
            lock = ConversationTranslationService._language_decision_locks.setdefault(conversation_id, asyncio.Lock())
            async with lock:
                recent_text = "\n".join(
                    ConversationTranslationService.plain_text(item.content_type, item.content)
                    for item in recent
                )
                decision_prompt = (
                    "Determine the visitor's current communication language from the recent messages. "
                    "Return only an ISO 639-1 language code.\n"
                    f"Current recorded language: {state.visitor_language}\nRecent messages:\n{recent_text}"
                )
                fallback_language = (
                    source_language
                    if state.visitor_language_source in {None, "browser"}
                    else state.visitor_language
                )
                try:
                    decided_language = ConversationTranslationService.normalize_language_code(
                        await create_llm_client().complete(
                            [
                                {"role": "system", "content": LANGUAGE_DECISION_SYSTEM_PROMPT},
                                {"role": "user", "content": decision_prompt},
                            ],
                            temperature=0.0,
                            max_tokens=LANGUAGE_DECISION_MAX_TOKENS,
                            timeout=settings.LLM_TIMEOUT_SECONDS,
                            reasoning_effort="high",
                        )
                    ) or fallback_language
                except LLMProviderError as exc:
                    logger.warning(
                        "lingomaster_language_decision_failed tenant_id=%s conversation_id=%s "
                        "message_id=%s detected_language=%s recorded_language=%s "
                        "fallback_language=%s error=%s",
                        tenant_id,
                        conversation_id,
                        message_id,
                        source_language,
                        state.visitor_language,
                        fallback_language,
                        exc,
                    )
                    decided_language = fallback_language

        settings_update: ConversationTranslationSettingsResponse | None = None
        if not state.visitor_language_locked and (
            not state.visitor_language
            or not ConversationTranslationService.same_language(decided_language, state.visitor_language)
        ):
            async with AsyncSessionLocal() as db:
                conversation = await ConversationRepository.get_by_id(db, conversation_id)
                if conversation is not None:
                    raw = ConversationTranslationService._raw_state(conversation)
                    if raw.get("visitor_language_locked") is not True:
                        raw.update({
                            "visitor_language": decided_language,
                            "visitor_language_source": "detected",
                            "visitor_language_locked": False,
                        })
                        conversation = await ConversationRepository.update_lingomaster_settings(
                            db,
                            conversation,
                            raw,
                        )
                        settings_update = ConversationTranslationService._state_response(
                            conversation,
                            config.enabled,
                            agent_language,
                        )
                        logger.info(
                            "lingomaster_visitor_language_updated tenant_id=%s conversation_id=%s "
                            "message_id=%s previous_language=%s detected_language=%s decided_language=%s",
                            tenant_id,
                            conversation_id,
                            message_id,
                            state.visitor_language,
                            source_language,
                            decided_language,
                        )

        language_update_result = (
            VisitorMessageTranslationResult(
                conversation=conversation,
                settings_update=settings_update,
            )
            if settings_update is not None
            else None
        )
        target_language = state.resolved_visitor_target_language
        if not state.visitor_translation_enabled:
            logger.info(
                "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                "message_id=%s skip_reason=visitor_translation_disabled source_language=%s "
                "target_language=%s",
                tenant_id,
                conversation_id,
                message_id,
                source_language,
                target_language,
            )
            return language_update_result
        if not target_language:
            logger.warning(
                "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                "message_id=%s skip_reason=target_language_missing source_language=%s",
                tenant_id,
                conversation_id,
                message_id,
                source_language,
            )
            return language_update_result
        if ConversationTranslationService.same_language(source_language, target_language):
            logger.info(
                "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                "message_id=%s skip_reason=same_language source_language=%s target_language=%s",
                tenant_id,
                conversation_id,
                message_id,
                source_language,
                target_language,
            )
            return language_update_result
        prompt = ConversationTranslationService.render_prompt(
            config.visitor_prompt,
            message=text,
            conversation_history=ConversationTranslationService.history_text(history),
            source_language=source_language,
            target_language=target_language,
        )
        pending_translation: dict[str, Any] = {
            "status": "pending",
            "source_language": source_language,
            "target_language": target_language,
            "direction": "visitor_to_agent",
        }
        async with AsyncSessionLocal() as db:
            pending_message = await MessageRepository.get_by_id_for_tenant(db, tenant_id, message_id)
            pending_conversation = await ConversationRepository.get_by_id(db, conversation_id)
            if pending_message is None or pending_conversation is None:
                logger.warning(
                    "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                    "message_id=%s skip_reason=pending_target_missing message_exists=%s "
                    "conversation_exists=%s",
                    tenant_id,
                    conversation_id,
                    message_id,
                    pending_message is not None,
                    pending_conversation is not None,
                )
                return None
            metadata = dict(pending_message.metadata_ or {})
            metadata[TRANSLATION_METADATA_KEY] = pending_translation
            pending_message = await MessageRepository.update_metadata(db, pending_message, metadata)
            pending_payload = ConversationService._message_response_payload(
                pending_message,
                conversation_id=conversation_id,
                sender_name=getattr(pending_conversation.visitor, "name", None),
                sender_avatar=None,
                visitor_facing=False,
            )
            pending_payload["created_at"] = (
                pending_message.created_at.isoformat() if pending_message.created_at else None
            )

        if on_pending is not None:
            try:
                await on_pending(
                    VisitorMessageTranslationResult(
                        conversation=pending_conversation,
                        message_payload=pending_payload,
                    )
                )
            except Exception:
                logger.exception(
                    "lingomaster_visitor_translation_pending_emit_failed tenant_id=%s "
                    "conversation_id=%s message_id=%s",
                    tenant_id,
                    conversation_id,
                    message_id,
                )

        translation: dict[str, Any] = {
            "status": "failed",
            "source_language": source_language,
            "target_language": target_language,
            "direction": "visitor_to_agent",
        }
        logger.info(
            "lingomaster_visitor_translation_started tenant_id=%s conversation_id=%s message_id=%s "
            "source_language=%s target_language=%s detection_confidence=%.3f",
            tenant_id,
            conversation_id,
            message_id,
            source_language,
            target_language,
            detection.confidence,
        )
        try:
            translation["translated_text"] = await create_llm_client().complete(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                timeout=settings.LLM_TIMEOUT_SECONDS,
                reasoning_effort="high",
            )
            translation["status"] = "translated"
        except LLMProviderError as exc:
            logger.warning(
                "lingomaster_visitor_translation_llm_failed tenant_id=%s conversation_id=%s "
                "message_id=%s source_language=%s target_language=%s error=%s",
                tenant_id,
                conversation_id,
                message_id,
                source_language,
                target_language,
                exc,
            )

        async with AsyncSessionLocal() as db:
            message = await MessageRepository.get_by_id_for_tenant(db, tenant_id, message_id)
            conversation = await ConversationRepository.get_by_id(db, conversation_id)
            if message is None or conversation is None:
                logger.warning(
                    "lingomaster_visitor_translation_skipped tenant_id=%s conversation_id=%s "
                    "message_id=%s skip_reason=persistence_target_missing message_exists=%s "
                    "conversation_exists=%s",
                    tenant_id,
                    conversation_id,
                    message_id,
                    message is not None,
                    conversation is not None,
                )
                return None
            metadata = dict(message.metadata_ or {})
            metadata[TRANSLATION_METADATA_KEY] = translation
            message = await MessageRepository.update_metadata(db, message, metadata)
            payload = ConversationService._message_response_payload(
                message,
                conversation_id=conversation_id,
                sender_name=getattr(conversation.visitor, "name", None),
                sender_avatar=None,
                visitor_facing=False,
            )
            payload["created_at"] = message.created_at.isoformat() if message.created_at else None
            logger.info(
                "lingomaster_visitor_translation_completed tenant_id=%s conversation_id=%s message_id=%s "
                "source_language=%s target_language=%s status=%s",
                tenant_id,
                conversation_id,
                message_id,
                source_language,
                target_language,
                translation["status"],
            )
            return VisitorMessageTranslationResult(
                conversation=conversation,
                message_payload=payload,
                settings_update=settings_update,
            )
