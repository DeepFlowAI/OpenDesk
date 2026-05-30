"""Integration tests for /api/v1/reports/call-monitor."""
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

import app.extensions  # noqa: F401 - triggers private overlay
from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal, engine
from app.main import _fastapi_app

_TENANT_SLUG = "test-call-monitor-corp"
_SEEDED = False
_ADMIN_TOKEN = ""
_AGENT_TOKEN = ""
_TENANT_PK = 0
_ALPHA_ID = 0
_BETA_ID = 0
_GAMMA_ID = 0


@pytest_asyncio.fixture(autouse=True)
async def seed_call_monitor_data():
    global _SEEDED, _ADMIN_TOKEN, _AGENT_TOKEN, _TENANT_PK
    global _ALPHA_ID, _BETA_ID, _GAMMA_ID

    if not any(r.path.startswith("/api/v1/reports/call-monitor") for r in _fastapi_app.routes):
        from app.extensions.reports import register as _reg

        _reg(_fastapi_app)

    if _SEEDED:
        yield
        await engine.dispose()
        return

    base_time = datetime.now().replace(tzinfo=None, microsecond=0)
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                """
                INSERT INTO tenants (tenant_id, name, is_active)
                VALUES (:slug, 'Call Monitor Test Corp', true)
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
                  (:tid, 'call_mon_alpha', 'call-mon-alpha@test.local', :pw,
                   'Alpha Monitor', 'Alpha Monitor', '["admin"]'::jsonb, true),
                  (:tid, 'call_mon_beta', 'call-mon-beta@test.local', :pw,
                   'Beta Monitor', 'Beta Monitor', '["agent"]'::jsonb, true),
                  (:tid, 'call_mon_gamma', 'call-mon-gamma@test.local', :pw,
                   'Gamma Monitor', 'Gamma Monitor', '["agent"]'::jsonb, false),
                  (:tid, 'call_mon_delta', 'call-mon-delta@test.local', :pw,
                   'Delta Monitor', 'Delta Monitor', '["agent"]'::jsonb, false)
                """
            ),
            {"tid": _TENANT_PK, "pw": password_hash},
        )
        await db.commit()

        ids = await db.execute(
            text(
                """
                SELECT username, id
                FROM employees
                WHERE tenant_id = :tid
                  AND username IN ('call_mon_alpha', 'call_mon_beta', 'call_mon_gamma')
                """
            ),
            {"tid": _TENANT_PK},
        )
        id_map = {row.username: row.id for row in ids.all()}
        _ALPHA_ID = id_map["call_mon_alpha"]
        _BETA_ID = id_map["call_mon_beta"]
        _GAMMA_ID = id_map["call_mon_gamma"]

        await db.execute(
            text(
                """
                INSERT INTO call_records (
                    tenant_id, call_id, direction, state, from_number, to_number,
                    agent_id, started_at, answered_at, ended_at, talk_duration_ms,
                    extra_metadata
                )
                VALUES
                  (:tid, 'call_mon_alpha_in_answered', 'inbound', 'completed',
                   '+1001', '+2001', :alpha_id,
                   :alpha_in_started,
                   :alpha_in_answered,
                   :alpha_in_ended,
                   120000, '{}'::jsonb),
                  (:tid, 'call_mon_beta_in_answered', 'inbound', 'completed',
                   '+1002', '+2001', :beta_id,
                   :beta_in_started,
                   :beta_in_answered,
                   :beta_in_ended,
                   180000, '{}'::jsonb),
                  (:tid, 'call_mon_unassigned_missed', 'inbound', 'missed',
                   '+1003', '+2001', NULL,
                   :missed_started,
                   NULL,
                   :missed_ended,
                   NULL, '{}'::jsonb),
                  (:tid, 'call_mon_alpha_out_answered', 'outbound', 'completed',
                   '+2001', '+1004', :alpha_id,
                   :alpha_out_started,
                   :alpha_out_answered,
                   :alpha_out_ended,
                   240000, '{}'::jsonb),
                  (:tid, 'call_mon_alpha_out_failed', 'outbound', 'failed',
                   '+2001', '+1005', :alpha_id,
                   :alpha_failed_started,
                   NULL,
                   :alpha_failed_ended,
                   NULL, '{}'::jsonb),
                  (:tid, 'call_mon_gamma_out_answered', 'outbound', 'completed',
                   '+2001', '+1006', :gamma_id,
                   :gamma_out_started,
                   :gamma_out_answered,
                   :gamma_out_ended,
                   180000, '{}'::jsonb)
                """
            ),
            {
                "tid": _TENANT_PK,
                "alpha_id": _ALPHA_ID,
                "beta_id": _BETA_ID,
                "gamma_id": _GAMMA_ID,
                "alpha_in_started": base_time,
                "alpha_in_answered": base_time,
                "alpha_in_ended": base_time,
                "beta_in_started": base_time,
                "beta_in_answered": base_time,
                "beta_in_ended": base_time,
                "missed_started": base_time,
                "missed_ended": base_time,
                "alpha_out_started": base_time,
                "alpha_out_answered": base_time,
                "alpha_out_ended": base_time,
                "alpha_failed_started": base_time,
                "alpha_failed_ended": base_time,
                "gamma_out_started": base_time,
                "gamma_out_answered": base_time,
                "gamma_out_ended": base_time,
            },
        )
        await db.commit()

        await db.execute(
            text(
                """
                INSERT INTO agent_status (
                    tenant_id, employee_id, status, reason
                )
                VALUES
                  (:tid, :alpha_id, 'ready', NULL),
                  (:tid, :beta_id, 'busy', 'on call'),
                  (:tid, :gamma_id, 'after_call_work', NULL)
                ON CONFLICT ON CONSTRAINT uq_agent_status_tenant_employee
                DO UPDATE SET status = EXCLUDED.status, reason = EXCLUDED.reason
                """
            ),
            {
                "tid": _TENANT_PK,
                "alpha_id": _ALPHA_ID,
                "beta_id": _BETA_ID,
                "gamma_id": _GAMMA_ID,
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


class TestCallMonitorAPI:
    @pytest.mark.asyncio
    async def test_returns_today_overview_and_employee_rows(self, client: AsyncClient):
        resp = await client.get("/api/v1/reports/call-monitor", headers=_auth())

        assert resp.status_code == 200
        data = resp.json()
        assert data["today"]["total_calls"] == 6
        assert data["today"]["inbound_calls"] == 3
        assert data["today"]["answered_inbound_calls"] == 2
        assert data["today"]["outbound_calls"] == 3
        assert data["today"]["answered_outbound_calls"] == 2
        assert data["today"]["range_label"].startswith("今日 00:00 - ")
        assert "as_of" in data

        rows = {row["employee"]["username"]: row for row in data["employees"]}
        assert set(rows) == {"call_mon_alpha", "call_mon_beta", "call_mon_gamma"}
        assert rows["call_mon_alpha"]["answered_inbound_calls"] == 1
        assert rows["call_mon_alpha"]["outbound_calls"] == 2
        assert rows["call_mon_alpha"]["answered_outbound_calls"] == 1
        assert rows["call_mon_alpha"]["call_center_status"] == "ready"
        assert rows["call_mon_beta"]["answered_inbound_calls"] == 1
        assert rows["call_mon_beta"]["call_center_status"] == "busy"
        assert rows["call_mon_gamma"]["employee"]["is_active"] is False
        assert rows["call_mon_gamma"]["call_center_status"] == "after_call_work"

    @pytest.mark.asyncio
    async def test_default_sort_order_prioritizes_required_metrics(self, client: AsyncClient):
        resp = await client.get("/api/v1/reports/call-monitor", headers=_auth())

        assert resp.status_code == 200
        usernames = [row["employee"]["username"] for row in resp.json()["employees"]]
        assert usernames == ["call_mon_alpha", "call_mon_beta", "call_mon_gamma"]

    @pytest.mark.asyncio
    async def test_agent_role_returns_403(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/call-monitor",
            headers=_auth(_AGENT_TOKEN),
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/reports/call-monitor")

        assert resp.status_code == 401
