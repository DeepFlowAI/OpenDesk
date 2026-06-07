"""
Unit tests for data scope helpers.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.exceptions import ForbiddenError
from app.models.call_record import CallRecord
from app.models.conversation import Conversation
from app.models.ticket import Ticket
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService, RESOURCE_TICKET


def _principal(**overrides) -> EffectivePrincipal:
    base = {
        "user_id": 10,
        "tenant_id": 1,
        "is_super_admin": False,
        "role_ids": [1],
        "legacy_roles": ["agent"],
        "permissions": ["ticket.workspace.view"],
        "data_scopes": {"ticket": "self", "session_record": "self", "call_record": "self"},
        "group_ids": [100],
    }
    base.update(overrides)
    return EffectivePrincipal(**base)


class TestDataScopeService:
    def test_get_scope_super_admin_is_all(self):
        principal = _principal(is_super_admin=True, data_scopes={})
        assert DataScopeService.get_scope(principal, RESOURCE_TICKET) == "all"

    def test_ticket_self_predicate(self):
        principal = _principal(data_scopes={"ticket": "self"})
        predicate = DataScopeService.build_ticket_predicate(principal, [])
        assert predicate is not None
        ticket = MagicMock(spec=Ticket)
        ticket.agent_id = 10
        assert DataScopeService.ticket_in_scope(principal, ticket, []) is True
        ticket.agent_id = 99
        assert DataScopeService.ticket_in_scope(principal, ticket, []) is False

    def test_ticket_group_matches_assignee_group(self):
        principal = _principal(data_scopes={"ticket": "group"}, group_ids=[100])
        ticket = MagicMock(spec=Ticket)
        ticket.agent_id = 99
        ticket.assignee_group_id = 100
        assert DataScopeService.ticket_in_scope(principal, ticket, []) is True

    def test_ticket_group_matches_peer_agent(self):
        principal = _principal(data_scopes={"ticket": "group"}, group_ids=[100])
        ticket = MagicMock(spec=Ticket)
        ticket.agent_id = 20
        ticket.assignee_group_id = None
        assert DataScopeService.ticket_in_scope(principal, ticket, [20, 30]) is True

    def test_conversation_group_matches_group_id(self):
        principal = _principal(data_scopes={"session_record": "group"}, group_ids=[100])
        conversation = MagicMock(spec=Conversation)
        conversation.agent_id = 99
        conversation.group_id = 100
        assert DataScopeService.conversation_in_scope(principal, conversation, []) is True

    def test_call_record_self_scope(self):
        principal = _principal(data_scopes={"call_record": "self"})
        row = MagicMock(spec=CallRecord)
        row.agent_id = 10
        row.employee_group_id = None
        assert DataScopeService.call_record_in_scope(principal, row, []) is True
        row.agent_id = 11
        assert DataScopeService.call_record_in_scope(principal, row, []) is False

    def test_resolve_agent_filter_self_forces_current_user(self):
        principal = _principal(data_scopes={"session_record": "self"})
        assert DataScopeService.resolve_agent_filter(principal, "session_record", 99, []) == 10

    def test_resolve_agent_filter_group_rejects_foreign_agent(self):
        principal = _principal(data_scopes={"session_record": "group"}, group_ids=[100])
        with pytest.raises(ForbiddenError):
            DataScopeService.resolve_agent_filter(principal, "session_record", 99, [20])

    @pytest.mark.asyncio
    async def test_get_group_peer_employee_ids(self):
        db = AsyncMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.services.data_scope_service.EmployeeRepository.get_employee_ids_in_groups",
                AsyncMock(return_value=[20, 30]),
            )
            peer_ids = await DataScopeService.get_group_peer_employee_ids(db, [100])
        assert peer_ids == [20, 30]
