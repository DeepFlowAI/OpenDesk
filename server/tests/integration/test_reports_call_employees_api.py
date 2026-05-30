"""Integration tests for /api/v1/reports/calls employee endpoints."""
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

import app.extensions  # noqa: F401 - triggers private overlay
from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal, engine
from app.main import _fastapi_app

_ANCHOR_DATE_STR = "2026-05-10"
_TENANT_SLUG = "test-call-employee-reports-corp"

_SEEDED = False
_ADMIN_TOKEN = ""
_AGENT_TOKEN = ""
_TENANT_PK = 0
_ALPHA_ID = 0
_BETA_ID = 0


@pytest_asyncio.fixture(autouse=True)
async def seed_call_employee_reports_data():
    global _SEEDED, _ADMIN_TOKEN, _AGENT_TOKEN, _TENANT_PK, _ALPHA_ID, _BETA_ID

    if not any(r.path.startswith("/api/v1/reports/calls/employees") for r in _fastapi_app.routes):
        from app.extensions.reports import register as _reg

        _reg(_fastapi_app)

    if _SEEDED:
        yield
        await engine.dispose()
        return

    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                """
                INSERT INTO tenants (tenant_id, name, is_active)
                VALUES (:slug, 'Call Employee Reports Test Corp', true)
                ON CONFLICT (tenant_id) DO NOTHING
                """
            ),
            {"slug": _TENANT_SLUG},
        )
        await db.commit()
        tenant_row = await db.execute(
            text("SELECT id FROM tenants WHERE tenant_id = :slug"),
            {"slug": _TENANT_SLUG},
        )
        _TENANT_PK = tenant_row.scalar_one()

        await db.execute(text("DELETE FROM call_records WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.execute(text("DELETE FROM employees WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.commit()

        password_hash = hash_password("Test1234")
        await db.execute(
            text(
                """
                INSERT INTO employees (
                    tenant_id, username, email, password_hash, display_name,
                    name, roles, is_active
                )
                VALUES
                  (:tid, 'call_emp_alpha', 'call-alpha@test.local', :pw,
                   'Alpha Agent', 'Alpha Agent', '["admin"]'::jsonb, true),
                  (:tid, 'call_emp_beta', 'call-beta@test.local', :pw,
                   'Beta Agent', 'Beta Agent', '["agent"]'::jsonb, true),
                  (:tid, 'call_emp_gamma', 'call-gamma@test.local', :pw,
                   'Gamma Agent', 'Gamma Agent', '["agent"]'::jsonb, false)
                """
            ),
            {"tid": _TENANT_PK, "pw": password_hash},
        )
        await db.commit()

        alpha_row = await db.execute(
            text("SELECT id FROM employees WHERE username='call_emp_alpha' AND tenant_id=:tid"),
            {"tid": _TENANT_PK},
        )
        _ALPHA_ID = alpha_row.scalar_one()
        beta_row = await db.execute(
            text("SELECT id FROM employees WHERE username='call_emp_beta' AND tenant_id=:tid"),
            {"tid": _TENANT_PK},
        )
        _BETA_ID = beta_row.scalar_one()

        await db.execute(
            text(
                """
                INSERT INTO call_records (
                    tenant_id, call_id, direction, state, from_number, to_number,
                    agent_id, started_at, answered_at, ended_at, talk_duration_ms,
                    extra_metadata
                )
                VALUES
                  (:tid, 'call_emp_alpha_in_answered', 'inbound', 'completed',
                   '+1001', '+2001', :alpha_id,
                   (:anchor)::date + TIME '09:00',
                   (:anchor)::date + TIME '09:01',
                   (:anchor)::date + TIME '09:03',
                   120000, '{}'::jsonb),
                  (:tid, 'call_emp_alpha_out_answered', 'outbound', 'completed',
                   '+2001', '+1002', :alpha_id,
                   (:anchor)::date + TIME '10:00',
                   (:anchor)::date + TIME '10:01',
                   (:anchor)::date + TIME '10:05',
                   240000, '{}'::jsonb),
                  (:tid, 'call_emp_alpha_out_failed', 'outbound', 'failed',
                   '+2001', '+1003', :alpha_id,
                   (:anchor)::date + TIME '11:00',
                   NULL,
                   (:anchor)::date + TIME '11:01',
                   NULL, '{}'::jsonb),
                  (:tid, 'call_emp_beta_in_answered', 'inbound', 'completed',
                   '+1004', '+2001', :beta_id,
                   (:anchor)::date + TIME '12:00',
                   (:anchor)::date + TIME '12:01',
                   (:anchor)::date + TIME '12:02',
                   60000, '{}'::jsonb),
                  (:tid, 'call_emp_unassigned_missed', 'inbound', 'missed',
                   '+1005', '+2001', NULL,
                   (:anchor)::date + TIME '13:00',
                   NULL,
                   (:anchor)::date + TIME '13:01',
                   NULL, '{}'::jsonb)
                """
            ),
            {
                "tid": _TENANT_PK,
                "alpha_id": _ALPHA_ID,
                "beta_id": _BETA_ID,
                "anchor": date.fromisoformat(_ANCHOR_DATE_STR),
            },
        )
        await db.commit()

        _ADMIN_TOKEN = create_access_token(
            {"sub": str(_ALPHA_ID), "tenant_id": _TENANT_PK, "roles": ["admin"]}
        )
        _AGENT_TOKEN = create_access_token(
            {"sub": str(_BETA_ID), "tenant_id": _TENANT_PK, "roles": ["agent"]}
        )

    _SEEDED = True
    yield
    await engine.dispose()


def _auth(token: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token or _ADMIN_TOKEN}"}


class TestCallEmployeesListAPI:
    @pytest.mark.asyncio
    async def test_list_returns_employees_with_call_metrics(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/employees",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert data["items"][0]["employee"]["name"] == "Alpha Agent"
        assert data["items"][0]["metrics"]["total_calls"] == 3
        assert data["items"][0]["metrics"]["inbound_calls"] == 1
        assert data["items"][0]["metrics"]["answered_inbound_calls"] == 1
        assert data["items"][0]["metrics"]["outbound_calls"] == 2
        assert data["items"][0]["metrics"]["answered_outbound_calls"] == 1
        assert data["items"][0]["metrics"]["avg_inbound_talk_seconds"] == 120
        assert data["items"][0]["metrics"]["avg_outbound_talk_seconds"] == 240
        assert data["items"][1]["metrics"]["total_calls"] == 1
        assert data["items"][2]["metrics"]["total_calls"] == 0
        assert data["items"][2]["employee"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_search_filters_employees(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/employees",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "q": "Beta"},
            headers=_auth(),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["employee"]["name"] == "Beta Agent"

    @pytest.mark.asyncio
    async def test_pagination(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/employees",
            params={
                "start": _ANCHOR_DATE_STR,
                "end": _ANCHOR_DATE_STR,
                "page": 1,
                "per_page": 2,
            },
            headers=_auth(),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["pages"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_agent_role_returns_403(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/employees",
            params={"start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(_AGENT_TOKEN),
        )

        assert resp.status_code == 403


class TestCallEmployeeDetailMetricsAPI:
    @pytest.mark.asyncio
    async def test_overview_can_scope_to_employee(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/overview",
            params={
                "start": _ANCHOR_DATE_STR,
                "end": _ANCHOR_DATE_STR,
                "employee_id": _ALPHA_ID,
            },
            headers=_auth(),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_calls"] == 3
        assert data["inbound_calls"] == 1
        assert data["outbound_calls"] == 2

    @pytest.mark.asyncio
    async def test_trend_can_scope_to_employee(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/calls/trend",
            params={
                "start": _ANCHOR_DATE_STR,
                "end": _ANCHOR_DATE_STR,
                "trend": "hour",
                "employee_id": _ALPHA_ID,
            },
            headers=_auth(),
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["trend"] == "hour"
        assert len(data["buckets"]) == 24
        assert sum(bucket["metrics"]["total_calls"] for bucket in data["buckets"]) == 3
