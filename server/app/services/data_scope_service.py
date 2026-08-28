"""
Data scope helpers for ticket, conversation, queue, and call record queries.
"""
from __future__ import annotations

from sqlalchemy import false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import ForbiddenError
from app.models.call_record import CallRecord
from app.models.call_record_access_scope import CallRecordAccessScope
from app.models.conversation import Conversation
from app.models.offline_message import OfflineMessage
from app.models.ticket import Ticket
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.permission import EffectivePrincipal

SCOPE_ALL = "all"
SCOPE_GROUP = "group"
SCOPE_SELF = "self"

RESOURCE_TICKET = "ticket"
RESOURCE_SESSION_RECORD = "session_record"
RESOURCE_CALL_RECORD = "call_record"
RESOURCE_OFFLINE_MESSAGE = "offline_message"
RESOURCE_PEER_CONVERSATION = "chat.conversation.peer.view"
RESOURCE_CHAT_QUEUE = "chat.queue.view"
RESOURCE_COLLABORATION_INVITE = "chat.conversation.collaboration.invite"


class DataScopeService:
    @staticmethod
    def get_scope(principal: EffectivePrincipal, resource: str) -> str:
        if principal.is_super_admin:
            return SCOPE_ALL
        return principal.data_scopes.get(resource, SCOPE_SELF)

    @staticmethod
    async def get_group_peer_employee_ids(
        db: AsyncSession,
        group_ids: list[int],
    ) -> list[int]:
        if not group_ids:
            return []
        return await EmployeeRepository.get_employee_ids_in_groups(db, group_ids)

    @staticmethod
    def resolve_agent_filter(
        principal: EffectivePrincipal,
        resource: str,
        requested_agent_id: int | None,
        peer_employee_ids: list[int],
    ) -> int | None:
        scope = DataScopeService.get_scope(principal, resource)
        if scope == SCOPE_ALL:
            return requested_agent_id
        if scope == SCOPE_SELF:
            return principal.user_id
        allowed_ids = set(peer_employee_ids) | {principal.user_id}
        if requested_agent_id is None:
            return None
        if requested_agent_id not in allowed_ids:
            raise ForbiddenError("Permission denied")
        return requested_agent_id

    @staticmethod
    def build_ticket_predicate(
        principal: EffectivePrincipal,
        peer_employee_ids: list[int],
    ) -> ColumnElement | None:
        scope = DataScopeService.get_scope(principal, RESOURCE_TICKET)
        if scope == SCOPE_ALL:
            return None
        if scope == SCOPE_SELF:
            return Ticket.agent_id == principal.user_id
        return DataScopeService._build_group_predicate(
            principal,
            peer_employee_ids,
            group_column=Ticket.assignee_group_id,
            agent_column=Ticket.agent_id,
        )

    @staticmethod
    def build_session_record_predicate(
        principal: EffectivePrincipal,
        peer_employee_ids: list[int],
        resource: str = RESOURCE_SESSION_RECORD,
    ) -> ColumnElement | None:
        scope = DataScopeService.get_scope(principal, resource)
        if scope == SCOPE_ALL:
            return None
        if scope == SCOPE_SELF:
            return Conversation.agent_id == principal.user_id
        return DataScopeService._build_group_predicate(
            principal,
            peer_employee_ids,
            group_column=Conversation.group_id,
            agent_column=Conversation.agent_id,
        )

    @staticmethod
    def build_call_record_predicate(
        principal: EffectivePrincipal,
        peer_employee_ids: list[int] | None = None,
    ) -> ColumnElement | None:
        del peer_employee_ids
        scope = DataScopeService.get_scope(principal, RESOURCE_CALL_RECORD)
        if scope == SCOPE_ALL:
            return None
        subject_type = "employee"
        subject_ids = [principal.user_id]
        if scope == SCOPE_GROUP:
            subject_type = "employee_group"
            subject_ids = principal.group_ids
        if not subject_ids:
            return false()
        return (
            select(CallRecordAccessScope.id)
            .where(
                CallRecordAccessScope.tenant_id == principal.tenant_id,
                CallRecordAccessScope.call_record_id == CallRecord.id,
                CallRecordAccessScope.subject_type == subject_type,
                CallRecordAccessScope.subject_id.in_(subject_ids),
            )
            .exists()
        )

    @staticmethod
    def build_offline_message_predicate(
        principal: EffectivePrincipal,
        peer_employee_ids: list[int],
    ) -> ColumnElement | None:
        scope = DataScopeService.get_scope(principal, RESOURCE_OFFLINE_MESSAGE)
        if scope == SCOPE_ALL:
            return None
        if scope == SCOPE_SELF:
            clauses: list[ColumnElement] = [OfflineMessage.handled_by_id == principal.user_id]
            if principal.group_ids:
                clauses.append(OfflineMessage.target_group_id.in_(principal.group_ids))
            return or_(*clauses)
        return DataScopeService._build_group_predicate(
            principal,
            peer_employee_ids,
            group_column=OfflineMessage.target_group_id,
            agent_column=OfflineMessage.handled_by_id,
        )

    @staticmethod
    def _build_group_predicate(
        principal: EffectivePrincipal,
        peer_employee_ids: list[int],
        *,
        group_column,
        agent_column,
    ) -> ColumnElement:
        clauses: list[ColumnElement] = []
        if principal.group_ids:
            clauses.append(group_column.in_(principal.group_ids))
        allowed_agent_ids = sorted(set(peer_employee_ids) | {principal.user_id})
        if allowed_agent_ids:
            clauses.append(agent_column.in_(allowed_agent_ids))
        if not clauses:
            return agent_column == principal.user_id
        return or_(*clauses)

    @staticmethod
    def ticket_in_scope(
        principal: EffectivePrincipal,
        ticket: Ticket,
        peer_employee_ids: list[int],
    ) -> bool:
        scope = DataScopeService.get_scope(principal, RESOURCE_TICKET)
        if scope == SCOPE_ALL:
            return True
        if scope == SCOPE_SELF:
            return ticket.agent_id == principal.user_id
        return DataScopeService._row_in_group_scope(
            principal,
            peer_employee_ids,
            group_id=ticket.assignee_group_id,
            agent_id=ticket.agent_id,
        )

    @staticmethod
    def conversation_in_scope(
        principal: EffectivePrincipal,
        conversation: Conversation,
        peer_employee_ids: list[int],
        resource: str = RESOURCE_SESSION_RECORD,
    ) -> bool:
        scope = DataScopeService.get_scope(principal, resource)
        if scope == SCOPE_ALL:
            return True
        if scope == SCOPE_SELF:
            return conversation.agent_id == principal.user_id
        return DataScopeService._row_in_group_scope(
            principal,
            peer_employee_ids,
            group_id=conversation.group_id,
            agent_id=conversation.agent_id,
        )

    @staticmethod
    async def call_record_in_scope(
        db: AsyncSession,
        principal: EffectivePrincipal,
        row: CallRecord,
    ) -> bool:
        scope = DataScopeService.get_scope(principal, RESOURCE_CALL_RECORD)
        if scope == SCOPE_ALL:
            return True
        subject_type = "employee" if scope == SCOPE_SELF else "employee_group"
        subject_ids = [principal.user_id] if scope == SCOPE_SELF else principal.group_ids
        if not subject_ids:
            return False
        query = select(CallRecordAccessScope.id).where(
            CallRecordAccessScope.tenant_id == principal.tenant_id,
            CallRecordAccessScope.call_record_id == row.id,
            CallRecordAccessScope.subject_type == subject_type,
            CallRecordAccessScope.subject_id.in_(subject_ids),
        )
        return (await db.execute(query.limit(1))).scalar_one_or_none() is not None

    @staticmethod
    async def call_record_ids_in_scope(
        db: AsyncSession,
        principal: EffectivePrincipal,
        call_record_ids: list[int],
    ) -> set[int]:
        """Batch variant of call_record_in_scope: return the subset visible to the principal."""
        ids = sorted({call_record_id for call_record_id in call_record_ids if call_record_id is not None})
        if not ids:
            return set()
        scope = DataScopeService.get_scope(principal, RESOURCE_CALL_RECORD)
        if scope == SCOPE_ALL:
            return set(ids)
        subject_type = "employee" if scope == SCOPE_SELF else "employee_group"
        subject_ids = [principal.user_id] if scope == SCOPE_SELF else principal.group_ids
        if not subject_ids:
            return set()
        result = await db.execute(
            select(CallRecordAccessScope.call_record_id)
            .where(
                CallRecordAccessScope.tenant_id == principal.tenant_id,
                CallRecordAccessScope.call_record_id.in_(ids),
                CallRecordAccessScope.subject_type == subject_type,
                CallRecordAccessScope.subject_id.in_(subject_ids),
            )
            .distinct()
        )
        return {row[0] for row in result}

    @staticmethod
    def offline_message_in_scope(
        principal: EffectivePrincipal,
        row: OfflineMessage,
        peer_employee_ids: list[int],
    ) -> bool:
        scope = DataScopeService.get_scope(principal, RESOURCE_OFFLINE_MESSAGE)
        if scope == SCOPE_ALL:
            return True
        if scope == SCOPE_SELF:
            if row.handled_by_id == principal.user_id:
                return True
            return row.status == "pending" and row.target_group_id in principal.group_ids
        return DataScopeService._row_in_group_scope(
            principal,
            peer_employee_ids,
            group_id=row.target_group_id,
            agent_id=row.handled_by_id,
        )

    @staticmethod
    def _row_in_group_scope(
        principal: EffectivePrincipal,
        peer_employee_ids: list[int],
        *,
        group_id: int | None,
        agent_id: int | None,
    ) -> bool:
        if group_id is not None and group_id in principal.group_ids:
            return True
        allowed_agent_ids = set(peer_employee_ids) | {principal.user_id}
        return agent_id is not None and agent_id in allowed_agent_ids

    @staticmethod
    def assert_ticket_in_scope(
        principal: EffectivePrincipal,
        ticket: Ticket,
        peer_employee_ids: list[int],
    ) -> None:
        if not DataScopeService.ticket_in_scope(principal, ticket, peer_employee_ids):
            raise ForbiddenError("Permission denied")

    @staticmethod
    def assert_conversation_in_scope(
        principal: EffectivePrincipal,
        conversation: Conversation,
        peer_employee_ids: list[int],
        resource: str = RESOURCE_SESSION_RECORD,
    ) -> None:
        if not DataScopeService.conversation_in_scope(principal, conversation, peer_employee_ids, resource):
            raise ForbiddenError("Permission denied")

    @staticmethod
    async def assert_call_record_in_scope(
        db: AsyncSession,
        principal: EffectivePrincipal,
        row: CallRecord,
    ) -> None:
        if not await DataScopeService.call_record_in_scope(db, principal, row):
            raise ForbiddenError("Permission denied")

    @staticmethod
    def assert_offline_message_in_scope(
        principal: EffectivePrincipal,
        row: OfflineMessage,
        peer_employee_ids: list[int],
    ) -> None:
        if not DataScopeService.offline_message_in_scope(principal, row, peer_employee_ids):
            raise ForbiddenError("Permission denied")

    @staticmethod
    def empty_result_predicate() -> ColumnElement:
        return false()

    @staticmethod
    async def session_history_filters(
        db: AsyncSession,
        principal: EffectivePrincipal,
    ) -> tuple[int | None, ColumnElement | None]:
        """Return visitor-history filters as (agent_id, scope_predicate)."""
        scope = DataScopeService.get_scope(principal, RESOURCE_SESSION_RECORD)
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        if scope == SCOPE_ALL:
            return None, None
        if scope == SCOPE_SELF:
            return principal.user_id, None
        return None, DataScopeService.build_session_record_predicate(principal, peer_ids)

    @staticmethod
    async def assert_conversation_access(
        db: AsyncSession,
        principal: EffectivePrincipal,
        conversation: Conversation,
    ) -> None:
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        DataScopeService.assert_conversation_in_scope(principal, conversation, peer_ids)

    @staticmethod
    async def can_access_conversation(
        db: AsyncSession,
        principal: EffectivePrincipal,
        conversation: Conversation,
    ) -> bool:
        peer_ids = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        return DataScopeService.conversation_in_scope(principal, conversation, peer_ids)
