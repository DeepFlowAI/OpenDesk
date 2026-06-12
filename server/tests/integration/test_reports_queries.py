"""Integration tests for reports aggregation queries.

Seeds a small set of conversations + messages in a dedicated tenant, then
exercises ``fetch_overview``, ``fetch_trend`` and ``fetch_employees_overview``
against the real Postgres test DB.
"""
import importlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import text

import app.extensions  # triggers private overlay
from app.db.session import AsyncSessionLocal, engine

queries = importlib.import_module("app.extensions.reports.lib.queries")
buckets_mod = importlib.import_module("app.extensions.reports.lib.buckets")

TZ = ZoneInfo("Asia/Shanghai")

# Test scope: anchor everything to a fixed date in the recent past so the
# "session in progress (no ended_at)" branch still produces a sensible duration.
_ANCHOR_DATE_STR = "2026-05-10"  # within recent enough range
_TENANT_SLUG = "test-reports-corp"

_SEEDED = False
_TENANT_PK = 0
_AGENT_A_ID = 0
_AGENT_B_ID = 0


@pytest_asyncio.fixture(autouse=True)
async def seed_reports_data():
    """Seed data once per session; dispose engine after each test so that
    SQLAlchemy's async connection pool does not hold connections tied to a
    closed event loop (pytest-asyncio uses a fresh loop per test)."""
    global _SEEDED, _TENANT_PK, _AGENT_A_ID, _AGENT_B_ID
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

        # Wipe any conversations + messages from prior test runs so counts
        # are deterministic. ON DELETE CASCADE on conversations handles messages.
        await db.execute(text("DELETE FROM conversations WHERE tenant_id = :tid"), {"tid": _TENANT_PK})
        await db.commit()

        # Two agents
        await db.execute(text("""
            INSERT INTO employees (tenant_id, username, email, password_hash, display_name, name, roles, is_active)
            VALUES
              (:tid, 'rep_agent_a', 'a@reports.test', 'x', 'Agent A', 'Agent A', '["agent"]'::jsonb, true),
              (:tid, 'rep_agent_b', 'b@reports.test', 'x', 'Agent B', 'Agent B', '["agent"]'::jsonb, true)
            ON CONFLICT ON CONSTRAINT uq_employees_tenant_username DO NOTHING
        """), {"tid": _TENANT_PK})
        await db.commit()
        a = await db.execute(text(
            "SELECT id FROM employees WHERE username='rep_agent_a' AND tenant_id=:tid"
        ), {"tid": _TENANT_PK})
        _AGENT_A_ID = a.scalar_one()
        b = await db.execute(text(
            "SELECT id FROM employees WHERE username='rep_agent_b' AND tenant_id=:tid"
        ), {"tid": _TENANT_PK})
        _AGENT_B_ID = b.scalar_one()

        # Visitor
        await db.execute(text("""
            INSERT INTO users (tenant_id, public_id, external_id, name)
            VALUES (:tid, 'usr_reports_query_visitor', 'rep_visitor', 'Rep Visitor')
            ON CONFLICT ON CONSTRAINT uq_users_tenant_external DO NOTHING
        """), {"tid": _TENANT_PK})
        await db.commit()
        v = await db.execute(text(
            "SELECT id FROM users WHERE external_id='rep_visitor' AND tenant_id=:tid"
        ), {"tid": _TENANT_PK})
        visitor_id = v.scalar_one()

        # 3 closed conversations on _ANCHOR_DATE in tenant tz, each 10 minutes long.
        # Agent A: 2 sessions; Agent B: 1 session.
        # Bucket distribution: 2 sessions at 10:15 (hour=10), 1 session at 15:45 (hour=15).
        await db.execute(text("""
            INSERT INTO conversations (public_id, share_code, tenant_id, visitor_id, agent_id, status, started_at, ended_at, ended_by)
            VALUES
              ('cv_rep_query_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :a, 'closed',
               ((:anchor)::date + TIME '10:15')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '10:25')::timestamp AT TIME ZONE 'Asia/Shanghai', 'agent'),
              ('cv_rep_query_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :a, 'closed',
               ((:anchor)::date + TIME '10:45')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '10:55')::timestamp AT TIME ZONE 'Asia/Shanghai', 'agent'),
              ('cv_rep_query_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :b, 'closed',
               ((:anchor)::date + TIME '15:45')::timestamp AT TIME ZONE 'Asia/Shanghai',
               ((:anchor)::date + TIME '15:55')::timestamp AT TIME ZONE 'Asia/Shanghai', 'agent')
        """), {"tid": _TENANT_PK, "vid": visitor_id, "a": _AGENT_A_ID, "b": _AGENT_B_ID, "anchor": date.fromisoformat(_ANCHOR_DATE_STR)})
        await db.commit()

        # Three messages per conversation: visitor / agent / agent
        rows = await db.execute(text("""
            SELECT id FROM conversations WHERE tenant_id=:tid AND agent_id IN (:a,:b)
            ORDER BY id DESC LIMIT 3
        """), {"tid": _TENANT_PK, "a": _AGENT_A_ID, "b": _AGENT_B_ID})
        conv_ids = [r[0] for r in rows.all()]
        assert len(conv_ids) == 3

        for cid in conv_ids:
            await db.execute(text("""
                INSERT INTO messages (tenant_id, conversation_id, sender_type, content_type, content, created_at)
                VALUES
                  (:tid, :cid, 'visitor', 'text', 'hi', NOW()),
                  (:tid, :cid, 'agent',   'text', 'hello', NOW()),
                  (:tid, :cid, 'agent',   'text', 'how can I help', NOW()),
                  (:tid, :cid, 'system',  'system', 'started', NOW())
            """), {"tid": _TENANT_PK, "cid": cid})
        await db.commit()

    _SEEDED = True
    yield
    await engine.dispose()


