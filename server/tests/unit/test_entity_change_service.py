"""
Unit tests for user and organization change diff generation.
"""
from decimal import Decimal

from app.models.organization import Organization
from app.models.user import User
from app.services.entity_change_service import (
    ENTITY_CHANGE_BATCH_FIELD_KEY,
    ENTITY_CHANGE_CREATE_FIELD_KEY,
    EntityChangeService,
)


class TestEntityChangeDiff:

    def test_build_change_rows_includes_only_changed_user_fields(self):
        user = User(
            id=42,
            tenant_id=7,
            external_id="usr_test",
            name="Old name",
            email="old@example.com",
        )

        rows = EntityChangeService.build_change_rows(
            entity_type="user",
            entity_id=42,
            current=user,
            tenant_id=7,
            update_data={"name": "New name", "email": "old@example.com"},
            field_labels={"name": "昵称", "email": "邮箱"},
            actor_id=9,
            actor_name="Test Actor",
        )

        assert len(rows) == 1
        assert rows[0]["field_key"] == "name"
        assert rows[0]["field_label"] == "昵称"
        assert rows[0]["old_value"] == "Old name"
        assert rows[0]["new_value"] == "New name"
        assert rows[0]["entity_type"] == "user"
        assert rows[0]["entity_id"] == 42

    def test_build_change_rows_normalizes_decimal_values(self):
        org = Organization(id=43, tenant_id=7, name="Org")
        org.num_1 = Decimal("1.0000000000")

        rows = EntityChangeService.build_change_rows(
            entity_type="organization",
            entity_id=43,
            current=org,
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
        user = User(id=42, tenant_id=7, external_id="usr_test", name="Old", phone="1")
        field_rows = EntityChangeService.build_change_rows(
            entity_type="user",
            entity_id=42,
            current=user,
            tenant_id=7,
            update_data={"name": "New", "phone": "2"},
            field_labels={"name": "昵称", "phone": "手机号"},
            actor_id=1,
            actor_name="A",
        )
        packed = EntityChangeService.pack_change_batch(field_rows)

        assert len(packed) == 1
        assert packed[0]["field_key"] == ENTITY_CHANGE_BATCH_FIELD_KEY
        assert packed[0]["old_value"] is None
        entries = packed[0]["new_value"]
        assert len(entries) == 2
        assert entries[0]["field_key"] == "name"
        assert entries[1]["field_key"] == "phone"

    def test_build_create_change_row_uses_value_only_entries(self):
        org = Organization(id=44, tenant_id=7, name="Created org", description="Desc")

        entries = EntityChangeService.build_create_entries(
            entity=org,
            field_labels={"name": "名称", "description": "描述"},
            created_fields=["name", "description"],
        )
        rows = EntityChangeService.build_create_change_row(
            entity_type="organization",
            entity_id=44,
            tenant_id=7,
            entries=entries,
            actor_id=9,
            actor_name="Test Actor",
        )

        assert len(rows) == 1
        assert rows[0]["field_key"] == ENTITY_CHANGE_CREATE_FIELD_KEY
        assert rows[0]["old_value"] is None
        assert rows[0]["new_value"][0]["field_key"] == "name"
        assert rows[0]["new_value"][0]["old_value"] is None
        assert rows[0]["new_value"][0]["new_value"] == "Created org"
