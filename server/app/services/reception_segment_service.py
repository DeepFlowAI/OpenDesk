"""
Reception segment generation service.

After a conversation ends, generates the conversation's reception segments in
bulk from the structured reception events plus the message timeline, materializes
per-segment metrics, self-validates, and writes the conversation-level aggregate
columns. Idempotent: re-running replaces the existing segments.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ConversationStatus, MessageSenderType
from app.libs.conversation_metrics import (
    compute_agent_response_metrics,
    compute_duration_seconds,
    compute_first_human_response_seconds,
)
from app.libs.reception_segments import (
    ReceptionEventInput,
    SegmentDraft,
    build_segment_drafts,
    opening_event_count,
    windows_non_overlapping,
)
from app.models.conversation import Conversation
from app.models.employee import Employee
from app.models.employee_group import EmployeeGroup
from app.models.message import Message
from app.repositories.reception_event_repository import ReceptionEventRepository
from app.repositories.reception_segment_repository import ReceptionSegmentRepository

logger = logging.getLogger(__name__)

# Public message caliber, identical to the conversation-level first-response /
# response-metric SQL: visitor/agent text-like messages only.
_PUBLIC_CONTENT_TYPES = ("text", "rich_text", "image", "file")

GENERATION_STATUS_GENERATED = "generated"
GENERATION_STATUS_FAILED = "failed"


class _PublicMessage:
    __slots__ = ("sender_type", "sender_id", "created_at")

    def __init__(self, sender_type: str, sender_id: int | None, created_at):
        self.sender_type = sender_type
        self.sender_id = sender_id
        self.created_at = created_at


class ReceptionSegmentService:

    @staticmethod
    async def generate_for_conversation(db: AsyncSession, conversation_id: int) -> None:
        """Generate and persist reception segments for an ended conversation.

        Safe to call after the conversation-close commit. Never raises: any
        failure is logged and recorded as a ``failed`` generation status so the
        conversation can be regenerated later.
        """
        try:
            await ReceptionSegmentService._generate(db, conversation_id)
        except Exception:
            logger.exception(
                "Failed to generate reception segments for conversation %s",
                conversation_id,
            )
            await ReceptionSegmentService._mark_failed(db, conversation_id)

    @staticmethod
    async def _generate(db: AsyncSession, conversation_id: int) -> None:
        conversation = await db.get(Conversation, conversation_id)
        if conversation is None:
            return
        # In-progress conversations are not materialized (segments only serve
        # history and reports).
        if conversation.status != ConversationStatus.CLOSED.value:
            return

        tenant_id = conversation.tenant_id
        events = await ReceptionEventRepository.list_for_conversation(db, conversation_id)
        event_inputs = [
            ReceptionEventInput(
                event_type=ev.event_type,
                reason=ev.reason,
                occurred_at=ev.occurred_at,
                agent_id=ev.agent_id,
                group_id=ev.group_id,
                from_agent_id=ev.from_agent_id,
                to_agent_id=ev.to_agent_id,
            )
            for ev in events
        ]
        drafts = build_segment_drafts(event_inputs, conversation.ended_at)

        # No human reception: clear any stale segments and zero the aggregates.
        if not drafts:
            await ReceptionSegmentRepository.replace_for_conversation(
                db, tenant_id, conversation_id, []
            )
            ReceptionSegmentService._apply_conversation_aggregates(
                conversation, [], {}, status=GENERATION_STATUS_GENERATED
            )
            await db.commit()
            return

        public_messages = await ReceptionSegmentService._load_public_messages(db, conversation_id)
        name_snapshots = await ReceptionSegmentService._load_agent_names(db, tenant_id, drafts)
        group_snapshots = await ReceptionSegmentService._load_group_names(db, tenant_id, drafts)

        rows = ReceptionSegmentService._build_rows(
            conversation,
            drafts,
            public_messages,
            name_snapshots,
            group_snapshots,
        )

        # Self-validation: segment count matches opening events and windows do
        # not overlap. A failure still persists the rows but flags the status so
        # the conversation can be regenerated.
        valid = (
            len(drafts) == opening_event_count(event_inputs)
            and windows_non_overlapping(drafts)
        )
        status = GENERATION_STATUS_GENERATED if valid else GENERATION_STATUS_FAILED

        await ReceptionSegmentRepository.replace_for_conversation(
            db, tenant_id, conversation_id, rows
        )
        ReceptionSegmentService._apply_conversation_aggregates(
            conversation, drafts, name_snapshots, status=status
        )
        await db.commit()

    @staticmethod
    async def _load_public_messages(
        db: AsyncSession, conversation_id: int
    ) -> list[_PublicMessage]:
        result = await db.execute(
            select(Message.sender_type, Message.sender_id, Message.created_at)
            .where(
                Message.conversation_id == conversation_id,
                Message.sender_type.in_(
                    [MessageSenderType.VISITOR.value, MessageSenderType.AGENT.value]
                ),
                Message.content_type.in_(_PUBLIC_CONTENT_TYPES),
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return [_PublicMessage(row[0], row[1], row[2]) for row in result.all()]

    @staticmethod
    async def _load_agent_names(
        db: AsyncSession, tenant_id: int, drafts: list[SegmentDraft]
    ) -> dict[int, str]:
        agent_ids = {d.agent_id for d in drafts if d.agent_id is not None}
        if not agent_ids:
            return {}
        result = await db.execute(
            select(Employee.id, Employee.name, Employee.username).where(
                Employee.tenant_id == tenant_id,
                Employee.id.in_(agent_ids),
            )
        )
        return {row[0]: (row[1] or row[2]) for row in result.all()}

    @staticmethod
    async def _load_group_names(
        db: AsyncSession, tenant_id: int, drafts: list[SegmentDraft]
    ) -> dict[int, str]:
        group_ids = {d.group_id for d in drafts if d.group_id is not None}
        if not group_ids:
            return {}
        result = await db.execute(
            select(EmployeeGroup.id, EmployeeGroup.name).where(
                EmployeeGroup.tenant_id == tenant_id,
                EmployeeGroup.id.in_(group_ids),
            )
        )
        return {row[0]: row[1] for row in result.all()}

    @staticmethod
    def _build_rows(
        conversation: Conversation,
        drafts: list[SegmentDraft],
        public_messages: list[_PublicMessage],
        name_snapshots: dict[int, str],
        group_snapshots: dict[int, str],
    ) -> list[dict]:
        rows: list[dict] = []
        for draft in drafts:
            window = ReceptionSegmentService._messages_in_window(
                public_messages, draft.started_at, draft.ended_at
            )
            visitor_count = sum(
                1 for m in window if m.sender_type == MessageSenderType.VISITOR.value
            )
            agent_count = sum(
                1
                for m in window
                if m.sender_type == MessageSenderType.AGENT.value
                and m.sender_id == draft.agent_id
            )
            _, avg_response = compute_agent_response_metrics(
                [(m.sender_type, m.created_at) for m in window]
            )
            # Only the first segment may carry a segment-local first response.
            # If the first owner transferred before replying, the conversation
            # can still have a first response while this segment stays empty.
            first_response = (
                ReceptionSegmentService._first_response_seconds_in_window(
                    window,
                    draft.agent_id,
                )
                if draft.seq_no == 1
                else None
            )
            rows.append(
                {
                    "tenant_id": conversation.tenant_id,
                    "conversation_id": conversation.id,
                    "seq_no": draft.seq_no,
                    "agent_id": draft.agent_id,
                    "agent_name_snapshot": name_snapshots.get(draft.agent_id),
                    "group_id": draft.group_id,
                    "group_name_snapshot": group_snapshots.get(draft.group_id),
                    "started_at": draft.started_at,
                    "ended_at": draft.ended_at,
                    "duration_seconds": compute_duration_seconds(
                        draft.started_at, draft.ended_at
                    ),
                    "entry_reason": draft.entry_reason,
                    "end_reason": draft.end_reason,
                    "from_agent_id": draft.from_agent_id,
                    "to_agent_id": draft.to_agent_id,
                    "visitor_message_count": visitor_count,
                    "agent_message_count": agent_count,
                    "first_response_seconds": first_response,
                    "avg_response_seconds": avg_response,
                    "conversation_started_at": conversation.started_at,
                }
            )
        return rows

    @staticmethod
    def _messages_in_window(
        public_messages: list[_PublicMessage], started_at, ended_at
    ) -> list[_PublicMessage]:
        """Public messages in ``[started_at, ended_at)`` (open end excludes it)."""
        result = []
        for m in public_messages:
            if m.created_at < started_at:
                continue
            if ended_at is not None and m.created_at >= ended_at:
                continue
            result.append(m)
        return result

    @staticmethod
    def _first_response_seconds_in_window(
        public_messages: list[_PublicMessage],
        agent_id: int | None,
    ) -> int | None:
        if agent_id is None:
            return None

        pending_visitor_at = None
        for message in public_messages:
            if message.sender_type == MessageSenderType.VISITOR.value:
                pending_visitor_at = message.created_at
                continue
            if (
                message.sender_type == MessageSenderType.AGENT.value
                and message.sender_id == agent_id
                and pending_visitor_at is not None
            ):
                return compute_first_human_response_seconds(
                    pending_visitor_at,
                    message.created_at,
                )
        return None

    @staticmethod
    def _apply_conversation_aggregates(
        conversation: Conversation,
        drafts: list[SegmentDraft],
        name_snapshots: dict[int, str],
        *,
        status: str,
    ) -> None:
        conversation.reception_segment_count = len(drafts)
        # Ownership changes after the first segment (transfers + reassigns).
        conversation.reception_transfer_count = max(0, len(drafts) - 1)
        conversation.reception_final_agent_id = drafts[-1].agent_id if drafts else None
        conversation.reception_participants = ReceptionSegmentService._participants(
            drafts, name_snapshots
        )
        conversation.reception_generation_status = status

    @staticmethod
    def _participants(
        drafts: list[SegmentDraft], name_snapshots: dict[int, str]
    ) -> list[dict]:
        """Ordered unique participating agents (by first appearance) with names."""
        seen: set[int] = set()
        participants: list[dict] = []
        for draft in drafts:
            if draft.agent_id is None or draft.agent_id in seen:
                continue
            seen.add(draft.agent_id)
            participants.append(
                {"agent_id": draft.agent_id, "name": name_snapshots.get(draft.agent_id)}
            )
        return participants

    @staticmethod
    async def _mark_failed(db: AsyncSession, conversation_id: int) -> None:
        try:
            await db.rollback()
            conversation = await db.get(Conversation, conversation_id)
            if conversation is not None:
                conversation.reception_generation_status = GENERATION_STATUS_FAILED
                await db.commit()
        except Exception:
            logger.exception(
                "Failed to mark reception generation failed for conversation %s",
                conversation_id,
            )