def _range_for_anchor():
    d = date.fromisoformat(_ANCHOR_DATE_STR)
    start = datetime.combine(d, datetime.min.time(), tzinfo=TZ)
    end = start + timedelta(days=1)
    return start, end, d, d


class TestFetchOverview:

    @pytest.mark.asyncio
    async def test_overall_overview(self):
        rs, re, _, _ = _range_for_anchor()
        async with AsyncSessionLocal() as db:
            res = await queries.fetch_overview(db, _TENANT_PK, rs, re)
        assert res.session_count == 3
        # 3 visitor messages, 6 agent messages, system messages excluded
        assert res.user_message_count == 3
        assert res.agent_message_count == 6
        assert res.message_count == 9
        # ~600s per session (10 min). Allow small float drift.
        assert 595 < res.avg_duration_seconds < 605

    @pytest.mark.asyncio
    async def test_employee_a_overview(self):
        rs, re, _, _ = _range_for_anchor()
        async with AsyncSessionLocal() as db:
            res = await queries.fetch_overview(db, _TENANT_PK, rs, re, employee_id=_AGENT_A_ID)
        assert res.session_count == 2
        assert res.user_message_count == 2
        assert res.agent_message_count == 4
        assert res.message_count == 6

    @pytest.mark.asyncio
    async def test_no_data_range_returns_zeros(self):
        # A range with no sessions
        from datetime import date
        start = datetime.combine(date(2020, 1, 1), datetime.min.time(), tzinfo=TZ)
        end = start + timedelta(days=1)
        async with AsyncSessionLocal() as db:
            res = await queries.fetch_overview(db, _TENANT_PK, start, end)
        assert res.session_count == 0
        assert res.message_count == 0
        assert res.avg_duration_seconds is None


