"""
Unit tests for ticket service.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.schemas.ticket import TicketCreate
from app.services.ticket_service import TicketService


class TestTicketService:

    @pytest.mark.asyncio
    async def test_create_ticket_with_conversation_id_persists_link(self):
        mock_db = AsyncMock()
        payload = TicketCreate(
            title="Need help",
            conversation_id=123,
            custom_fields={},
        )

        with (
            patch.object(TicketService, "_get_key_to_slot_map", AsyncMock(return_value={})),
            patch.object(TicketService, "_get_field_key_slot_map", AsyncMock(return_value={})),
            patch.object(TicketService, "_validate_conversation", AsyncMock()) as validate_conversation,
            patch.object(TicketService, "_enrich_response", return_value={"id": 1, "conversation_id": 123}),
            patch(
                "app.services.ticket_service.TicketWorkflowExecutionService.apply",
                AsyncMock(return_value=SimpleNamespace(updates={}, field_labels={})),
            ),
            patch("app.services.ticket_service.TicketRepository") as ticket_repo,
        ):
            ticket_repo.create = AsyncMock(return_value=SimpleNamespace(id=1))

            result = await TicketService.create_ticket(mock_db, 10, payload)

            validate_conversation.assert_awaited_once_with(mock_db, 10, 123)
            ticket_repo.create.assert_awaited_once()
            created_data = ticket_repo.create.await_args.args[1]
            assert created_data["conversation_id"] == 123
            assert result["conversation_id"] == 123

    @pytest.mark.asyncio
    async def test_create_ticket_with_call_record_id_persists_link(self):
        mock_db = AsyncMock()
        payload = TicketCreate(
            title="Need help",
            call_record_id=456,
            custom_fields={},
        )

        with (
            patch.object(TicketService, "_get_key_to_slot_map", AsyncMock(return_value={})),
            patch.object(TicketService, "_get_field_key_slot_map", AsyncMock(return_value={})),
            patch.object(TicketService, "_validate_call_record", AsyncMock()) as validate_call_record,
            patch.object(TicketService, "_get_call_record_call_id_map", AsyncMock(return_value={456: "call-456"})),
            patch.object(TicketService, "_enrich_response", return_value={"id": 1, "call_record_id": 456}),
            patch(
                "app.services.ticket_service.TicketWorkflowExecutionService.apply",
                AsyncMock(return_value=SimpleNamespace(updates={}, field_labels={})),
            ),
            patch("app.services.ticket_service.TicketRepository") as ticket_repo,
            patch("app.services.ticket_service.TicketChangeRepository") as ticket_change_repo,
        ):
            ticket_repo.create = AsyncMock(return_value=SimpleNamespace(id=1, call_record_id=456, conversation_id=None))
            ticket_change_repo.create_many = AsyncMock()

            result = await TicketService.create_ticket(mock_db, 10, payload)

            validate_call_record.assert_awaited_once_with(mock_db, 10, 456)
            ticket_repo.create.assert_awaited_once()
            created_data = ticket_repo.create.await_args.args[1]
            assert created_data["call_record_id"] == 456
            assert result["call_record_id"] == 456

    @pytest.mark.asyncio
    async def test_validate_conversation_not_found_raises_error(self):
        mock_db = AsyncMock()

        with patch("app.services.ticket_service.ConversationRepository") as conversation_repo:
            conversation_repo.get_by_id = AsyncMock(return_value=None)

            with pytest.raises(NotFoundError):
                await TicketService._validate_conversation(mock_db, 10, 999)

    @pytest.mark.asyncio
    async def test_validate_conversation_cross_tenant_raises_error(self):
        mock_db = AsyncMock()
        conversation = SimpleNamespace(id=123, tenant_id=20)

        with patch("app.services.ticket_service.ConversationRepository") as conversation_repo:
            conversation_repo.get_by_id = AsyncMock(return_value=conversation)

            with pytest.raises(NotFoundError):
                await TicketService._validate_conversation(mock_db, 10, 123)

    @pytest.mark.asyncio
    async def test_validate_call_record_not_found_raises_error(self):
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        with pytest.raises(NotFoundError):
            await TicketService._validate_call_record(mock_db, 10, 999)

    @pytest.mark.asyncio
    async def test_validate_call_record_cross_tenant_raises_error(self):
        mock_db = AsyncMock()
        call_record = SimpleNamespace(id=456, tenant_id=20)
        mock_db.get = AsyncMock(return_value=call_record)

        with pytest.raises(NotFoundError):
            await TicketService._validate_call_record(mock_db, 10, 456)

    @pytest.mark.asyncio
    async def test_validate_assignee_values_allows_matching_group_member(self):
        mock_db = AsyncMock()
        group = SimpleNamespace(id=2, tenant_id=10)
        employee = SimpleNamespace(id=3, tenant_id=10, is_active=True)

        with (
            patch("app.services.ticket_service.EmployeeGroupRepository") as group_repo,
            patch("app.services.ticket_service.EmployeeRepository") as employee_repo,
        ):
            group_repo.get_by_id = AsyncMock(return_value=group)
            group_repo.has_member = AsyncMock(return_value=True)
            employee_repo.get_by_id = AsyncMock(return_value=employee)

            await TicketService._validate_assignee_values(mock_db, 10, 2, 3)

            group_repo.has_member.assert_awaited_once_with(mock_db, 2, 3)

    @pytest.mark.asyncio
    async def test_validate_assignee_values_rejects_mismatched_group_member(self):
        mock_db = AsyncMock()
        group = SimpleNamespace(id=2, tenant_id=10)
        employee = SimpleNamespace(id=3, tenant_id=10, is_active=True)

        with (
            patch("app.services.ticket_service.EmployeeGroupRepository") as group_repo,
            patch("app.services.ticket_service.EmployeeRepository") as employee_repo,
        ):
            group_repo.get_by_id = AsyncMock(return_value=group)
            group_repo.has_member = AsyncMock(return_value=False)
            employee_repo.get_by_id = AsyncMock(return_value=employee)

            with pytest.raises(ValidationError):
                await TicketService._validate_assignee_values(mock_db, 10, 2, 3)

    def test_apply_system_field_aliases_respects_explicit_agent_id(self):
        target = {"agent_id": 9}
        changed_fields = ["agent_id"]

        TicketService._apply_system_field_aliases(
            target,
            {"assignee": 3, "assignee_group": 2},
            {"agent_id"},
            changed_fields,
        )

        assert target["agent_id"] == 9
        assert target["assignee_group_id"] == 2
        assert changed_fields == ["agent_id", "assignee_group_id"]
