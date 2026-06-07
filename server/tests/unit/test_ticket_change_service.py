"""
Unit tests for ticket change diff generation.
"""
from decimal import Decimal

from app.models.ticket import Ticket
from app.services.ticket_service import (
    TicketService,
    TICKET_CHANGE_BATCH_FIELD_KEY,
    TICKET_CHANGE_CREATE_FIELD_KEY,
)


class TestTicketChangeDiff:

    def test_build_change_rows_includes_only_changed_fields(self):
        ticket = Ticket(
            id=42,
            tenant_id=7,
            title="Old title",
            status="open",
            priority="medium",
        )

        rows = TicketService._build_change_rows(
            ticket=ticket,
            tenant_id=7,
            update_data={"title": "New title", "status": "open"},
            field_labels={"title": "标题", "status": "状态"},
            actor_id=9,
            actor_name="Test Actor",
        )

        assert len(rows) == 1
        assert rows[0]["field_key"] == "title"
        assert rows[0]["field_label"] == "标题"
        assert rows[0]["field_source"] == "ticket"
        assert rows[0]["old_value"] == "Old title"
        assert rows[0]["new_value"] == "New title"
        assert rows[0]["actor_id"] == 9

    def test_build_change_rows_normalizes_decimal_values(self):
        ticket = Ticket(id=43, tenant_id=7, title="Ticket", status="open")
        ticket.num_1 = Decimal("1.0000000000")

        rows = TicketService._build_change_rows(
            ticket=ticket,
            tenant_id=7,
            update_data={"num_1": Decimal("2.5000000000")},
            field_labels={"num_1": "金额"},
            actor_id=None,
            actor_name=None,
        )

        assert rows[0]["old_value"] == 1.0
        assert rows[0]["new_value"] == 2.5
        assert rows[0]["actor_type"] == "system"

    def test_pack_change_batch_single_row_with_entries(self):
        ticket = Ticket(
            id=42,
            tenant_id=7,
            title="Old",
            status="open",
            priority="medium",
        )
        field_rows = TicketService._build_change_rows(
            ticket=ticket,
            tenant_id=7,
            update_data={"title": "New", "priority": "high"},
            field_labels={"title": "标题", "priority": "优先级"},
            field_sources={"priority": "ticket_workflow"},
            actor_id=1,
            actor_name="A",
        )
        packed = TicketService._pack_change_batch(field_rows)
        assert len(packed) == 1
        assert packed[0]["field_key"] == TICKET_CHANGE_BATCH_FIELD_KEY
        assert packed[0]["old_value"] is None
        entries = packed[0]["new_value"]
        assert len(entries) == 2
        assert entries[0]["field_key"] == "title"
        assert entries[1]["field_key"] == "priority"
        assert entries[1]["field_source"] == "ticket_workflow"

    def test_build_create_change_row_uses_value_only_entries(self):
        ticket = Ticket(
            id=44,
            tenant_id=7,
            ticket_number="TK001",
            title="Created ticket",
            status="open",
            priority="medium",
        )

        entries = TicketService._build_create_entries(
            ticket=ticket,
            field_labels={
                "ticket_number": "编号",
                "title": "标题",
                "status": "状态",
                "priority": "优先级",
            },
            created_fields=["title", "status", "priority"],
            field_sources={"priority": "ticket_workflow"},
        )
        rows = TicketService._build_create_change_row(
            ticket=ticket,
            tenant_id=7,
            entries=entries,
            actor_id=9,
            actor_name="Test Actor",
        )

        assert len(rows) == 1
        assert rows[0]["field_key"] == TICKET_CHANGE_CREATE_FIELD_KEY
        assert rows[0]["old_value"] is None
        assert rows[0]["new_value"][0]["field_key"] == "ticket_number"
        assert rows[0]["new_value"][0]["old_value"] is None
        assert rows[0]["new_value"][0]["new_value"] == "TK001"
        assert rows[0]["new_value"][3]["field_source"] == "ticket_workflow"
