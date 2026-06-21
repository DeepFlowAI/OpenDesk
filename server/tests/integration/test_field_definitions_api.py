"""
Integration tests for Field Definition API
"""
import uuid

import pytest
from httpx import AsyncClient

from app.configs.settings import settings

API_KEY = settings.TENANT_API_KEY
TENANT_HEADERS = {"X-API-Key": API_KEY}


def _unique(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _field_payload(payload: dict, key: str | None = None) -> dict:
    data = {**payload}
    data.setdefault("key", key or _unique("field"))
    return data


async def _setup_tenant_and_auth(client: AsyncClient) -> dict:
    """Create a fresh tenant, login, and return auth headers."""
    tenant_name = _unique("fd_test")
    admin_user = _unique("admin")
    admin_pass = "Passw0rd123"

    create_resp = await client.post("/api/v1/tenants", headers=TENANT_HEADERS, json={
        "name": tenant_name,
        "admin_username": admin_user,
        "admin_password": admin_pass,
    })
    assert create_resp.status_code == 201
    tenant_slug = create_resp.json()["id"]

    login_resp = await client.post("/api/v1/auth/login", json={
        "tenant": tenant_slug,
        "username": admin_user,
        "password": admin_pass,
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


SAMPLE_FIELD = {
    "domain": "user",
    "key": "vip_level",
    "name": "VIP等级",
    "description": "VIP level of the user",
    "help_text": "请选择VIP等级",
    "field_type": "single_line_text",
    "type_config": {"max_length": 256, "placeholder": "请输入"},
    "sort_order": 0,
}

SAMPLE_SELECT_FIELD = {
    "domain": "user",
    "key": "gender",
    "name": "性别",
    "field_type": "single_select",
    "type_config": {},
    "options": [
        {"label": "男", "value": "male", "sort_order": 0},
        {"label": "女", "value": "female", "sort_order": 1},
    ],
}

SAMPLE_TREE_FIELD = {
    "domain": "organization",
    "key": "industry_category",
    "name": "行业分类",
    "field_type": "single_select_tree",
    "type_config": {"tree_source": "static", "leaf_only": False},
    "tree_nodes": [
        {"label": "科技", "value": "tech", "sort_order": 0},
        {"label": "金融", "value": "finance", "sort_order": 1},
    ],
}

SAMPLE_SHARED_POOL_FIELD = {
    "domain": "shared_pool",
    "key": "urgency",
    "name": "紧急程度",
    "field_type": "single_select",
    "type_config": {},
    "applicable_modules": ["ticket"],
    "options": [
        {"label": "紧急", "value": "urgent"},
        {"label": "普通", "value": "normal"},
    ],
}


class TestFieldDefinitionCRUD:

    @pytest.mark.asyncio
    async def test_list_empty_returns_200(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        resp = await client.get("/api/v1/field-definitions?domain=user", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_unified_user_fields_include_level_system_field(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        resp = await client.get("/api/v1/field-definitions/unified?domain=user", headers=headers)
        assert resp.status_code == 200
        fields = {item["key"]: item for item in resp.json()["items"]}

        level = fields["level"]
        assert level["source"] == "system"
        assert level["name"] == "等级"
        assert level["field_type"] == "single_select"
        assert level["type_config"]["default_value"] == "normal"
        assert [option["value"] for option in level["options"]] == ["normal", "vip"]

    @pytest.mark.asyncio
    async def test_create_text_field_returns_201(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        resp = await client.post("/api/v1/field-definitions", json=SAMPLE_FIELD, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "VIP等级"
        assert data["field_type"] == "single_line_text"
        assert data["slot_column"].startswith("str_")
        assert data["domain"] == "user"
        assert data["key"] == "vip_level"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_duplicate_field_key_returns_409(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        await client.post("/api/v1/field-definitions", json=SAMPLE_FIELD, headers=headers)
        payload = {**SAMPLE_FIELD, "name": "VIP等级2"}
        resp = await client.post("/api/v1/field-definitions", json=payload, headers=headers)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_invalid_field_key_returns_422(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        payload = {**SAMPLE_FIELD, "key": "VIP Level"}
        resp = await client.post("/api/v1/field-definitions", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_select_field_with_options(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        resp = await client.post("/api/v1/field-definitions", json=SAMPLE_SELECT_FIELD, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["field_type"] == "single_select"
        assert len(data["options"]) == 2
        assert data["options"][0]["label"] == "男"

    @pytest.mark.asyncio
    async def test_create_tree_field_with_nodes(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        resp = await client.post("/api/v1/field-definitions", json=SAMPLE_TREE_FIELD, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["field_type"] == "single_select_tree"
        assert len(data["tree_nodes"]) == 2

    @pytest.mark.asyncio
    async def test_create_shared_pool_field(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        resp = await client.post("/api/v1/field-definitions", json=SAMPLE_SHARED_POOL_FIELD, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["domain"] == "shared_pool"
        assert data["applicable_modules"] == ["ticket"]

    @pytest.mark.asyncio
    async def test_create_shared_pool_without_modules_returns_400(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        payload = {
            "domain": "shared_pool",
            "key": "missing_modules",
            "name": "缺少模块",
            "field_type": "single_line_text",
        }
        resp = await client.post("/api/v1/field-definitions", json=payload, headers=headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_by_id_returns_200(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        create_resp = await client.post("/api/v1/field-definitions", json=SAMPLE_FIELD, headers=headers)
        created_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/field-definitions/{created_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == created_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        resp = await client.get("/api/v1/field-definitions/99999", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_returns_200(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        create_resp = await client.post("/api/v1/field-definitions", json=SAMPLE_FIELD, headers=headers)
        created_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/field-definitions/{created_id}",
            json={"name": "VIP等级_updated", "description": "Updated desc"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "VIP等级_updated"
        assert resp.json()["key"] == "vip_level"

    @pytest.mark.asyncio
    async def test_update_field_key_is_ignored(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        create_resp = await client.post("/api/v1/field-definitions", json=SAMPLE_FIELD, headers=headers)
        created_id = create_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/field-definitions/{created_id}",
            json={"name": "VIP等级_updated", "key": "changed_key"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["key"] == "vip_level"

    @pytest.mark.asyncio
    async def test_delete_returns_200(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        create_resp = await client.post("/api/v1/field-definitions", json=SAMPLE_FIELD, headers=headers)
        created_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/field-definitions/{created_id}", headers=headers)
        assert resp.status_code == 200

        resp2 = await client.get(f"/api/v1/field-definitions/{created_id}", headers=headers)
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_name_returns_409(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        await client.post("/api/v1/field-definitions", json=SAMPLE_FIELD, headers=headers)
        resp = await client.post("/api/v1/field-definitions", json=SAMPLE_FIELD, headers=headers)
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_field_type_returns_400(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        payload = {**SAMPLE_FIELD, "field_type": "invalid_type"}
        resp = await client.post("/api/v1/field-definitions", json=payload, headers=headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_auth_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/field-definitions")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client: AsyncClient):
        headers = {"Authorization": "Bearer invalid.token"}
        resp = await client.get("/api/v1/field-definitions", headers=headers)
        assert resp.status_code == 401


class TestSlotAllocation:

    @pytest.mark.asyncio
    async def test_auto_allocates_sequential_slots(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        slots = []
        for i in range(3):
            payload = {
                "domain": "user",
                "key": _unique("field"),
                "name": f"字段_{i}",
                "field_type": "single_line_text",
            }
            resp = await client.post("/api/v1/field-definitions", json=payload, headers=headers)
            assert resp.status_code == 201
            slots.append(resp.json()["slot_column"])

        assert slots == ["str_1", "str_2", "str_3"]

    @pytest.mark.asyncio
    async def test_different_types_use_different_prefixes(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)

        text_payload = {"domain": "user", "key": "text_field", "name": "文本字段", "field_type": "single_line_text"}
        num_payload = {"domain": "user", "key": "number_field", "name": "数值字段", "field_type": "number"}
        json_payload = {"domain": "user", "key": "multi_select_field", "name": "多选字段", "field_type": "multi_select"}

        resp1 = await client.post("/api/v1/field-definitions", json=text_payload, headers=headers)
        resp2 = await client.post("/api/v1/field-definitions", json=num_payload, headers=headers)
        resp3 = await client.post("/api/v1/field-definitions", json=json_payload, headers=headers)

        assert resp1.json()["slot_column"] == "str_1"
        assert resp2.json()["slot_column"] == "num_1"
        assert resp3.json()["slot_column"] == "json_1"

    @pytest.mark.asyncio
    async def test_selector_types_share_num_slot_pool_with_number(self, client: AsyncClient):
        """user/org/employee/group select store ids in num_* slots like number fields."""
        headers = await _setup_tenant_and_auth(client)
        num_payload = {"domain": "user", "key": _unique("num_first"), "name": _unique("num_first"), "field_type": "number"}
        usr_payload = {"domain": "user", "key": _unique("ref_user"), "name": _unique("ref_user"), "field_type": "user_select"}
        r1 = await client.post("/api/v1/field-definitions", json=num_payload, headers=headers)
        r2 = await client.post("/api/v1/field-definitions", json=usr_payload, headers=headers)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["slot_column"] == "num_1"
        assert r2.json()["slot_column"] == "num_2"


class TestSelectorFieldTypes:
    """Custom fields that reference entities must allocate num_* slots (regression)."""

    @pytest.mark.asyncio
    async def test_create_user_select_field_returns_201(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        payload = {
            "domain": "user",
            "key": _unique("user_select"),
            "name": _unique("用户选择"),
            "field_type": "user_select",
            "type_config": {},
        }
        resp = await client.post("/api/v1/field-definitions", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["field_type"] == "user_select"
        assert data["slot_column"].startswith("num_")
        assert data["domain"] == "user"

    @pytest.mark.asyncio
    async def test_create_organization_select_field_returns_201(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        payload = {
            "domain": "organization",
            "key": _unique("organization_select"),
            "name": _unique("组织选择"),
            "field_type": "organization_select",
            "type_config": {},
        }
        resp = await client.post("/api/v1/field-definitions", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["field_type"] == "organization_select"
        assert data["slot_column"].startswith("num_")
        assert data["domain"] == "organization"

    @pytest.mark.asyncio
    async def test_create_employee_select_shared_pool_returns_201(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        payload = {
            "domain": "shared_pool",
            "key": _unique("employee_select"),
            "name": _unique("员工选择"),
            "field_type": "employee_select",
            "type_config": {},
            "applicable_modules": ["ticket"],
        }
        resp = await client.post("/api/v1/field-definitions", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["field_type"] == "employee_select"
        assert data["slot_column"].startswith("num_")
        assert data["applicable_modules"] == ["ticket"]

    @pytest.mark.asyncio
    async def test_create_group_select_shared_pool_returns_201(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        payload = {
            "domain": "shared_pool",
            "key": _unique("group_select"),
            "name": _unique("员工组选择"),
            "field_type": "group_select",
            "type_config": {},
            "applicable_modules": ["ticket"],
        }
        resp = await client.post("/api/v1/field-definitions", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["field_type"] == "group_select"
        assert data["slot_column"].startswith("num_")
        assert data["applicable_modules"] == ["ticket"]


class TestFieldOptions:

    @pytest.mark.asyncio
    async def test_add_option_to_select_field(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        field_payload = {
            "domain": "user",
            "key": "status_field",
            "name": "状态",
            "field_type": "single_select",
        }
        create_resp = await client.post("/api/v1/field-definitions", json=field_payload, headers=headers)
        field_id = create_resp.json()["id"]

        option_payload = {"label": "活跃", "value": "active"}
        resp = await client.post(
            f"/api/v1/field-definitions/{field_id}/options",
            json=option_payload,
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["label"] == "活跃"

    @pytest.mark.asyncio
    async def test_list_options(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        create_resp = await client.post("/api/v1/field-definitions", json={
            "domain": "user",
            "key": "color",
            "name": "颜色",
            "field_type": "single_select",
            "options": [
                {"label": "红", "value": "red"},
                {"label": "蓝", "value": "blue"},
            ],
        }, headers=headers)
        field_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/field-definitions/{field_id}/options", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_add_option_to_non_select_field_returns_400(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        create_resp = await client.post("/api/v1/field-definitions", json={
            "domain": "user",
            "key": "plain_text",
            "name": "纯文本",
            "field_type": "single_line_text",
        }, headers=headers)
        field_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/field-definitions/{field_id}/options",
            json={"label": "x", "value": "x"},
            headers=headers,
        )
        assert resp.status_code == 400


class TestTreeNodes:

    @pytest.mark.asyncio
    async def test_add_tree_node(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        create_resp = await client.post("/api/v1/field-definitions", json={
            "domain": "organization",
            "key": "region",
            "name": "地区",
            "field_type": "single_select_tree",
            "type_config": {"tree_source": "static"},
        }, headers=headers)
        field_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/field-definitions/{field_id}/tree-nodes",
            json={"label": "中国", "value": "cn"},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["label"] == "中国"

    @pytest.mark.asyncio
    async def test_add_tree_node_to_non_tree_field_returns_400(self, client: AsyncClient):
        headers = await _setup_tenant_and_auth(client)
        create_resp = await client.post("/api/v1/field-definitions", json={
            "domain": "user",
            "key": "plain_text",
            "name": "纯文本",
            "field_type": "single_line_text",
        }, headers=headers)
        field_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/field-definitions/{field_id}/tree-nodes",
            json={"label": "x", "value": "x"},
            headers=headers,
        )
        assert resp.status_code == 400
