"""Integration tests for /api/v1/reports/sessions/export."""
from __future__ import annotations

from datetime import date
from io import BytesIO
from zoneinfo import ZoneInfo
import zipfile

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
_TENANT_SLUG = "test-reports-export-corp"

_SEEDED = False
_ADMIN_TOKEN = ""
_AGENT_TOKEN = ""
_TENANT_PK = 0
_ADMIN_ID = 0
_AGENT_ID = 0


@pytest_asyncio.fixture(autouse=True)
async def seed():
    global _SEEDED, _ADMIN_TOKEN, _AGENT_TOKEN, _TENANT_PK, _ADMIN_ID, _AGENT_ID

    if not any(r.path == "/api/v1/reports/sessions/export" for r in _fastapi_app.routes):
        from app.extensions.reports import register as _reg
        _reg(_fastapi_app)

    if _SEEDED:
        yield
        await engine.dispose()
        return

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO tenants (tenant_id, name, is_active)
            VALUES (:slug, 'Reports Export Test Corp', true)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {"slug": _TENANT_SLUG})
        await db.commit()
        tenant = await db.execute(
            text("SELECT id FROM tenants WHERE tenant_id = :slug"),
            {"slug": _TENANT_SLUG},
        )
        _TENANT_PK = tenant.scalar_one()

        await db.execute(text("DELETE FROM conversations WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.execute(text("DELETE FROM employees WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.commit()

        password_hash = hash_password("Test1234")
        await db.execute(text("""
            INSERT INTO employees (tenant_id, username, email, password_hash, display_name, name, roles, is_active)
            VALUES
              (:tid, 'export_admin', 'export-admin@reports.test', :pw, 'Export Admin', 'Export Admin', '["admin"]'::jsonb, true),
              (:tid, 'export_agent', 'export-agent@reports.test', :pw, 'Export Agent', 'Export Agent', '["agent"]'::jsonb, true)
        """), {"tid": _TENANT_PK, "pw": password_hash})
        await db.commit()
        admin = await db.execute(
            text("SELECT id FROM employees WHERE username='export_admin' AND tenant_id=:tid"),
            {"tid": _TENANT_PK},
        )
        _ADMIN_ID = admin.scalar_one()
        agent = await db.execute(
            text("SELECT id FROM employees WHERE username='export_agent' AND tenant_id=:tid"),
            {"tid": _TENANT_PK},
        )
        _AGENT_ID = agent.scalar_one()

        await db.execute(text("""
            INSERT INTO users (tenant_id, external_id, name)
            VALUES (:tid, 'export_visitor', 'Export Visitor')
            ON CONFLICT ON CONSTRAINT uq_users_tenant_external DO NOTHING
        """), {"tid": _TENANT_PK})
        await db.commit()
        visitor = await db.execute(
            text("SELECT id FROM users WHERE external_id='export_visitor' AND tenant_id=:tid"),
            {"tid": _TENANT_PK},
        )
        visitor_id = visitor.scalar_one()

        columns = await db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'conversations'
        """))
        conversation_columns = {row[0] for row in columns.all()}
        await _insert_conversation(
            db,
            tenant_id=_TENANT_PK,
            visitor_id=visitor_id,
            agent_id=_ADMIN_ID,
            anchor=date.fromisoformat(_ANCHOR_DATE_STR),
            start_time="10:00",
            end_time="10:10",
            has_public_id="public_id" in conversation_columns,
            has_share_code="share_code" in conversation_columns,
        )
        await _insert_conversation(
            db,
            tenant_id=_TENANT_PK,
            visitor_id=visitor_id,
            agent_id=_AGENT_ID,
            anchor=date.fromisoformat(_ANCHOR_DATE_STR),
            start_time="11:00",
            end_time="11:10",
            has_public_id="public_id" in conversation_columns,
            has_share_code="share_code" in conversation_columns,
        )
        await db.commit()

        convs = await db.execute(
            text("SELECT id FROM conversations WHERE tenant_id=:tid ORDER BY id DESC LIMIT 2"),
            {"tid": _TENANT_PK},
        )
        for (conversation_id,) in convs.all():
            await db.execute(text("""
                INSERT INTO messages (tenant_id, conversation_id, sender_type, content_type, content, created_at)
                VALUES
                  (:tid, :cid, 'visitor', 'text', 'hi', NOW()),
                  (:tid, :cid, 'agent', 'text', 'hello', NOW())
            """), {"tid": _TENANT_PK, "cid": conversation_id})
        await db.commit()

        _ADMIN_TOKEN = create_access_token(
            {"sub": str(_ADMIN_ID), "tenant_id": _TENANT_PK, "roles": ["admin"]}
        )
        _AGENT_TOKEN = create_access_token(
            {"sub": str(_AGENT_ID), "tenant_id": _TENANT_PK, "roles": ["agent"]}
        )

    _SEEDED = True
    yield
    await engine.dispose()


def _auth(token: str = "") -> dict[str, str]:
    return {"Authorization": f"Bearer {token or _ADMIN_TOKEN}"}


async def _insert_conversation(
    db,
    *,
    tenant_id: int,
    visitor_id: int,
    agent_id: int,
    anchor: date,
    start_time: str,
    end_time: str,
    has_public_id: bool,
    has_share_code: bool,
) -> None:
    columns = ["tenant_id", "visitor_id", "agent_id", "status", "started_at", "ended_at", "ended_by"]
    values = [
        ":tid",
        ":vid",
        ":agent_id",
        "'closed'",
        f"((:anchor)::date + TIME '{start_time}')::timestamp AT TIME ZONE 'Asia/Shanghai'",
        f"((:anchor)::date + TIME '{end_time}')::timestamp AT TIME ZONE 'Asia/Shanghai'",
        "'agent'",
    ]
    if has_public_id:
        columns.insert(0, "public_id")
        values.insert(0, "'cv_export_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24)")
    if has_share_code:
        insert_at = 1 if has_public_id else 0
        columns.insert(insert_at, "share_code")
        values.insert(insert_at, "'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8))")

    await db.execute(
        text(f"INSERT INTO conversations ({', '.join(columns)}) VALUES ({', '.join(values)})"),
        {"tid": tenant_id, "vid": visitor_id, "agent_id": agent_id, "anchor": anchor},
    )


def _worksheet_text(content: bytes, sheet: int) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.read(f"xl/worksheets/sheet{sheet}.xml").decode("utf-8")


class TestReportsExportAPI:

    @pytest.mark.asyncio
    async def test_overall_export_returns_xlsx(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/export",
            params={"scope": "overall", "start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR, "trend": "hour"},
            headers=_auth(),
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "filename*=UTF-8''" in resp.headers["content-disposition"]
        assert resp.content.startswith(b"PK")
        assert "概览指标" in _worksheet_text(resp.content, 1)
        assert "趋势明细" in _worksheet_text(resp.content, 2)

    @pytest.mark.asyncio
    async def test_employees_export_ignores_pagination_and_keeps_accounts(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/export",
            params={
                "scope": "employees",
                "start": _ANCHOR_DATE_STR,
                "end": _ANCHOR_DATE_STR,
                "sort": "name",
                "order": "asc",
            },
            headers=_auth(),
        )

        assert resp.status_code == 200
        sheet = _worksheet_text(resp.content, 1)
        assert "员工指标列表" in sheet
        assert "export_admin" in sheet
        assert "export_agent" in sheet

    @pytest.mark.asyncio
    async def test_employee_export_requires_employee_id(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/export",
            params={"scope": "employee", "start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(),
        )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_non_admin_export_returns_403(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/reports/sessions/export",
            params={"scope": "overall", "start": _ANCHOR_DATE_STR, "end": _ANCHOR_DATE_STR},
            headers=_auth(_AGENT_TOKEN),
        )

        assert resp.status_code == 403
