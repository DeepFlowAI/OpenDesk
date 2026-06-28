"""Integration tests for /api/v1/reports/sessions/employees (SR2)."""
from datetime import date
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

import app.extensions  # triggers private overlay
from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal, engine
from app.main import _fastapi_app

TZ = ZoneInfo("Asia/Shanghai")
_ANCHOR_DATE_STR = "2026-05-10"
_TENANT_SLUG = "test-reports-emp-corp"

_SEEDED = False
_TOKEN = ""
_TENANT_PK = 0
_AGENT_A_ID = 0
_AGENT_B_ID = 0


@pytest_asyncio.fixture(autouse=True)
async def seed():
    global _SEEDED, _TOKEN, _TENANT_PK, _AGENT_A_ID, _AGENT_B_ID

    if not any(r.path.startswith("/api/v1/reports/sessions/employees") for r in _fastapi_app.routes):
        from app.extensions.reports import register as _reg
        _reg(_fastapi_app)

    if _SEEDED:
        yield
        await engine.dispose()
        return

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO tenants (tenant_id, name, is_active)
            VALUES (:slug, 'Reports Test Corp', true)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {"slug": _TENANT_SLUG})
        await db.commit()
        t = await db.execute(text("SELECT id FROM tenants WHERE tenant_id = :slug"), {"slug": _TENANT_SLUG})
        _TENANT_PK = t.scalar_one()

        await db.execute(text("DELETE FROM conversations WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.commit()
        # Wipe pre-existing employees too so counts are deterministic across runs.
        await db.execute(text("DELETE FROM employees WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.commit()

        pw = hash_password("Test1234")
        await db.execute(text("""
            INSERT INTO employees (tenant_id, username, email, password_hash, display_name, name, roles, is_active)
            VALUES
              (:tid, 'emp_alpha', 'alpha@reports.test', :pw, 'Alpha User', 'Alpha User', '["admin"]'::jsonb, true),
              (:tid, 'emp_beta',  'beta@reports.test',  :pw, 'Beta User',  'Beta User',  '["agent"]'::jsonb, true),
              (:tid, 'emp_gamma', 'gamma@reports.test', :pw, 'Gamma User', 'Gamma User', '["agent"]'::jsonb, false)
            ON CONFLICT ON CONSTRAINT uq_employees_tenant_username DO NOTHING
        """), {"tid": _TENANT_PK, "pw": pw})
        await db.commit()
        a = await db.execute(text("SELECT id FROM employees WHERE username='emp_alpha' AND tenant_id=:tid"), {"tid": _TENANT_PK})
        _AGENT_A_ID = a.scalar_one()
        b = await db.execute(text("SELECT id FROM employees WHERE username='emp_beta' AND tenant_id=:tid"), {"tid": _TENANT_PK})
        _AGENT_B_ID = b.scalar_one()

        await db.execute(text("""
            INSERT INTO users (tenant_id, public_id, external_id, name)
            VALUES (:tid, 'rep_emp_v', 'rep_emp_v', 'Rep Emp Visitor')
            ON CONFLICT ON CONSTRAINT uq_users_tenant_external DO NOTHING
        """), {"tid": _TENANT_PK})
        await db.commit()
        v = await db.execute(text("SELECT id FROM users WHERE external_id='rep_emp_v' AND tenant_id=:tid"), {"tid": _TENANT_PK})
        visitor_id = v.scalar_one()

        await db.execute(text("""
            INSERT INTO conversations (public_id, share_code, tenant_id, visitor_id, agent_id, status, started_at, ended_at, ended_by)
            VALUES
              ('cv_rep_emp_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :a, 'closed',
               ((:anchor)::date + TIME '10:00')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '10:10')::timestamp AT TIME ZONE 'Asia/Shanghai', 'agent'),
              ('cv_rep_emp_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :a, 'closed',
               ((:anchor)::date + TIME '11:00')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '11:10')::timestamp AT TIME ZONE 'Asia/Shanghai', 'agent'),
              ('cv_rep_emp_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :a, 'closed',
               ((:anchor)::date + TIME '13:00')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '13:10')::timestamp AT TIME ZONE 'Asia/Shanghai', 'agent'),
              ('cv_rep_emp_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :b, 'closed',
               ((:anchor)::date + TIME '14:00')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '14:10')::timestamp AT TIME ZONE 'Asia/Shanghai', 'agent')
        """), {"tid": _TENANT_PK, "vid": visitor_id, "a": _AGENT_A_ID, "b": _AGENT_B_ID,
              "anchor": date.fromisoformat(_ANCHOR_DATE_STR)})
        await db.commit()

        _TOKEN = create_access_token(
            {"sub": str(_AGENT_A_ID), "tenant_id": _TENANT_PK, "roles": ["admin"]}
        )

    _SEEDED = True
    yield
    await engine.dispose()


def _auth():
    return {"Authorization": f"Bearer {_TOKEN}"}


class TestEmployeesListAPI:

    @pytest.mark.asyncio
    async def test_list_returns_all_employees(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/employees",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        # 3 employees seeded; the third is inactive but should still be present.
        assert data["total"] == 3
        assert len(data["items"]) == 3
        # Default sort: session_count desc — Alpha (3) > Beta (1) > Gamma (0)
        assert data["items"][0]["employee"]["name"] == "Alpha User"
        assert data["items"][0]["metrics"]["session_count"] == 3
        assert data["items"][1]["metrics"]["session_count"] == 1
        assert data["items"][2]["metrics"]["session_count"] == 0

    @pytest.mark.asyncio
    async def test_search_filters_employees(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/employees",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "q": "Beta"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["employee"]["name"] == "Beta User"

    @pytest.mark.asyncio
    async def test_sort_by_name_asc(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/employees",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR,
                    "sort": "name", "order": "asc"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        names = [it["employee"]["name"] for it in resp.json()["items"]]
        assert names == ["Alpha User", "Beta User", "Gamma User"]

    @pytest.mark.asyncio
    async def test_inactive_employee_still_listed(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/employees",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        data = resp.json()
        gamma = next(it for it in data["items"] if it["employee"]["name"] == "Gamma User")
        assert gamma["employee"]["is_active"] is False
        assert gamma["metrics"]["session_count"] == 0

    @pytest.mark.asyncio
    async def test_pagination(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/employees",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR,
                    "page": 1, "per_page": 2},
            headers=_auth(),
        )
        data = resp.json()
        assert data["total"] == 3
        assert data["per_page"] == 2
        assert data["pages"] == 2
        assert len(data["items"]) == 2

        resp2 = await client.get(
            "/api/v1/reports/sessions/employees",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR,
                    "page": 2, "per_page": 2},
            headers=_auth(),
        )
        assert len(resp2.json()["items"]) == 1

    @pytest.mark.asyncio
    async def test_invalid_date_range_returns_400(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/employees",
            params={"start": "2026-05-20", "end": "2026-05-19"},
            headers=_auth(),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_unauth_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/employees",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
        )
        assert resp.status_code == 401


class TestEmployeeDetailAPI:

    @pytest.mark.asyncio
    async def test_detail_returns_employee_and_metrics(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/reports/sessions/employees/{_AGENT_A_ID}",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["employee"]["id"] == _AGENT_A_ID
        assert data["employee"]["name"] == "Alpha User"
        assert data["metrics"]["session_count"] == 3
        assert "reception_segment_count" in data["metrics"]
        assert "bot_session_count" not in data["metrics"]
        assert "as_of" in data

    @pytest.mark.asyncio
    async def test_detail_unknown_employee_returns_404(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/employees/999999999",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_trend_returns_basic_metrics_only(self, client: AsyncClient):
        resp = await client.get(
            f"/api/v1/reports/sessions/employees/{_AGENT_A_ID}/trend",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "trend": "hour"},
            headers=_auth(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["trend"] == "hour"
        assert len(data["buckets"]) == 24
        hour_10 = next(bucket for bucket in data["buckets"] if bucket["label"] == "10")
        assert hour_10["metrics"]["session_count"] == 1
        assert "bot_session_count" not in hour_10["metrics"]
        assert "reception_segment_count" not in hour_10["metrics"]
