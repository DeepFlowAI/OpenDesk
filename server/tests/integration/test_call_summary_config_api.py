"""
Integration tests for call summary config APIs.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from app.models.call_summary_config import CallSummaryConfig
from app.models.fd_field_definition import FdFieldDefinition
from app.models.tenant import Tenant


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _auth_header(tenant_id: int) -> dict:
    token = create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": ["admin"], "name": "Admin"})
    return {"Authorization": f"Bearer {token}"}


async def _create_tenant_with_field(applicable_modules: list[str]) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        tenant = Tenant(
            tenant_id=_unique("call_summary_tenant"),
            name="Call Summary Test Tenant",
            is_active=True,
        )
        db.add(tenant)
        await db.flush()

        field = FdFieldDefinition(
            tenant_id=tenant.id,
            domain="shared_pool",
            source="custom",
            name=_unique("Call Field"),
            description=None,
            help_text=None,
            field_type="single_line_text",
            type_config={},
            slot_column="str_1",
            field_key=_unique("call_field"),
            applicable_modules=applicable_modules,
            show_in_workspace=None,
            status="active",
            sort_order=1,
        )
        db.add(field)
        await db.commit()
        return tenant.id, field.id


async def _cleanup(tenant_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(CallSummaryConfig).where(CallSummaryConfig.tenant_id == tenant_id))
        await db.execute(delete(FdFieldDefinition).where(FdFieldDefinition.tenant_id == tenant_id))
        await db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await db.commit()


class TestCallSummaryConfigAPI:

    @pytest.mark.asyncio
    async def test_field_and_rule_flow(self, client: AsyncClient):
        tenant_id, field_id = await _create_tenant_with_field(["call_summary"])
        headers = _auth_header(tenant_id)
        try:
            config_resp = await client.get("/api/v1/call-summary/config", headers=headers)
            assert config_resp.status_code == 200
            assert config_resp.json()["tenant_id"] == tenant_id

            empty_fields = await client.get("/api/v1/call-summary/config/fields", headers=headers)
            assert empty_fields.status_code == 200
            assert empty_fields.json()["total"] == 0

            add_field = await client.post(
                "/api/v1/call-summary/config/fields",
                headers=headers,
                json={"field_definition_id": field_id},
            )
            assert add_field.status_code == 201
            config_field_id = add_field.json()["id"]
            assert add_field.json()["field_definition_id"] == field_id

            duplicate = await client.post(
                "/api/v1/call-summary/config/fields",
                headers=headers,
                json={"field_definition_id": field_id},
            )
            assert duplicate.status_code == 409

            toggle = await client.put(
                f"/api/v1/call-summary/config/fields/{config_field_id}",
                headers=headers,
                json={"is_active": False},
            )
            assert toggle.status_code == 200
            assert toggle.json()["is_active"] is False

            sort_fields = await client.put(
                "/api/v1/call-summary/config/fields/sort",
                headers=headers,
                json={"items": [{"id": config_field_id, "sort_order": 0}]},
            )
            assert sort_fields.status_code == 200

            rule_payload = {
                "name": "VIP field readonly",
                "condition_logic": "and",
                "conditions": [{"field_id": field_id, "operator": "eq", "value": "vip"}],
                "actions": [{"target_field_id": field_id, "state": "readonly"}],
                "is_enabled": True,
            }
            create_rule = await client.post(
                "/api/v1/call-summary/config/interaction-rules",
                headers=headers,
                json=rule_payload,
            )
            assert create_rule.status_code == 201
            rule_id = create_rule.json()["id"]

            list_rules = await client.get("/api/v1/call-summary/config/interaction-rules", headers=headers)
            assert list_rules.status_code == 200
            assert list_rules.json()["total"] == 1

            update_rule = await client.put(
                f"/api/v1/call-summary/config/interaction-rules/{rule_id}",
                headers=headers,
                json={"is_enabled": False},
            )
            assert update_rule.status_code == 200
            assert update_rule.json()["is_enabled"] is False

            sort_rules = await client.put(
                "/api/v1/call-summary/config/interaction-rules/sort",
                headers=headers,
                json={"items": [{"id": rule_id, "sort_order": 0}]},
            )
            assert sort_rules.status_code == 200

            delete_rule = await client.delete(
                f"/api/v1/call-summary/config/interaction-rules/{rule_id}",
                headers=headers,
            )
            assert delete_rule.status_code == 200

            delete_field = await client.delete(
                f"/api/v1/call-summary/config/fields/{config_field_id}",
                headers=headers,
            )
            assert delete_field.status_code == 200
        finally:
            await _cleanup(tenant_id)

    @pytest.mark.asyncio
    async def test_rejects_field_without_call_summary_applicability(self, client: AsyncClient):
        tenant_id, field_id = await _create_tenant_with_field(["session_summary"])
        headers = _auth_header(tenant_id)
        try:
            resp = await client.post(
                "/api/v1/call-summary/config/fields",
                headers=headers,
                json={"field_definition_id": field_id},
            )
            assert resp.status_code == 400
            assert "call summary" in resp.json()["message"]
        finally:
            await _cleanup(tenant_id)
