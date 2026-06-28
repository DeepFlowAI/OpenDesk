"""
Integration tests for knowledge base API.
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.libs.excel import build_xlsx, parse_spreadsheet
from app.services.knowledge_import_service import KNOWLEDGE_IMPORT_HEADERS


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _headers(employee_id: int, tenant_id: int) -> dict[str, str]:
    token = create_access_token({"sub": str(employee_id), "tenant_id": tenant_id, "roles": []})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def knowledge_context() -> dict:
    suffix = uuid.uuid4().hex[:10]
    password_hash = hash_password("Test1234abc")

    async with AsyncSessionLocal() as db:
        tenant_id = (
            await db.execute(
                text(
                    """
                    INSERT INTO tenants (tenant_id, slug, name, is_active)
                    VALUES (:tenant_key, :slug, :name, true)
                    RETURNING id
                    """
                ),
                {
                    "tenant_key": f"knowledge-{suffix}",
                    "slug": f"knowledge-{suffix}",
                    "name": f"Knowledge {suffix}",
                },
            )
        ).scalar_one()

        async def create_employee(name: str) -> int:
            username = _unique(name)
            return (
                await db.execute(
                    text(
                        """
                        INSERT INTO employees (
                            tenant_id, username, email, password_hash, display_name,
                            name, roles, is_active
                        )
                        VALUES (
                            :tenant_id, :username, :email, :password_hash, :display_name,
                            :name, '[]'::json, true
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "username": username,
                        "email": f"{username}@example.com",
                        "password_hash": password_hash,
                        "display_name": name,
                        "name": name,
                    },
                )
            ).scalar_one()

        async def create_role(name: str, permissions: list[str]) -> int:
            return (
                await db.execute(
                    text(
                        """
                        INSERT INTO roles (
                            tenant_id, name, description, is_system, is_active,
                            permissions, data_scopes
                        )
                        VALUES (
                            :tenant_id, :name, :description, false, true,
                            CAST(:permissions AS JSON), '{}'::json
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "name": name,
                        "description": name,
                        "permissions": json.dumps(permissions),
                    },
                )
            ).scalar_one()

        async def assign_role(employee_id: int, role_id: int) -> None:
            await db.execute(
                text("INSERT INTO employee_roles (employee_id, role_id) VALUES (:employee_id, :role_id)"),
                {"employee_id": employee_id, "role_id": role_id},
            )

        view_role = await create_role(f"knowledge-view-{suffix}", ["knowledge.workspace.view"])
        manage_role = await create_role(
            f"knowledge-manage-{suffix}",
            ["knowledge.workspace.view", "knowledge.workspace.directory.manage"],
        )
        create_role_id = await create_role(
            f"knowledge-create-{suffix}",
            ["knowledge.workspace.view", "knowledge.workspace.document.create"],
        )
        edit_role = await create_role(
            f"knowledge-edit-{suffix}",
            ["knowledge.workspace.view", "knowledge.workspace.document.edit"],
        )
        delete_role = await create_role(
            f"knowledge-delete-{suffix}",
            ["knowledge.workspace.view", "knowledge.workspace.document.delete"],
        )
        import_role = await create_role(
            f"knowledge-import-{suffix}",
            ["knowledge.workspace.view", "knowledge.workspace.import"],
        )
        export_role = await create_role(
            f"knowledge-export-{suffix}",
            ["knowledge.workspace.view", "knowledge.workspace.export"],
        )

        view_employee = await create_employee("Knowledge View")
        manage_employee = await create_employee("Knowledge Manage")
        create_employee_id = await create_employee("Knowledge Create")
        edit_employee = await create_employee("Knowledge Edit")
        delete_employee = await create_employee("Knowledge Delete")
        import_employee = await create_employee("Knowledge Import")
        export_employee = await create_employee("Knowledge Export")
        no_perm_employee = await create_employee("Knowledge None")

        for employee_id, role_id in [
            (view_employee, view_role),
            (manage_employee, manage_role),
            (create_employee_id, create_role_id),
            (edit_employee, edit_role),
            (delete_employee, delete_role),
            (import_employee, import_role),
            (export_employee, export_role),
        ]:
            await assign_role(employee_id, role_id)

        await db.commit()

    return {
        "tenant_id": tenant_id,
        "view": _headers(view_employee, tenant_id),
        "manage": _headers(manage_employee, tenant_id),
        "create": _headers(create_employee_id, tenant_id),
        "edit": _headers(edit_employee, tenant_id),
        "delete": _headers(delete_employee, tenant_id),
        "import": _headers(import_employee, tenant_id),
        "export": _headers(export_employee, tenant_id),
        "none": _headers(no_perm_employee, tenant_id),
    }


@pytest.mark.asyncio
async def test_knowledge_api_directory_and_document_flow(
    client: AsyncClient,
    knowledge_context: dict,
) -> None:
    denied = await client.post(
        "/api/v1/knowledge/directories",
        json={"name": "产品"},
        headers=knowledge_context["view"],
    )
    assert denied.status_code == 403

    root_resp = await client.post(
        "/api/v1/knowledge/directories",
        json={"name": "产品"},
        headers=knowledge_context["manage"],
    )
    assert root_resp.status_code == 201
    root_id = root_resp.json()["id"]

    child_resp = await client.post(
        "/api/v1/knowledge/directories",
        json={"name": "退款", "parent_id": root_id},
        headers=knowledge_context["manage"],
    )
    assert child_resp.status_code == 201
    child_id = child_resp.json()["id"]

    published = await client.post(
        "/api/v1/knowledge/documents",
        json={
            "directory_id": child_id,
            "title": "退款流程说明",
            "content_html": "<h2>流程</h2><p>先核实订单</p>",
            "status": "published",
            "validity_type": "permanent",
        },
        headers=knowledge_context["create"],
    )
    assert published.status_code == 201
    assert published.json()["display_status"] == "published"
    document_id = published.json()["id"]

    expired = await client.post(
        "/api/v1/knowledge/documents",
        json={
            "directory_id": child_id,
            "title": "过期知识",
            "content_html": "<p>已过期内容</p>",
            "status": "published",
            "validity_type": "scheduled",
            "valid_from": "2020-01-01T00:00:00",
            "valid_to": "2020-01-02T00:00:00",
        },
        headers=knowledge_context["create"],
    )
    assert expired.status_code == 201
    assert expired.json()["display_status"] == "expired"

    draft = await client.post(
        "/api/v1/knowledge/documents",
        json={
            "directory_id": child_id,
            "title": "内部草稿",
            "content_html": "<p>仅编辑可见</p>",
            "status": "draft",
            "validity_type": "permanent",
        },
        headers=knowledge_context["create"],
    )
    assert draft.status_code == 201

    view_list = await client.get(
        f"/api/v1/knowledge/documents?directory={root_id}&q=订单",
        headers=knowledge_context["view"],
    )
    assert view_list.status_code == 200
    assert view_list.json()["total"] == 1

    sdk_list = await client.get(
        f"/api/v1/knowledge/documents?directory={root_id}&display_status=published",
        headers=knowledge_context["view"],
    )
    assert sdk_list.status_code == 200
    assert sdk_list.json()["total"] == 1
    assert sdk_list.json()["items"][0]["id"] == document_id

    edit_list = await client.get(
        f"/api/v1/knowledge/documents?directory={root_id}",
        headers=knowledge_context["edit"],
    )
    assert edit_list.status_code == 200
    assert edit_list.json()["total"] == 3

    nonempty_delete = await client.delete(
        f"/api/v1/knowledge/directories/{child_id}",
        headers=knowledge_context["manage"],
    )
    assert nonempty_delete.status_code == 400

    detail = await client.get(
        f"/api/v1/knowledge/documents/{document_id}",
        headers=knowledge_context["view"],
    )
    assert detail.status_code == 200
    assert [item["name"] for item in detail.json()["directory_path"]] == ["产品", "退款"]

    delete_doc = await client.delete(
        f"/api/v1/knowledge/documents/{document_id}",
        headers=knowledge_context["delete"],
    )
    assert delete_doc.status_code == 200


@pytest.mark.asyncio
async def test_knowledge_api_requires_view_permission(
    client: AsyncClient,
    knowledge_context: dict,
) -> None:
    response = await client.get(
        "/api/v1/knowledge/directories",
        headers=knowledge_context["none"],
    )

    assert response.status_code == 403

    recommendation_response = await client.get(
        "/api/v1/knowledge/recommendations",
        headers=knowledge_context["none"],
    )
    assert recommendation_response.status_code == 403


@pytest.mark.asyncio
async def test_knowledge_recommendations_without_conversation_returns_empty_state(
    client: AsyncClient,
    knowledge_context: dict,
) -> None:
    response = await client.get(
        "/api/v1/knowledge/recommendations",
        headers=knowledge_context["view"],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_conversation"
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_knowledge_import_export_flow(
    client: AsyncClient,
    knowledge_context: dict,
) -> None:
    denied_template = await client.get(
        "/api/v1/knowledge/import/template",
        headers=knowledge_context["view"],
    )
    assert denied_template.status_code == 403

    template = await client.get(
        "/api/v1/knowledge/import/template",
        headers=knowledge_context["import"],
    )
    assert template.status_code == 200
    assert template.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    workbook = build_xlsx(
        KNOWLEDGE_IMPORT_HEADERS,
        [
            [
                "",
                "产品/退款",
                "退款导入说明",
                "published",
                "permanent",
                "",
                "",
                "客户可在订单详情提交退款申请。",
                "",
                "",
                "",
                "",
            ]
        ],
        sheet_name="知识文档",
    )
    preview = await client.post(
        "/api/v1/knowledge/import/preview",
        files={
            "file": (
                "knowledge.xlsx",
                workbook,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=knowledge_context["import"],
    )
    assert preview.status_code == 200
    preview_data = preview.json()
    assert preview_data["has_errors"] is False
    assert preview_data["summary"]["create_directories"] == 2
    assert preview_data["summary"]["create_documents"] == 1

    execute = await client.post(
        "/api/v1/knowledge/import/execute",
        json={"preview_token": preview_data["preview_token"]},
        headers=knowledge_context["import"],
    )
    assert execute.status_code == 200
    assert execute.json()["summary"]["create_documents"] == 1

    listed = await client.get(
        "/api/v1/knowledge/documents?q=退款导入",
        headers=knowledge_context["view"],
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    denied_export = await client.get(
        "/api/v1/knowledge/export?q=退款导入",
        headers=knowledge_context["view"],
    )
    assert denied_export.status_code == 403

    exported = await client.get(
        "/api/v1/knowledge/export?q=退款导入",
        headers=knowledge_context["export"],
    )
    assert exported.status_code == 200
    headers, rows = parse_spreadsheet(exported.content, "knowledge-export.xlsx")
    assert headers[:3] == ["id", "directory_path", "title"]
    assert rows[0][2] == "退款导入说明"

    duplicate_preview = await client.post(
        "/api/v1/knowledge/import/preview",
        files={
            "file": (
                "knowledge.xlsx",
                workbook,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=knowledge_context["import"],
    )
    assert duplicate_preview.status_code == 200
    duplicate_data = duplicate_preview.json()
    assert duplicate_data["has_errors"] is True
    assert duplicate_data["summary"]["error_rows"] == 1
