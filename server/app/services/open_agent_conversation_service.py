"""
OpenAgent conversation service.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
import json
import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessError, ValidationError
from app.enums import ConversationStatus, MessageContentType, MessageSenderType
from app.libs.open_agent import create_open_agent_client
from app.libs.open_agent.base import BaseOpenAgentClient, OpenAgentClientError
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.channel import ChannelConfig
from app.schemas.open_agent_conversation import OpenAgentChatRequest
from app.services.conversation_service import ConversationService
from app.services.open_agent_settings_service import OpenAgentSettingsService


class OpenAgentConversationService:
    _ROUND_EVENT_ID_RE = re.compile(r"^r\d+-e\d+$")
    _MAX_TOOL_METADATA_VALUE_LENGTH = 2000
    _HUMAN_HANDOFF_TOOL_NAME = "human_handoff"
    _DEFAULT_HANDOFF_BRIEF = "这个问题需要人工客服进一步处理。"
    _HANDOFF_EVENT_CONFIRM_REQUESTED = "confirm_requested"
    _HANDOFF_EVENT_CONFIRMED_BY_VISITOR = "confirmed_by_visitor"
    _HANDOFF_EVENT_AUTO_TRIGGERED = "auto_triggered"
    _HANDOFF_TOOL_RESULT_SUCCESS = "handoff_success"
    _HANDOFF_TOOL_RESULT_FAILED = "handoff_failed"
    _CONFIRMED_BY_VISITOR_CONTENT = "您已确认转接人工客服"
    _HANDOFF_STATE_DISMISSED = "dismissed"
    _HANDOFF_FIELD_MAX_LENGTHS = {
        "brief": 200,
        "reason": 1000,
        "urgency": 16,
        "user_message": 1000,
        "agent_id": 128,
        "agent_group_id": 128,
        "business_type": 128,
    }

    @staticmethod
    def _is_round_event_id(event_id: str | None) -> bool:
        return bool(event_id and OpenAgentConversationService._ROUND_EVENT_ID_RE.match(event_id))

    @staticmethod
    def _sse_event(event: str, data: dict[str, Any], event_id: str | None = None) -> bytes:
        lines: list[str] = []
        if event_id:
            lines.append(f"id: {event_id}")
        lines.append(f"event: {event}")
        lines.append(f"data: {json.dumps(data, ensure_ascii=False, default=str)}")
        return ("\n".join(lines) + "\n\n").encode("utf-8")

    @staticmethod
    def _parse_sse_frame(frame: str) -> tuple[str, dict[str, Any] | None, str | None]:
        event = "message"
        event_id: str | None = None
        data_lines: list[str] = []
        for raw_line in frame.splitlines():
            line = raw_line.rstrip("\r")
            if not line or line.startswith(":"):
                continue
            if line.startswith("event:"):
                event = line[6:].strip() or "message"
            elif line.startswith("id:"):
                event_id = line[3:].strip() or None
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            return event, None, event_id
        data_text = "\n".join(data_lines)
        try:
            data = json.loads(data_text)
        except json.JSONDecodeError:
            data = {"content": data_text}
        return event, data if isinstance(data, dict) else {"value": data}, event_id

    @staticmethod
    def _extract_delta(event: str, data: dict[str, Any] | None) -> str:
        if event not in {"content_delta", "content"} or not data:
            return ""
        value = data.get("content") or data.get("delta") or data.get("text")
        return value if isinstance(value, str) else ""

    @staticmethod
    def _extract_thinking_delta(event: str, data: dict[str, Any] | None) -> str:
        if event not in {"thinking_delta", "thinking"} or not data:
            return ""
        value = data.get("content") or data.get("delta") or data.get("text")
        return value if isinstance(value, str) else ""

    @staticmethod
    def _extract_final_content(data: dict[str, Any] | None, fallback: str) -> str:
        if not data:
            return fallback
        value = data.get("final_content") or data.get("content") or data.get("text")
        return value if isinstance(value, str) and value else fallback

    @staticmethod
    def _external_conversation_id(conversation_public_id: str) -> str:
        return f"opendesk:{conversation_public_id}"

    @staticmethod
    def _compact_tool_metadata_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return (
                value
                if len(value) <= OpenAgentConversationService._MAX_TOOL_METADATA_VALUE_LENGTH
                else f"{value[:OpenAgentConversationService._MAX_TOOL_METADATA_VALUE_LENGTH]}..."
            )
        if isinstance(value, (int, float, bool)):
            return value
        try:
            encoded = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)[:OpenAgentConversationService._MAX_TOOL_METADATA_VALUE_LENGTH]
        if len(encoded) > OpenAgentConversationService._MAX_TOOL_METADATA_VALUE_LENGTH:
            return f"{encoded[:OpenAgentConversationService._MAX_TOOL_METADATA_VALUE_LENGTH]}..."
        return value

    @staticmethod
    def _tool_string(value: Any) -> str:
        return value if isinstance(value, str) else ""

    @staticmethod
    def _tool_int(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _normalize_human_handoff_tool_name(tool_name: str | None) -> str:
        return (tool_name or "").strip().lower()

    @staticmethod
    def _is_human_handoff_tool_name(tool_name: str | None) -> bool:
        return (
            OpenAgentConversationService._normalize_human_handoff_tool_name(tool_name)
            == OpenAgentConversationService._HUMAN_HANDOFF_TOOL_NAME
        )

    @staticmethod
    def _resolve_event_tool_name(
        data: dict[str, Any],
        pending_tool_calls: dict[str, dict[str, Any]] | None = None,
    ) -> str:
        tool_name = (
            OpenAgentConversationService._tool_string(data.get("tool_name"))
            or OpenAgentConversationService._tool_string(data.get("name"))
        )
        if tool_name or not pending_tool_calls:
            return tool_name
        tool_call_id = OpenAgentConversationService._extract_tool_call_id(data)
        if not tool_call_id:
            return tool_name
        pending = pending_tool_calls.get(tool_call_id, {})
        return (
            OpenAgentConversationService._tool_string(pending.get("tool_name"))
            or OpenAgentConversationService._tool_string(pending.get("name"))
        )

    @staticmethod
    def _is_human_handoff_tool_event(
        data: dict[str, Any],
        pending_tool_calls: dict[str, dict[str, Any]] | None = None,
    ) -> bool:
        return OpenAgentConversationService._is_human_handoff_tool_name(
            OpenAgentConversationService._resolve_event_tool_name(data, pending_tool_calls),
        )

    @staticmethod
    def _extract_required_tool_result_action(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        raw_action = data.get("required_action") if isinstance(data.get("required_action"), dict) else data
        if not isinstance(raw_action, dict):
            return None
        if raw_action.get("type") != "submit_tool_result":
            return None
        tool_type = OpenAgentConversationService._tool_string(raw_action.get("tool_type"))
        tool_name = (
            OpenAgentConversationService._tool_string(raw_action.get("tool_name"))
            or OpenAgentConversationService._tool_string(raw_action.get("name"))
        )
        if tool_type and tool_type != OpenAgentConversationService._HUMAN_HANDOFF_TOOL_NAME:
            return None
        if not tool_type and not OpenAgentConversationService._is_human_handoff_tool_name(tool_name):
            return None
        tool_call_id = OpenAgentConversationService._extract_tool_call_id(raw_action)
        if not tool_call_id:
            return None
        return raw_action

    @staticmethod
    def _trim_handoff_field(value: Any, field: str, *, required: bool = False) -> str | None:
        max_length = OpenAgentConversationService._HANDOFF_FIELD_MAX_LENGTHS.get(field)
        if value is None:
            if required:
                return ""
            return None
        if not isinstance(value, str):
            if required:
                return ""
            return None
        trimmed = value.strip()
        if required and not trimmed:
            return ""
        if not trimmed:
            return None
        if max_length is None:
            return trimmed
        return trimmed[:max_length]

    @staticmethod
    def _coerce_handoff_argument_source(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _normalize_handoff_arguments(args: dict[str, Any]) -> dict[str, str]:
        brief = OpenAgentConversationService._trim_handoff_field(args.get("brief"), "brief", required=True) or ""
        reason = OpenAgentConversationService._trim_handoff_field(args.get("reason"), "reason", required=True) or ""
        result: dict[str, str] = {"brief": brief, "reason": reason}

        urgency = OpenAgentConversationService._trim_handoff_field(args.get("urgency"), "urgency")
        if urgency is not None and urgency in {"normal", "high"}:
            result["urgency"] = urgency

        user_message = OpenAgentConversationService._trim_handoff_field(args.get("user_message"), "user_message")
        if user_message is not None:
            result["user_message"] = user_message

        for key in ("agent_id", "agent_group_id", "business_type"):
            value = OpenAgentConversationService._trim_handoff_field(args.get(key), key)
            if value is not None:
                result[key] = value

        return result

    @staticmethod
    def _resolve_handoff_arguments(
        tool_result: dict[str, Any] | None,
        tool_call_arguments: dict[str, Any] | None,
    ) -> dict[str, str]:
        result_args = OpenAgentConversationService._coerce_handoff_argument_source(
            (tool_result or {}).get("result"),
        )
        call_args = tool_call_arguments or {}
        merged = {**call_args, **result_args}
        normalized = OpenAgentConversationService._normalize_handoff_arguments(merged)
        if not normalized.get("brief"):
            normalized["brief"] = OpenAgentConversationService._DEFAULT_HANDOFF_BRIEF
        return normalized

    @staticmethod
    def _build_required_action_handoff_payload(
        action: dict[str, Any],
        pending_tool_calls: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        tool_call_id = OpenAgentConversationService._extract_tool_call_id(action)
        pending_call = pending_tool_calls.get(tool_call_id, {})
        call_arguments = OpenAgentConversationService._coerce_handoff_argument_source(
            pending_call.get("arguments", pending_call.get("args")),
        )
        action_arguments = OpenAgentConversationService._coerce_handoff_argument_source(
            action.get("arguments", action.get("args", action)),
        )
        handoff = OpenAgentConversationService._normalize_handoff_arguments({
            **call_arguments,
            **action_arguments,
        })
        if not handoff.get("brief"):
            handoff["brief"] = OpenAgentConversationService._DEFAULT_HANDOFF_BRIEF
        return OpenAgentConversationService._build_handoff_payload(
            handoff,
            handoff_source="bot_tool",
            tool_call_id=tool_call_id,
            related_tool_call_step_id=OpenAgentConversationService._tool_int(
                action.get("tool_call_step_id", action.get("step_id")),
            ),
        )

    @staticmethod
    def _build_handoff_payload(
        handoff: dict[str, str],
        *,
        handoff_source: str,
        tool_call_id: str | None = None,
        related_tool_call_step_id: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event_kind": "human_handoff",
            "schema_version": 1,
            "handoff_source": handoff_source,
            "handoff": handoff,
        }
        if tool_call_id:
            payload["tool_call_id"] = tool_call_id
        if related_tool_call_step_id is not None:
            payload["related_tool_call_step_id"] = related_tool_call_step_id
        return payload

    @staticmethod
    def _resolve_handoff_event_type(handoff_behavior: str | None) -> str:
        if handoff_behavior == "auto":
            return OpenAgentConversationService._HANDOFF_EVENT_AUTO_TRIGGERED
        return OpenAgentConversationService._HANDOFF_EVENT_CONFIRM_REQUESTED

    @staticmethod
    def _extract_tool_call_id(data: dict[str, Any]) -> str:
        return (
            OpenAgentConversationService._tool_string(data.get("tool_call_id"))
            or OpenAgentConversationService._tool_string(data.get("id"))
        )

    @staticmethod
    def _extract_handoff_payload_tool_call_id(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        value = payload.get("tool_call_id")
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _mark_handoff_tool_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                **block,
                "usedForHandoff": True,
            }
            if OpenAgentConversationService._is_human_handoff_tool_name(
                OpenAgentConversationService._tool_string(block.get("toolName")),
            )
            else block
            for block in blocks
        ]

    @staticmethod
    def _normalize_tool_call(data: dict[str, Any], timeline_index: int) -> dict[str, Any]:
        step_id = OpenAgentConversationService._tool_int(data.get("step_id"))
        tool_name = (
            OpenAgentConversationService._tool_string(data.get("tool_name"))
            or OpenAgentConversationService._tool_string(data.get("name"))
        )
        tool_call_id = (
            OpenAgentConversationService._tool_string(data.get("tool_call_id"))
            or OpenAgentConversationService._tool_string(data.get("id"))
            or (f"step_{step_id}" if step_id is not None else f"tool_{timeline_index}")
        )
        brief = OpenAgentConversationService._tool_string(data.get("brief"))
        if not brief:
            brief = f"调用 {tool_name}" if tool_name else "调用工具"

        block: dict[str, Any] = {
            "id": f"tool_{tool_call_id}",
            "toolName": tool_name,
            "brief": brief,
            "toolCallId": tool_call_id,
            "stepId": step_id,
            "isExecuting": True,
            "timelineIndex": timeline_index,
        }
        arguments = data.get("arguments", data.get("args"))
        if arguments is not None:
            block["arguments"] = OpenAgentConversationService._compact_tool_metadata_value(arguments)
        return block

    @staticmethod
    def _merge_tool_call(
        blocks: list[dict[str, Any]],
        data: dict[str, Any],
        timeline_index: int,
    ) -> list[dict[str, Any]]:
        block = OpenAgentConversationService._normalize_tool_call(data, timeline_index)
        existing_index = next(
            (idx for idx, item in enumerate(blocks) if item.get("toolCallId") == block["toolCallId"]),
            None,
        )
        if existing_index is None:
            return [*blocks, block]

        next_blocks = [*blocks]
        next_blocks[existing_index] = {
            **next_blocks[existing_index],
            **block,
            "timelineIndex": next_blocks[existing_index].get("timelineIndex") or timeline_index,
        }
        return next_blocks

    @staticmethod
    def _merge_tool_result(
        blocks: list[dict[str, Any]],
        data: dict[str, Any],
        timeline_index: int,
    ) -> list[dict[str, Any]]:
        tool_call_id = (
            OpenAgentConversationService._tool_string(data.get("tool_call_id"))
            or OpenAgentConversationService._tool_string(data.get("id"))
            or f"tool_{timeline_index}"
        )
        existing_index = next(
            (idx for idx, item in enumerate(blocks) if item.get("toolCallId") == tool_call_id),
            None,
        )
        result = data.get("result")
        result_value = (
            OpenAgentConversationService._compact_tool_metadata_value(result)
            if result is not None
            else None
        )
        if existing_index is None:
            tool_name = OpenAgentConversationService._tool_string(data.get("tool_name"))
            block: dict[str, Any] = {
                "id": f"tool_{tool_call_id}",
                "toolName": tool_name,
                "brief": f"调用 {tool_name}" if tool_name else "工具调用",
                "toolCallId": tool_call_id,
                "stepId": None,
                "isExecuting": False,
                "timelineIndex": timeline_index,
            }
            if result_value is not None:
                block["result"] = result_value
            return [*blocks, block]

        next_blocks = [*blocks]
        updated = {**next_blocks[existing_index], "isExecuting": False}
        if result_value is not None:
            updated["result"] = result_value
        next_blocks[existing_index] = updated
        return next_blocks

    @staticmethod
    def _finish_tool_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**block, "isExecuting": False} for block in blocks]

    @staticmethod
    def _append_text_block(
        blocks: list[dict[str, Any]],
        content: str,
        timeline_index: int,
    ) -> list[dict[str, Any]]:
        if not content:
            return blocks
        if blocks and blocks[-1].get("isStreaming") is True:
            next_blocks = [*blocks]
            last = next_blocks[-1]
            next_blocks[-1] = {
                **last,
                "content": f"{OpenAgentConversationService._tool_string(last.get('content'))}{content}",
            }
            return next_blocks
        return [
            *blocks,
            {
                "id": f"text_{timeline_index}",
                "content": content,
                "isStreaming": True,
                "timelineIndex": timeline_index,
            },
        ]

    @staticmethod
    def _finish_text_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**block, "isStreaming": False} for block in blocks]

    @staticmethod
    def _text_blocks_content(blocks: list[dict[str, Any]]) -> str:
        return "\n\n".join(
            OpenAgentConversationService._tool_string(block.get("content"))
            for block in blocks
            if OpenAgentConversationService._tool_string(block.get("content"))
        )

    @staticmethod
    def _append_final_text_if_needed(
        blocks: list[dict[str, Any]],
        final_content: str,
        timeline_index: int,
    ) -> tuple[list[dict[str, Any]], int]:
        if not final_content:
            return blocks, timeline_index
        existing_text = "".join(
            OpenAgentConversationService._tool_string(block.get("content"))
            for block in blocks
        )
        if existing_text and existing_text.strip() == final_content.strip():
            return blocks, timeline_index
        content_to_append = (
            final_content[len(existing_text):]
            if existing_text and final_content.startswith(existing_text)
            else final_content
        )
        if not content_to_append:
            return blocks, timeline_index
        if existing_text and not final_content.startswith(existing_text):
            blocks = OpenAgentConversationService._finish_text_blocks(blocks)
        if not blocks or blocks[-1].get("isStreaming") is not True:
            timeline_index += 1
        return (
            OpenAgentConversationService._append_text_block(
                blocks,
                content_to_append,
                timeline_index,
            ),
            timeline_index,
        )

    @staticmethod
    def _append_thinking_block(
        blocks: list[dict[str, Any]],
        content: str,
        timeline_index: int,
        llm_step_id: int | None,
    ) -> list[dict[str, Any]]:
        if not content:
            return blocks
        if blocks and blocks[-1].get("isStreaming") is True:
            next_blocks = [*blocks]
            last = next_blocks[-1]
            next_blocks[-1] = {
                **last,
                "content": f"{OpenAgentConversationService._tool_string(last.get('content'))}{content}",
                "llmStepId": last.get("llmStepId") or llm_step_id,
            }
            return next_blocks
        return [
            *blocks,
            {
                "id": f"think_{timeline_index}",
                "content": content,
                "llmStepId": llm_step_id,
                "isStreaming": True,
                "timelineIndex": timeline_index,
            },
        ]

    @staticmethod
    def _finish_thinking_blocks(
        blocks: list[dict[str, Any]],
        llm_step_id: int | None = None,
    ) -> list[dict[str, Any]]:
        return [
            {
                **block,
                "llmStepId": block.get("llmStepId") or llm_step_id,
                "isStreaming": False,
            }
            for block in blocks
        ]

    @staticmethod
    def _apply_thinking_step_id(
        blocks: list[dict[str, Any]],
        llm_step_id: int | None,
    ) -> list[dict[str, Any]]:
        if llm_step_id is None:
            return blocks
        return [
            {**block, "llmStepId": llm_step_id}
            if block.get("isStreaming") is True
            else block
            for block in blocks
        ]

    @staticmethod
    async def _save_bot_message(
        db: AsyncSession,
        conversation,
        content: str,
        metadata: dict[str, Any],
    ) -> dict:
        bot_name = conversation.open_agent_agent_name or metadata.get("open_agent_agent_name") or "智能助手"
        msg = await MessageRepository.create(db, {
            "tenant_id": conversation.tenant_id,
            "conversation_id": conversation.id,
            "sender_type": MessageSenderType.BOT.value,
            "sender_id": None,
            "content_type": MessageContentType.TEXT.value,
            "content": content,
            "metadata_": {
                **metadata,
                "sender_name": bot_name,
                "open_agent_agent_name": bot_name,
            },
        })
        await ConversationRepository.update_last_message(
            db,
            conversation.id,
            ConversationService.build_message_preview(msg.content_type, msg.content),
            msg.created_at or datetime.now(timezone.utc),
        )
        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        return ConversationService._public_message_payload(msg, conversation)

    @staticmethod
    async def _save_handoff_event(
        db: AsyncSession,
        conversation,
        payload: dict[str, Any],
        *,
        handoff_source: str = "bot_event",
        handoff_event_type: str | None = None,
        tool_call_id: str | None = None,
        processed_tool_call_ids: set[str] | None = None,
    ) -> dict | None:
        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        if not conversation:
            return None
        if getattr(conversation, "agent_id", None) or conversation.status == ConversationStatus.ACTIVE.value:
            return None

        normalized_tool_call_id = (tool_call_id or "").strip() or None
        resolved_event_type = (
            handoff_event_type
            or OpenAgentConversationService._HANDOFF_EVENT_CONFIRM_REQUESTED
        )
        if normalized_tool_call_id and processed_tool_call_ids is not None:
            processed_tool_call_ids.add(normalized_tool_call_id)

        current_state = getattr(conversation, "open_agent_handoff_state", None)
        if current_state in {"requested", "success"}:
            return None

        current_payload = getattr(conversation, "open_agent_handoff_payload", None) or {}
        current_tool_call_id = OpenAgentConversationService._extract_handoff_payload_tool_call_id(
            current_payload,
        )
        if current_state == OpenAgentConversationService._HANDOFF_STATE_DISMISSED:
            if (
                not normalized_tool_call_id
                or not current_tool_call_id
                or normalized_tool_call_id == current_tool_call_id
            ):
                return None

        handoff = payload.get("handoff")
        handoff_dict = handoff if isinstance(handoff, dict) else {}
        brief = str(handoff_dict.get("brief") or "").strip() or OpenAgentConversationService._DEFAULT_HANDOFF_BRIEF
        content = brief

        if current_state == "pending" and normalized_tool_call_id:
            if current_tool_call_id and current_tool_call_id != normalized_tool_call_id:
                return None
            conversation = await ConversationRepository.update_open_agent_state(
                db,
                conversation,
                {"open_agent_handoff_payload": payload},
            )
            return {
                "event": "open_desk_handoff_updated",
                "payload": payload,
                "brief": brief,
                "handoff_event_type": resolved_event_type,
                "conversation_public_id": conversation.public_id,
            }

        if current_state == "pending":
            return None

        conversation, marked_pending = await ConversationRepository.update_handoff_state_if_unassigned(
            db,
            conversation,
            state="pending",
            payload=payload,
            status=ConversationStatus.HANDOFF_PENDING.value,
            allowed_previous_states=(None, "failed", OpenAgentConversationService._HANDOFF_STATE_DISMISSED),
        )
        if (
            not marked_pending
            or getattr(conversation, "agent_id", None)
            or conversation.status == ConversationStatus.ACTIVE.value
        ):
            return None

        msg = await MessageRepository.create(db, {
            "tenant_id": conversation.tenant_id,
            "conversation_id": conversation.id,
            "sender_type": MessageSenderType.SYSTEM.value,
            "content_type": MessageContentType.SYSTEM.value,
            "content": content,
            "metadata_": {
                "event_type": "open_agent_handoff_event",
                "handoff_event_type": resolved_event_type,
                "handoff_source": handoff_source,
                "handoff_payload": payload,
                **({"tool_call_id": normalized_tool_call_id} if normalized_tool_call_id else {}),
            },
        })
        await ConversationRepository.update_last_message(
            db,
            conversation.id,
            content,
            msg.created_at or datetime.now(timezone.utc),
        )
        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        saved = ConversationService._public_message_payload(msg, conversation)
        saved["handoff_event_type"] = resolved_event_type
        return saved

    @staticmethod
    async def _handle_human_handoff_tool_result(
        db: AsyncSession,
        conversation,
        data: dict[str, Any],
        pending_tool_calls: dict[str, dict[str, Any]],
        processed_tool_call_ids: set[str],
        *,
        handoff_behavior: str | None = None,
    ) -> dict | None:
        tool_call_id = OpenAgentConversationService._extract_tool_call_id(data)
        if not tool_call_id:
            return None

        tool_call_data = pending_tool_calls.get(tool_call_id, {})
        call_arguments = OpenAgentConversationService._coerce_handoff_argument_source(
            tool_call_data.get("arguments", tool_call_data.get("args")),
        )
        handoff = OpenAgentConversationService._resolve_handoff_arguments(data, call_arguments)
        payload = OpenAgentConversationService._build_handoff_payload(
            handoff,
            handoff_source="bot_tool",
            tool_call_id=tool_call_id,
            related_tool_call_step_id=OpenAgentConversationService._tool_int(data.get("step_id")),
        )
        return await OpenAgentConversationService._save_handoff_event(
            db,
            conversation,
            payload,
            handoff_source="bot_tool",
            handoff_event_type=OpenAgentConversationService._resolve_handoff_event_type(handoff_behavior),
            tool_call_id=tool_call_id,
            processed_tool_call_ids=processed_tool_call_ids,
        )

    @staticmethod
    async def _handle_human_handoff_event(
        db: AsyncSession,
        conversation,
        data: dict[str, Any],
        processed_tool_call_ids: set[str],
        *,
        handoff_behavior: str | None = None,
    ) -> dict | None:
        related_tool_call_step_id = OpenAgentConversationService._tool_int(data.get("related_tool_call_step_id"))
        tool_call_id = OpenAgentConversationService._tool_string(data.get("tool_call_id"))
        if not tool_call_id and related_tool_call_step_id is not None:
            tool_call_id = f"step_{related_tool_call_step_id}"

        handoff = data.get("handoff")
        if isinstance(handoff, dict):
            normalized_handoff = OpenAgentConversationService._normalize_handoff_arguments(handoff)
            if not normalized_handoff.get("brief"):
                normalized_handoff["brief"] = OpenAgentConversationService._DEFAULT_HANDOFF_BRIEF
            payload = {
                **data,
                "handoff_source": "bot_event",
                "handoff": normalized_handoff,
            }
        else:
            payload = {
                **data,
                "handoff_source": "bot_event",
            }

        return await OpenAgentConversationService._save_handoff_event(
            db,
            conversation,
            payload,
            handoff_source="bot_event",
            handoff_event_type=OpenAgentConversationService._resolve_handoff_event_type(handoff_behavior),
            tool_call_id=tool_call_id or None,
            processed_tool_call_ids=processed_tool_call_ids,
        )

    @staticmethod
    async def _emit_handoff_route_events(
        db: AsyncSession,
        redis,
        conversation,
        visitor_context: dict,
        handoff_payload: dict[str, Any],
    ) -> list[bytes]:
        result = await ConversationService.request_human_handoff_for_session(
            db,
            redis,
            conversation_public_id=conversation.public_id,
            visitor_context=visitor_context,
            handoff_payload=handoff_payload,
            handoff_trigger="bot_auto",
        )
        events: list[bytes] = []
        for route_message in result.get("messages") or []:
            events.append(
                OpenAgentConversationService._sse_event("open_desk_message_saved", route_message),
            )
        if not events:
            route_message = result.get("message")
            if route_message:
                events.append(
                    OpenAgentConversationService._sse_event("open_desk_message_saved", route_message),
                )
        conv = result.get("conversation")
        if conv is not None:
            status_payload = {
                "conversation_public_id": conv.public_id,
                "status": conv.status,
                "ok": result.get("ok", False),
                "reason": result.get("reason"),
            }
            queue_position = result.get("queue_position")
            if queue_position is not None:
                status_payload["queue_position"] = queue_position
            status_payload.update(OpenAgentConversationService._handoff_unavailable_status_fields(result))
            events.append(
                OpenAgentConversationService._sse_event(
                    "open_desk_conversation_status",
                    status_payload,
                ),
            )
        return events

    @staticmethod
    async def _collect_handoff_saved_events(
        db: AsyncSession,
        redis,
        conversation,
        visitor_context: dict,
        saved: dict | None,
    ) -> list[bytes]:
        if not saved:
            return []
        events: list[bytes] = []
        if saved.get("event") == "open_desk_handoff_updated":
            events.append(
                OpenAgentConversationService._sse_event("open_desk_handoff_updated", saved),
            )
            return events

        events.append(
            OpenAgentConversationService._sse_event("open_desk_message_saved", saved),
        )
        if (
            saved.get("handoff_event_type") == OpenAgentConversationService._HANDOFF_EVENT_AUTO_TRIGGERED
            and redis is not None
        ):
            handoff_payload = saved.get("metadata", {}).get("handoff_payload")
            if not isinstance(handoff_payload, dict):
                handoff_payload = saved.get("handoff_payload")
            if isinstance(handoff_payload, dict):
                events.extend(
                    await OpenAgentConversationService._emit_handoff_route_events(
                        db,
                        redis,
                        conversation,
                        visitor_context,
                        handoff_payload,
                    ),
                )
        return events

    @staticmethod
    def _handoff_tool_result_payload(
        tool_call_id: str,
        status: str,
        message: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool_call_id": tool_call_id,
            "status": status,
        }
        if message:
            payload["message"] = message
        return payload

    @staticmethod
    def _non_handoff_tool_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            block
            for block in blocks
            if not OpenAgentConversationService._is_human_handoff_tool_name(
                OpenAgentConversationService._tool_string(block.get("toolName")),
            )
        ]

    @staticmethod
    async def _submit_handoff_tool_result_for_conversation(
        db: AsyncSession,
        conversation,
        visitor_context: dict,
        config: ChannelConfig,
        base_url: str,
        api_key: str,
        client: BaseOpenAgentClient,
        *,
        tool_call_id: str,
        status: str,
        message: str | None,
    ) -> list[bytes]:
        try:
            open_agent_conversation_id = int(conversation.open_agent_conversation_id)
        except (TypeError, ValueError):
            return [
                OpenAgentConversationService._sse_event(
                    "error",
                    {"message": "OpenAgent conversation id is required for tool result"},
                ),
            ]

        events: list[bytes] = []
        payload = OpenAgentConversationService._handoff_tool_result_payload(
            tool_call_id,
            status,
            message,
        )
        buffer = ""
        accumulated_content = ""
        last_event_id = conversation.open_agent_last_event_id
        final_saved = False
        text_blocks: list[dict[str, Any]] = []
        thinking_blocks: list[dict[str, Any]] = []
        tool_blocks: list[dict[str, Any]] = []
        trace_timeline_index = 0
        current_llm_step_id: int | None = None
        processed_handoff_tool_call_ids: set[str] = set()

        try:
            async for chunk in client.stream_tool_result(
                base_url,
                api_key,
                config.open_agent_agent_id,
                open_agent_conversation_id,
                payload,
            ):
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    event, data, event_id = OpenAgentConversationService._parse_sse_frame(frame)
                    if OpenAgentConversationService._is_round_event_id(event_id):
                        last_event_id = event_id

                    delta = OpenAgentConversationService._extract_delta(event, data)
                    if delta:
                        accumulated_content += delta
                        thinking_blocks = OpenAgentConversationService._finish_thinking_blocks(
                            thinking_blocks,
                            current_llm_step_id,
                        )
                        if not text_blocks or text_blocks[-1].get("isStreaming") is not True:
                            trace_timeline_index += 1
                        text_blocks = OpenAgentConversationService._append_text_block(
                            text_blocks,
                            delta,
                            trace_timeline_index,
                        )

                    thinking_delta = OpenAgentConversationService._extract_thinking_delta(event, data)
                    if event == "human_handoff_event" and data:
                        saved = await OpenAgentConversationService._handle_human_handoff_event(
                            db,
                            conversation,
                            data,
                            processed_handoff_tool_call_ids,
                            handoff_behavior=config.open_agent_handoff_behavior,
                        )
                        conversation = await ConversationRepository.get_by_id(db, conversation.id)
                        if saved:
                            events.extend(
                                await OpenAgentConversationService._collect_handoff_saved_events(
                                    db,
                                    None,
                                    conversation,
                                    visitor_context,
                                    saved,
                                ),
                            )
                    elif event == "llm_step_created" and data:
                        current_llm_step_id = OpenAgentConversationService._tool_int(data.get("step_id"))
                        thinking_blocks = OpenAgentConversationService._apply_thinking_step_id(
                            thinking_blocks,
                            current_llm_step_id,
                        )
                    elif thinking_delta:
                        text_blocks = OpenAgentConversationService._finish_text_blocks(text_blocks)
                        if not thinking_blocks or thinking_blocks[-1].get("isStreaming") is not True:
                            trace_timeline_index += 1
                        thinking_blocks = OpenAgentConversationService._append_thinking_block(
                            thinking_blocks,
                            thinking_delta,
                            trace_timeline_index,
                            current_llm_step_id,
                        )
                    elif event == "tool_call" and data:
                        text_blocks = OpenAgentConversationService._finish_text_blocks(text_blocks)
                        thinking_blocks = OpenAgentConversationService._finish_thinking_blocks(
                            thinking_blocks,
                            current_llm_step_id,
                        )
                        trace_timeline_index += 1
                        tool_blocks = OpenAgentConversationService._merge_tool_call(
                            tool_blocks,
                            data,
                            trace_timeline_index,
                        )
                    elif event == "tool_result" and data:
                        text_blocks = OpenAgentConversationService._finish_text_blocks(text_blocks)
                        trace_timeline_index += 1
                        tool_blocks = OpenAgentConversationService._merge_tool_result(
                            tool_blocks,
                            data,
                            trace_timeline_index,
                        )
                    elif event == "assistant_reset":
                        accumulated_content = ""
                        text_blocks = []
                        thinking_blocks = []
                        tool_blocks = []
                        trace_timeline_index = 0
                        current_llm_step_id = None
                    elif event == "done":
                        final_content = OpenAgentConversationService._extract_final_content(data, accumulated_content)
                        text_blocks, trace_timeline_index = (
                            OpenAgentConversationService._append_final_text_if_needed(
                                text_blocks,
                                final_content,
                                trace_timeline_index,
                            )
                        )
                        finished_text_blocks = OpenAgentConversationService._finish_text_blocks(text_blocks)
                        finished_thinking_blocks = OpenAgentConversationService._finish_thinking_blocks(
                            thinking_blocks,
                            current_llm_step_id,
                        )
                        finished_tool_blocks = OpenAgentConversationService._finish_tool_blocks(
                            OpenAgentConversationService._non_handoff_tool_blocks(tool_blocks),
                        )
                        if final_content.strip() or finished_text_blocks or finished_thinking_blocks or finished_tool_blocks:
                            metadata = {
                                "open_agent_tool_result_status": status,
                                "open_agent_tool_call_id": tool_call_id,
                                "open_agent_last_event_id": last_event_id,
                                "open_agent_agent_id": config.open_agent_agent_id,
                                "open_agent_agent_name": config.open_agent_agent_name or conversation.open_agent_agent_name,
                            }
                            if finished_text_blocks:
                                metadata["open_agent_text_blocks"] = finished_text_blocks
                            if finished_thinking_blocks:
                                metadata["open_agent_thinking_blocks"] = finished_thinking_blocks
                            if finished_tool_blocks:
                                metadata["open_agent_tool_blocks"] = finished_tool_blocks
                            saved_content = (
                                OpenAgentConversationService._text_blocks_content(finished_text_blocks)
                                or final_content
                            )
                            saved = await OpenAgentConversationService._save_bot_message(
                                db,
                                conversation,
                                saved_content,
                                metadata,
                            )
                            final_saved = True
                            conversation = await ConversationRepository.get_by_id(db, conversation.id)
                            events.append(
                                OpenAgentConversationService._sse_event("open_desk_message_saved", saved),
                            )
                        await ConversationRepository.update_open_agent_state(db, conversation, {
                            "open_agent_last_event_id": last_event_id,
                        })
        except OpenAgentClientError as exc:
            events.append(OpenAgentConversationService._sse_event("error", {"message": str(exc)}))
            return events

        if not final_saved:
            finished_text_blocks = OpenAgentConversationService._finish_text_blocks(text_blocks)
            finished_thinking_blocks = OpenAgentConversationService._finish_thinking_blocks(
                thinking_blocks,
                current_llm_step_id,
            )
            finished_tool_blocks = OpenAgentConversationService._finish_tool_blocks(
                OpenAgentConversationService._non_handoff_tool_blocks(tool_blocks),
            )
            if accumulated_content.strip() or finished_text_blocks or finished_thinking_blocks or finished_tool_blocks:
                metadata = {
                    "open_agent_tool_result_status": status,
                    "open_agent_tool_call_id": tool_call_id,
                    "open_agent_last_event_id": last_event_id,
                    "open_agent_agent_id": config.open_agent_agent_id,
                    "open_agent_agent_name": config.open_agent_agent_name or conversation.open_agent_agent_name,
                }
                if finished_text_blocks:
                    metadata["open_agent_text_blocks"] = finished_text_blocks
                if finished_thinking_blocks:
                    metadata["open_agent_thinking_blocks"] = finished_thinking_blocks
                if finished_tool_blocks:
                    metadata["open_agent_tool_blocks"] = finished_tool_blocks
                saved = await OpenAgentConversationService._save_bot_message(
                    db,
                    conversation,
                    OpenAgentConversationService._text_blocks_content(finished_text_blocks) or accumulated_content,
                    metadata,
                )
                events.append(OpenAgentConversationService._sse_event("open_desk_message_saved", saved))

        return events

    @staticmethod
    async def submit_handoff_tool_result_for_session(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
        *,
        tool_call_id: str,
        status: str,
        message: str | None = None,
        open_agent_client: BaseOpenAgentClient | None = None,
    ) -> list[bytes]:
        conversation = await ConversationService.get_conversation_for_visitor_session(
            db,
            conversation_public_id=conversation_public_id,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
        )
        if not conversation.channel:
            raise ValidationError("Channel is required")

        config = ChannelConfig.model_validate(conversation.channel.config or {})
        if not config.open_agent_enabled or not config.open_agent_agent_id:
            raise ValidationError("OpenAgent bot is not enabled")

        credentials = await OpenAgentSettingsService.get_credentials(db, conversation.tenant_id)
        if not credentials or not credentials[1]:
            raise ValidationError("OpenAgent settings are required")
        base_url, api_key = credentials
        client = open_agent_client or create_open_agent_client()
        return await OpenAgentConversationService._submit_handoff_tool_result_for_conversation(
            db,
            conversation,
            visitor_context,
            config,
            base_url,
            api_key,
            client,
            tool_call_id=tool_call_id,
            status=status,
            message=message,
        )

    @staticmethod
    def _handoff_unavailable_status_fields(result: dict) -> dict:
        availability = result.get("availability") or {}
        fields: dict = {}
        if result.get("leave_message"):
            fields["leave_message"] = True
            fields["leave_message_prompt"] = availability.get("leave_message_prompt")
        if result.get("queue_full"):
            fields["queue_full"] = True
            fields["queue_full_message"] = availability.get("queue_full_message")
            fields["queue_full_show_leave_message_button"] = availability.get(
                "queue_full_show_leave_message_button",
                True,
            )
            fields["queue_full_leave_message_button_label"] = availability.get(
                "queue_full_leave_message_button_label",
            )
            fields["leave_message_prompt"] = availability.get("leave_message_prompt")
        return fields

    @staticmethod
    def _handoff_route_result_events(result: dict) -> list[bytes]:
        events: list[bytes] = []
        for route_message in result.get("messages") or []:
            events.append(
                OpenAgentConversationService._sse_event("open_desk_message_saved", route_message),
            )
        if not events:
            route_message = result.get("message")
            if route_message:
                events.append(
                    OpenAgentConversationService._sse_event("open_desk_message_saved", route_message),
                )
        conv = result.get("conversation")
        if conv is not None:
            status_payload = {
                "conversation_public_id": conv.public_id,
                "status": conv.status,
                "ok": result.get("ok", False),
                "reason": result.get("reason"),
            }
            queue_position = result.get("queue_position")
            if queue_position is not None:
                status_payload["queue_position"] = queue_position
            status_payload.update(OpenAgentConversationService._handoff_unavailable_status_fields(result))
            events.append(
                OpenAgentConversationService._sse_event(
                    "open_desk_conversation_status",
                    status_payload,
                ),
            )
        return events

    @staticmethod
    def _handoff_tool_result_from_route_result(result: dict) -> tuple[str, str]:
        route_message = result.get("message")
        content = route_message.get("content") if isinstance(route_message, dict) else None
        if result.get("ok"):
            return (
                OpenAgentConversationService._HANDOFF_TOOL_RESULT_SUCCESS,
                content if isinstance(content, str) and content else "已为您转接人工客服",
            )
        return (
            OpenAgentConversationService._HANDOFF_TOOL_RESULT_FAILED,
            content if isinstance(content, str) and content else "当前没有可用客服，请继续由机器人处理。",
        )

    @staticmethod
    async def _handle_required_handoff_action(
        db: AsyncSession,
        redis,
        conversation,
        visitor_context: dict,
        config: ChannelConfig,
        base_url: str,
        api_key: str,
        client: BaseOpenAgentClient,
        action: dict[str, Any],
        pending_tool_calls: dict[str, dict[str, Any]],
    ) -> tuple[Any, list[bytes], bool]:
        tool_call_id = OpenAgentConversationService._extract_tool_call_id(action)
        payload = OpenAgentConversationService._build_required_action_handoff_payload(
            action,
            pending_tool_calls,
        )
        event_type = OpenAgentConversationService._resolve_handoff_event_type(
            config.open_agent_handoff_behavior,
        )
        saved = await OpenAgentConversationService._save_handoff_event(
            db,
            conversation,
            payload,
            handoff_source="bot_tool",
            handoff_event_type=event_type,
            tool_call_id=tool_call_id,
        )
        conversation = await ConversationRepository.get_by_id(db, conversation.id)
        events = await OpenAgentConversationService._collect_handoff_saved_events(
            db,
            None,
            conversation,
            visitor_context,
            saved,
        )
        handoff_triggered = bool(saved and saved.get("event") != "open_desk_handoff_updated")

        if config.open_agent_handoff_behavior != "auto":
            return conversation, events, handoff_triggered

        if not saved:
            return conversation, events, handoff_triggered

        route_result = await ConversationService.request_human_handoff_for_session(
            db,
            redis,
            conversation_public_id=conversation.public_id,
            visitor_context=visitor_context,
            handoff_payload=payload,
            handoff_trigger="bot_auto",
            tool_call_id=tool_call_id,
        )
        events.extend(OpenAgentConversationService._handoff_route_result_events(route_result))
        routed_conversation = route_result.get("conversation") or conversation
        status, message = OpenAgentConversationService._handoff_tool_result_from_route_result(route_result)
        events.extend(
            await OpenAgentConversationService._submit_handoff_tool_result_for_conversation(
                db,
                routed_conversation,
                visitor_context,
                config,
                base_url,
                api_key,
                client,
                tool_call_id=tool_call_id,
                status=status,
                message=message,
            ),
        )
        conversation = await ConversationRepository.get_by_id(db, routed_conversation.id)
        return conversation, events, handoff_triggered

    @staticmethod
    async def stream_chat_for_session(
        db: AsyncSession,
        conversation_public_id: str,
        visitor_context: dict,
        body: OpenAgentChatRequest,
        open_agent_client: BaseOpenAgentClient | None = None,
        redis=None,
    ) -> AsyncIterator[bytes]:
        conversation = await ConversationService.get_conversation_for_visitor_session(
            db,
            conversation_public_id=conversation_public_id,
            tenant_id=visitor_context["tenant_id"],
            channel_id=visitor_context["channel_id"],
            visitor_external_id=visitor_context["visitor_external_id"],
        )
        if conversation.status not in {
            ConversationStatus.BOT.value,
            ConversationStatus.HANDOFF_PENDING.value,
        }:
            raise BusinessError("Conversation is not in bot mode")
        if not conversation.channel:
            raise ValidationError("Channel is required")

        config = ChannelConfig.model_validate(conversation.channel.config or {})
        if not config.open_agent_enabled or not config.open_agent_agent_id:
            raise ValidationError("OpenAgent bot is not enabled")

        credentials = await OpenAgentSettingsService.get_credentials(db, conversation.tenant_id)
        if not credentials or not credentials[1]:
            raise ValidationError("OpenAgent settings are required")
        base_url, api_key = credentials

        client_message_id = body.client_message_id or uuid.uuid4().hex
        existing_message = await MessageRepository.get_by_client_message_id(
            db,
            conversation.tenant_id,
            conversation.id,
            client_message_id,
        )
        if existing_message is None and (not body.resume or body.client_message_id):
            visitor = conversation.visitor
            await ConversationService.send_message(
                db,
                conversation_id=conversation.id,
                sender_type=MessageSenderType.VISITOR.value,
                sender_id=visitor.id if visitor else None,
                content_type=MessageContentType.TEXT.value,
                content=body.message,
                tenant_id=conversation.tenant_id,
                metadata={
                    "client_message_id": client_message_id,
                    "open_agent": True,
                },
            )

        request_id = body.request_id or uuid.uuid4().hex
        resume_last_event_id = body.last_event_id or (
            conversation.open_agent_last_event_id if body.resume else None
        )
        payload = {
            "message": body.message,
            "conversation_id": conversation.open_agent_conversation_id,
            "conversation_external_id": conversation.open_agent_conversation_external_id
            or OpenAgentConversationService._external_conversation_id(conversation.public_id),
            "request_id": request_id,
            "client_message_id": client_message_id,
            "resume": body.resume,
            "last_event_id": resume_last_event_id,
            "customer_context": {
                "external_user_id": visitor_context["visitor_external_id"],
                "display_name": visitor_context.get("visitor_name") or (conversation.visitor.name if conversation.visitor else None),
                "source": "api",
                "metadata": {
                    "opendesk_conversation_id": conversation.public_id,
                    "opendesk_channel_id": conversation.channel_id,
                    **(visitor_context.get("metadata") or {}),
                },
            },
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        open_agent_state = {
            "open_agent_agent_id": config.open_agent_agent_id,
            "open_agent_agent_name": config.open_agent_agent_name or conversation.open_agent_agent_name or "智能助手",
            "open_agent_last_request_id": request_id,
        }
        if not body.resume:
            open_agent_state["open_agent_last_event_id"] = None
        await ConversationRepository.update_open_agent_state(db, conversation, open_agent_state)

        client = open_agent_client or create_open_agent_client()
        accumulated_content = ""
        last_event_id = resume_last_event_id
        final_saved = False
        buffer = ""
        text_blocks: list[dict[str, Any]] = []
        thinking_blocks: list[dict[str, Any]] = []
        tool_blocks: list[dict[str, Any]] = []
        trace_timeline_index = 0
        current_llm_step_id: int | None = None
        pending_tool_calls: dict[str, dict[str, Any]] = {}
        processed_handoff_tool_call_ids: set[str] = set()
        processed_required_handoff_tool_call_ids: set[str] = set()
        handoff_triggered_this_round = False

        try:
            async for chunk in client.stream_chat(base_url, api_key, config.open_agent_agent_id, payload):
                local_events: list[bytes] = []
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    event, data, event_id = OpenAgentConversationService._parse_sse_frame(frame)
                    if OpenAgentConversationService._is_round_event_id(event_id):
                        last_event_id = event_id
                    delta = OpenAgentConversationService._extract_delta(event, data)
                    if delta:
                        accumulated_content += delta
                        thinking_blocks = OpenAgentConversationService._finish_thinking_blocks(
                            thinking_blocks,
                            current_llm_step_id,
                        )
                        if not text_blocks or text_blocks[-1].get("isStreaming") is not True:
                            trace_timeline_index += 1
                        text_blocks = OpenAgentConversationService._append_text_block(
                            text_blocks,
                            delta,
                            trace_timeline_index,
                        )
                    thinking_delta = OpenAgentConversationService._extract_thinking_delta(event, data)

                    if event == "conversation_created" and data:
                        oa_conversation = data.get("conversation_id") or data.get("id")
                        external_id = data.get("external_id") or data.get("conversation_external_id")
                        update_data: dict[str, Any] = {"open_agent_last_event_id": last_event_id}
                        try:
                            if oa_conversation is not None:
                                update_data["open_agent_conversation_id"] = int(oa_conversation)
                        except (TypeError, ValueError):
                            pass
                        if isinstance(external_id, str):
                            update_data["open_agent_conversation_external_id"] = external_id[:128]
                        conversation = await ConversationRepository.update_open_agent_state(
                            db, conversation, update_data
                        )
                    elif event == "requires_action" and data:
                        action = OpenAgentConversationService._extract_required_tool_result_action(data)
                        action_tool_call_id = (
                            OpenAgentConversationService._extract_tool_call_id(action)
                            if action
                            else ""
                        )
                        if action and action_tool_call_id not in processed_required_handoff_tool_call_ids:
                            processed_required_handoff_tool_call_ids.add(action_tool_call_id)
                            conversation, action_events, action_triggered = (
                                await OpenAgentConversationService._handle_required_handoff_action(
                                    db,
                                    redis,
                                    conversation,
                                    visitor_context,
                                    config,
                                    base_url,
                                    api_key,
                                    client,
                                    action,
                                    pending_tool_calls,
                                )
                            )
                            if action_triggered:
                                handoff_triggered_this_round = True
                            local_events.extend(action_events)
                    elif event == "human_handoff_event" and data:
                        saved = await OpenAgentConversationService._handle_human_handoff_event(
                            db,
                            conversation,
                            data,
                            processed_handoff_tool_call_ids,
                            handoff_behavior=config.open_agent_handoff_behavior,
                        )
                        conversation = await ConversationRepository.get_by_id(db, conversation.id)
                        if saved:
                            if saved.get("event") != "open_desk_handoff_updated":
                                handoff_triggered_this_round = True
                            local_events.extend(
                                await OpenAgentConversationService._collect_handoff_saved_events(
                                    db,
                                    redis,
                                    conversation,
                                    visitor_context,
                                    saved,
                                ),
                            )
                    elif event == "llm_step_created" and data:
                        current_llm_step_id = OpenAgentConversationService._tool_int(data.get("step_id"))
                        thinking_blocks = OpenAgentConversationService._apply_thinking_step_id(
                            thinking_blocks,
                            current_llm_step_id,
                        )
                    elif thinking_delta:
                        text_blocks = OpenAgentConversationService._finish_text_blocks(text_blocks)
                        if not thinking_blocks or thinking_blocks[-1].get("isStreaming") is not True:
                            trace_timeline_index += 1
                        thinking_blocks = OpenAgentConversationService._append_thinking_block(
                            thinking_blocks,
                            thinking_delta,
                            trace_timeline_index,
                            current_llm_step_id,
                        )
                    elif event == "tool_call" and data:
                        text_blocks = OpenAgentConversationService._finish_text_blocks(text_blocks)
                        thinking_blocks = OpenAgentConversationService._finish_thinking_blocks(
                            thinking_blocks,
                            current_llm_step_id,
                        )
                        trace_timeline_index += 1
                        tool_call_id = OpenAgentConversationService._extract_tool_call_id(data)
                        if tool_call_id:
                            pending_tool_calls[tool_call_id] = data
                        tool_blocks = OpenAgentConversationService._merge_tool_call(
                            tool_blocks,
                            data,
                            trace_timeline_index,
                        )
                    elif event == "tool_result" and data:
                        text_blocks = OpenAgentConversationService._finish_text_blocks(text_blocks)
                        trace_timeline_index += 1
                        tool_blocks = OpenAgentConversationService._merge_tool_result(
                            tool_blocks,
                            data,
                            trace_timeline_index,
                        )
                        if OpenAgentConversationService._is_human_handoff_tool_event(
                            data,
                            pending_tool_calls,
                        ):
                            saved = await OpenAgentConversationService._handle_human_handoff_tool_result(
                                db,
                                conversation,
                                data,
                                pending_tool_calls,
                                processed_handoff_tool_call_ids,
                                handoff_behavior=config.open_agent_handoff_behavior,
                            )
                            conversation = await ConversationRepository.get_by_id(db, conversation.id)
                            if saved:
                                if saved.get("event") != "open_desk_handoff_updated":
                                    handoff_triggered_this_round = True
                                local_events.extend(
                                    await OpenAgentConversationService._collect_handoff_saved_events(
                                        db,
                                        redis,
                                        conversation,
                                        visitor_context,
                                        saved,
                                    ),
                                )
                    elif event == "assistant_reset":
                        accumulated_content = ""
                        text_blocks = []
                        thinking_blocks = []
                        tool_blocks = []
                        trace_timeline_index = 0
                        current_llm_step_id = None
                        pending_tool_calls = {}
                        processed_handoff_tool_call_ids = set()
                        processed_required_handoff_tool_call_ids = set()
                        handoff_triggered_this_round = False
                    elif event == "done":
                        action = OpenAgentConversationService._extract_required_tool_result_action(data)
                        action_tool_call_id = (
                            OpenAgentConversationService._extract_tool_call_id(action)
                            if action
                            else ""
                        )
                        if action and action_tool_call_id not in processed_required_handoff_tool_call_ids:
                            processed_required_handoff_tool_call_ids.add(action_tool_call_id)
                            conversation, action_events, action_triggered = (
                                await OpenAgentConversationService._handle_required_handoff_action(
                                    db,
                                    redis,
                                    conversation,
                                    visitor_context,
                                    config,
                                    base_url,
                                    api_key,
                                    client,
                                    action,
                                    pending_tool_calls,
                                )
                            )
                            if action_triggered:
                                handoff_triggered_this_round = True
                            local_events.extend(action_events)
                        final_content = OpenAgentConversationService._extract_final_content(data, accumulated_content)
                        text_blocks, trace_timeline_index = (
                            OpenAgentConversationService._append_final_text_if_needed(
                                text_blocks,
                                final_content,
                                trace_timeline_index,
                            )
                        )
                        finished_text_blocks = OpenAgentConversationService._finish_text_blocks(text_blocks)
                        finished_thinking_blocks = OpenAgentConversationService._finish_thinking_blocks(
                            thinking_blocks,
                            current_llm_step_id,
                        )
                        finished_tool_blocks = OpenAgentConversationService._finish_tool_blocks(tool_blocks)
                        if processed_required_handoff_tool_call_ids:
                            finished_tool_blocks = OpenAgentConversationService._non_handoff_tool_blocks(
                                finished_tool_blocks,
                            )
                        if handoff_triggered_this_round:
                            finished_tool_blocks = OpenAgentConversationService._mark_handoff_tool_blocks(
                                finished_tool_blocks,
                            )
                        if (
                            final_content.strip()
                            or finished_text_blocks
                            or finished_thinking_blocks
                            or finished_tool_blocks
                        ):
                            metadata = {
                                "open_agent_request_id": request_id,
                                "client_message_id": client_message_id,
                                "open_agent_conversation_id": conversation.open_agent_conversation_id,
                                "open_agent_last_event_id": last_event_id,
                                "open_agent_agent_id": config.open_agent_agent_id,
                                "open_agent_agent_name": config.open_agent_agent_name or conversation.open_agent_agent_name,
                            }
                            if handoff_triggered_this_round:
                                metadata["bot_message_used_for_handoff"] = True
                            if finished_text_blocks:
                                metadata["open_agent_text_blocks"] = finished_text_blocks
                            if finished_thinking_blocks:
                                metadata["open_agent_thinking_blocks"] = finished_thinking_blocks
                            if finished_tool_blocks:
                                metadata["open_agent_tool_blocks"] = finished_tool_blocks
                            saved_content = (
                                OpenAgentConversationService._text_blocks_content(finished_text_blocks)
                                or final_content
                            )
                            saved = await OpenAgentConversationService._save_bot_message(
                                db,
                                conversation,
                                saved_content,
                                metadata,
                            )
                            final_saved = True
                            conversation = await ConversationRepository.get_by_id(db, conversation.id)
                            local_events.append(
                                OpenAgentConversationService._sse_event("open_desk_message_saved", saved)
                            )
                        await ConversationRepository.update_open_agent_state(db, conversation, {
                            "open_agent_last_event_id": last_event_id,
                        })
                yield chunk
                for local_event in local_events:
                    yield local_event
        except OpenAgentClientError as exc:
            yield OpenAgentConversationService._sse_event("error", {"message": str(exc)})
            return

        if not final_saved:
            finished_text_blocks = OpenAgentConversationService._finish_text_blocks(text_blocks)
            finished_thinking_blocks = OpenAgentConversationService._finish_thinking_blocks(
                thinking_blocks,
                current_llm_step_id,
            )
            finished_tool_blocks = OpenAgentConversationService._finish_tool_blocks(tool_blocks)
            if processed_required_handoff_tool_call_ids:
                finished_tool_blocks = OpenAgentConversationService._non_handoff_tool_blocks(
                    finished_tool_blocks,
                )
            if handoff_triggered_this_round:
                finished_tool_blocks = OpenAgentConversationService._mark_handoff_tool_blocks(
                    finished_tool_blocks,
                )
        if (
            not final_saved
            and (
                accumulated_content.strip()
                or finished_text_blocks
                or finished_thinking_blocks
                or finished_tool_blocks
            )
        ):
            metadata = {
                "open_agent_request_id": request_id,
                "client_message_id": client_message_id,
                "open_agent_last_event_id": last_event_id,
                "open_agent_agent_id": config.open_agent_agent_id,
                "open_agent_agent_name": config.open_agent_agent_name or conversation.open_agent_agent_name,
            }
            if handoff_triggered_this_round:
                metadata["bot_message_used_for_handoff"] = True
            if finished_text_blocks:
                metadata["open_agent_text_blocks"] = finished_text_blocks
            if finished_thinking_blocks:
                metadata["open_agent_thinking_blocks"] = finished_thinking_blocks
            if finished_tool_blocks:
                metadata["open_agent_tool_blocks"] = finished_tool_blocks
            saved_content = (
                OpenAgentConversationService._text_blocks_content(finished_text_blocks)
                or accumulated_content
            )
            saved = await OpenAgentConversationService._save_bot_message(
                db,
                conversation,
                saved_content,
                metadata,
            )
            yield OpenAgentConversationService._sse_event("open_desk_message_saved", saved)
