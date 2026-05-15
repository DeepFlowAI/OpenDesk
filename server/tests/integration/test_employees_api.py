"""
Integration tests for Employees API
"""
import pytest
from httpx import AsyncClient
from app.core.security import create_access_token


def _auth_header(tenant_id: int = 7, role: str = "admin") -> dict:
    token = create_access_token({"sub": "1", "tenant_id": tenant_id, "roles": [role]})
    return {"Authorization": f"Bearer {token}"}


class TestEmployeesAPI:

    @pytest.mark.asyncio
    async def test_list_employees_returns_200(self, client: AsyncClient):
        headers = _auth_header()
        resp = await client.get("/api/v1/employees", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data

    @pytest.mark.asyncio
    async def test_create_employee_returns_201(self, client: AsyncClient):
        headers = _auth_header()
        payload = {
            "name": "Test Employee",
            "username": f"testuser_{__import__('time').time_ns()}",
            "email": f"test_{__import__('time').time_ns()}@example.com",
            "password": "Test1234abc",
            "roles": ["agent"],
        }
        resp = await client.post("/api/v1/employees", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Employee"
        assert data["roles"] == ["agent"]
        assert data["is_active"] is True
        assert data["max_concurrent"] == 10
        assert data["default_language"] == "system"
        assert "password" not in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_create_employee_missing_required_field_returns_422(self, client: AsyncClient):
        headers = _auth_header()
        resp = await client.post("/api/v1/employees", json={}, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_employee_invalid_role_returns_422(self, client: AsyncClient):
        headers = _auth_header()
        payload = {
            "name": "Bad Role",
            "username": f"badrole_{__import__('time').time_ns()}",
            "email": f"badrole_{__import__('time').time_ns()}@example.com",
            "password": "Test1234abc",
            "roles": ["superuser"],
        }
        resp = await client.post("/api/v1/employees", json=payload, headers=headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_employee_duplicate_username_returns_400(self, client: AsyncClient):
        headers = _auth_header()
        ts = __import__("time").time_ns()
        payload = {
            "name": "Dup User",
            "username": f"dupuser_{ts}",
            "email": f"dup1_{ts}@example.com",
            "password": "Test1234abc",
        }
        resp1 = await client.post("/api/v1/employees", json=payload, headers=headers)
        assert resp1.status_code == 201

        payload["email"] = f"dup2_{ts}@example.com"
        resp2 = await client.post("/api/v1/employees", json=payload, headers=headers)
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_get_employee_returns_200(self, client: AsyncClient):
        headers = _auth_header()
        ts = __import__("time").time_ns()
        payload = {
            "name": "Get Test",
            "username": f"getuser_{ts}",
            "email": f"get_{ts}@example.com",
            "password": "Test1234abc",
        }
        create_resp = await client.post("/api/v1/employees", json=payload, headers=headers)
        emp_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/employees/{emp_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Test"

    @pytest.mark.asyncio
    async def test_get_employee_not_found_returns_404(self, client: AsyncClient):
        headers = _auth_header()
        resp = await client.get("/api/v1/employees/99999", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_employee_returns_200(self, client: AsyncClient):
        headers = _auth_header()
        ts = __import__("time").time_ns()
        payload = {
            "name": "Update Test",
            "username": f"updateuser_{ts}",
            "email": f"update_{ts}@example.com",
            "password": "Test1234abc",
        }
        create_resp = await client.post("/api/v1/employees", json=payload, headers=headers)
        emp_id = create_resp.json()["id"]

        update_resp = await client.put(
            f"/api/v1/employees/{emp_id}",
            json={"name": "Updated Name", "nickname": "Nick"},
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Updated Name"
        assert update_resp.json()["nickname"] == "Nick"

    @pytest.mark.asyncio
    async def test_update_employee_syncs_group_membership(self, client: AsyncClient):
        headers = _auth_header()
        ts = __import__("time").time_ns()
        group_resp = await client.post(
            "/api/v1/employee-groups",
            json={"name": f"Employee Edit Group {ts}"},
            headers=headers,
        )
        assert group_resp.status_code == 201
        group_id = group_resp.json()["id"]

        payload = {
            "name": "Group Sync Test",
            "username": f"groupsync_{ts}",
            "email": f"groupsync_{ts}@example.com",
            "password": "Test1234abc",
        }
        create_resp = await client.post("/api/v1/employees", json=payload, headers=headers)
        assert create_resp.status_code == 201
        emp_id = create_resp.json()["id"]

        update_resp = await client.put(
            f"/api/v1/employees/{emp_id}",
            json={"group_ids": [group_id]},
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["group_ids"] == [group_id]

        detail_resp = await client.get(f"/api/v1/employees/{emp_id}", headers=headers)
        assert detail_resp.status_code == 200
        assert detail_resp.json()["group_ids"] == [group_id]

        group_detail_resp = await client.get(f"/api/v1/employee-groups/{group_id}", headers=headers)
        assert group_detail_resp.status_code == 200
        member_ids = [member["employee_id"] for member in group_detail_resp.json()["members"]]
        assert emp_id in member_ids

    @pytest.mark.asyncio
    async def test_delete_employee_returns_200(self, client: AsyncClient):
        headers = _auth_header()
        ts = __import__("time").time_ns()
        payload = {
            "name": "Delete Test",
            "username": f"deluser_{ts}",
            "email": f"del_{ts}@example.com",
            "password": "Test1234abc",
        }
        create_resp = await client.post("/api/v1/employees", json=payload, headers=headers)
        emp_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/employees/{emp_id}", headers=headers)
        assert resp.status_code == 200

        get_resp = await client.get(f"/api/v1/employees/{emp_id}", headers=headers)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_toggle_status_returns_200(self, client: AsyncClient):
        headers = _auth_header()
        ts = __import__("time").time_ns()
        payload = {
            "name": "Status Test",
            "username": f"statususer_{ts}",
            "email": f"status_{ts}@example.com",
            "password": "Test1234abc",
        }
        create_resp = await client.post("/api/v1/employees", json=payload, headers=headers)
        emp_id = create_resp.json()["id"]
        assert create_resp.json()["is_active"] is True

        disable_resp = await client.patch(
            f"/api/v1/employees/{emp_id}/status",
            json={"is_active": False},
            headers=headers,
        )
        assert disable_resp.status_code == 200
        assert disable_resp.json()["is_active"] is False

        enable_resp = await client.patch(
            f"/api/v1/employees/{emp_id}/status",
            json={"is_active": True},
            headers=headers,
        )
        assert enable_resp.status_code == 200
        assert enable_resp.json()["is_active"] is True

    @pytest.mark.asyncio
    async def test_list_with_keyword_filter(self, client: AsyncClient):
        headers = _auth_header()
        ts = __import__("time").time_ns()
        payload = {
            "name": "Keyword Searchable",
            "username": f"kwuser_{ts}",
            "email": f"kw_{ts}@example.com",
            "password": "Test1234abc",
            "job_number": f"JN{ts}",
        }
        await client.post("/api/v1/employees", json=payload, headers=headers)

        resp = await client.get(
            "/api/v1/employees",
            params={"keyword": "Keyword Searchable"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_with_role_filter(self, client: AsyncClient):
        headers = _auth_header()
        resp = await client.get(
            "/api/v1/employees",
            params={"role": "admin"},
            headers=headers,
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert "admin" in item["roles"]

    @pytest.mark.asyncio
    async def test_list_role_filter_matches_employee_with_multiple_roles(self, client: AsyncClient):
        headers = _auth_header()
        ts = __import__("time").time_ns()
        payload = {
            "name": "Admin And Agent",
            "username": f"multirole_{ts}",
            "email": f"multirole_{ts}@example.com",
            "password": "Test1234abc",
            "roles": ["admin", "agent"],
        }
        create_resp = await client.post("/api/v1/employees", json=payload, headers=headers)
        assert create_resp.status_code == 201
        emp_id = create_resp.json()["id"]

        for role_param in ("admin", "agent"):
            resp = await client.get(
                "/api/v1/employees",
                params={"role": role_param},
                headers=headers,
            )
            assert resp.status_code == 200
            ids = [item["id"] for item in resp.json()["items"]]
            assert emp_id in ids, f"Expected employee when filtering role={role_param}"

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, client: AsyncClient):
        headers_t7 = _auth_header(tenant_id=7)
        ts = __import__("time").time_ns()
        payload = {
            "name": "Tenant7 Only",
            "username": f"t7user_{ts}",
            "email": f"t7_{ts}@example.com",
            "password": "Test1234abc",
        }
        create_resp = await client.post("/api/v1/employees", json=payload, headers=headers_t7)
        emp_id = create_resp.json()["id"]

        headers_other = _auth_header(tenant_id=9999)
        resp = await client.get(f"/api/v1/employees/{emp_id}", headers=headers_other)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_422(self, client: AsyncClient):
        resp = await client.get("/api/v1/employees")
        assert resp.status_code == 422