class TestFetchTrend:

    @pytest.mark.asyncio
    async def test_hour_trend_groups_at_correct_hours(self):
        rs, re, sd, ed = _range_for_anchor()
        async with AsyncSessionLocal() as db:
            res = await queries.fetch_trend(
                db, _TENANT_PK, rs, re,
                buckets_mod.TrendType.HOUR, TZ,
                range_start_date=sd, range_end_date=ed,
            )
        # 24 buckets, all 5 metrics present
        assert len(res) == 24
        # hour 10 has 2 sessions (both at 10:15 and 10:45)
        hour_10 = next(b for b in res if b.label == "10")
        assert hour_10.metrics.session_count == 2
        # hour 15 has 1 session
        hour_15 = next(b for b in res if b.label == "15")
        assert hour_15.metrics.session_count == 1
        # other hours are zero
        empty_hour = next(b for b in res if b.label == "00")
        assert empty_hour.metrics.session_count == 0

    @pytest.mark.asyncio
    async def test_half_hour_trend_groups_at_correct_half_hours(self):
        rs, re, sd, ed = _range_for_anchor()
        async with AsyncSessionLocal() as db:
            res = await queries.fetch_trend(
                db, _TENANT_PK, rs, re,
                buckets_mod.TrendType.HALF_HOUR, TZ,
                range_start_date=sd, range_end_date=ed,
            )
        assert len(res) == 48
        # 10:00 bucket holds the 10:15 session, 10:30 bucket holds the 10:45 session
        b_10_00 = next(b for b in res if b.label == "10:00")
        b_10_30 = next(b for b in res if b.label == "10:30")
        b_15_30 = next(b for b in res if b.label == "15:30")
        assert b_10_00.metrics.session_count == 1
        assert b_10_30.metrics.session_count == 1
        assert b_15_30.metrics.session_count == 1

    @pytest.mark.asyncio
    async def test_day_trend_walks_range(self):
        from datetime import date
        # 3-day range covering anchor
        sd = date.fromisoformat(_ANCHOR_DATE_STR) - timedelta(days=1)
        ed = date.fromisoformat(_ANCHOR_DATE_STR) + timedelta(days=1)
        rs = datetime.combine(sd, datetime.min.time(), tzinfo=TZ)
        re = datetime.combine(ed + timedelta(days=1), datetime.min.time(), tzinfo=TZ)
        async with AsyncSessionLocal() as db:
            res = await queries.fetch_trend(
                db, _TENANT_PK, rs, re,
                buckets_mod.TrendType.DAY, TZ,
                range_start_date=sd, range_end_date=ed,
            )
        assert [b.label for b in res] == [
            (sd + timedelta(days=i)).isoformat() for i in range(3)
        ]
        # anchor day has 3 sessions
        anchor_day = next(b for b in res if b.label == _ANCHOR_DATE_STR)
        assert anchor_day.metrics.session_count == 3


class TestFetchEmployeesOverview:

    @pytest.mark.asyncio
    async def test_returns_per_agent_breakdown(self):
        rs, re, _, _ = _range_for_anchor()
        async with AsyncSessionLocal() as db:
            res = await queries.fetch_employees_overview(db, _TENANT_PK, rs, re)
        assert _AGENT_A_ID in res
        assert _AGENT_B_ID in res
        assert res[_AGENT_A_ID].session_count == 2
        assert res[_AGENT_B_ID].session_count == 1
        assert res[_AGENT_A_ID].user_message_count == 2
        assert res[_AGENT_A_ID].agent_message_count == 4

    @pytest.mark.asyncio
    async def test_filter_by_employee_ids(self):
        rs, re, _, _ = _range_for_anchor()
        async with AsyncSessionLocal() as db:
            res = await queries.fetch_employees_overview(
                db, _TENANT_PK, rs, re, employee_ids=[_AGENT_A_ID]
            )
        assert list(res.keys()) == [_AGENT_A_ID]

    @pytest.mark.asyncio
    async def test_empty_employee_ids_returns_empty(self):
        rs, re, _, _ = _range_for_anchor()
        async with AsyncSessionLocal() as db:
            res = await queries.fetch_employees_overview(
                db, _TENANT_PK, rs, re, employee_ids=[]
            )
        assert res == {}
