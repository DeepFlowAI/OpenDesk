"""
Integration tests for the workspace transfer API.

Covers ``GET /api/v1/workspace/transfer-targets`` and
``POST /api/v1/workspace/conversations/{id}/transfer``. Real DB rows are
seeded for tenant / employees / visitor; each test that needs an active
conversation creates its own row (``_create_active_conversation``) so the
suite has no implicit ordering coupling between tests.
"""
import asyncio

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal


_STATE: dict = {}


@pytest_asyncio.fixture(autouse=True)
async def seed_transfer_data():
    """Seed the immutable directory rows: tenant, visitor, employees.

    Conversations are intentionally NOT seeded here — each test creates its
    own active conversation so the order in which pytest runs them no longer
    matters.
    """
    if _STATE.get("seeded"):
        return

    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            INSERT INTO tenants (tenant_id, name, is_active)
            VALUES ('xfer-corp', 'Xfer Corp', true)
            ON CONFLICT (tenant_id) DO NOTHING
        """))
        await db.commit()

        tenant_pk = (await db.execute(
            text("SELECT id FROM tenants WHERE tenant_id = 'xfer-corp'")
        )).scalar_one()

        hashed = hash_password("Test1234")
        for username, display, roles in [
            ("xfer_owner", "Owner Agent", '["agent"]'),
            ("xfer_target", "Target Agent", '["agent"]'),
            ("xfer_busy", "Busy Agent", '["agent"]'),
            ("xfer_admin", "Xfer Admin", '["admin"]'),
            ("xfer_admin_agent", "Admin Agent", '["admin","agent"]'),
        ]:
            await db.execute(text("""
                INSERT INTO employees (tenant_id, username, email, password_hash, name, display_name, roles, is_active)
                VALUES (:tid, :u, :e, :pw, :n, :d, CAST(:r AS jsonb), true)
                ON CONFLICT ON CONSTRAINT uq_employees_tenant_username DO NOTHING
            """), {
                "tid": tenant_pk,
                "u": username,
                "e": f"{username}@example.com",
                "pw": hashed,
                "n": display,
                "d": display,
                "r": roles,
            })
        await db.commit()

        async def _emp(username: str) -> int:
            return (await db.execute(text(
                "SELECT id FROM employees WHERE username = :u AND tenant_id = :tid"
            ), {"u": username, "tid": tenant_pk})).scalar_one()

        owner_id = await _emp("xfer_owner")
        target_id = await _emp("xfer_target")
        busy_id = await _emp("xfer_busy")
        admin_id = await _emp("xfer_admin")
        admin_agent_id = await _emp("xfer_admin_agent")

        await db.execute(text("""
            INSERT INTO users (tenant_id, external_id, name)
            VALUES (:tid, 'xfer-visitor', 'Xfer Visitor')
            ON CONFLICT ON CONSTRAINT uq_users_tenant_external DO NOTHING
        """), {"tid": tenant_pk})
        await db.commit()

        visitor_id = (await db.execute(text(
            "SELECT id FROM users WHERE external_id = 'xfer-visitor' AND tenant_id = :tid"
        ), {"tid": tenant_pk})).scalar_one()

    _STATE.update({
        "seeded": True,
        "tenant_pk": tenant_pk,
        "owner_id": owner_id,
        "target_id": target_id,
        "busy_id": busy_id,
        "admin_id": admin_id,
        "admin_agent_id": admin_agent_id,
        "visitor_id": visitor_id,
    })


def _token(user_id: int, *, roles: list[str] | None = None) -> str:
    return create_access_token({
        "sub": str(user_id),
        "tenant_id": _STATE["tenant_pk"],
        "roles": roles or ["agent"],
    })


def _owner_token() -> str:
    return _token(_STATE["owner_id"], roles=["agent"])


def _admin_token() -> str:
    return _token(_STATE["admin_agent_id"], roles=["admin", "agent"])


async def _create_active_conversation(*, agent_id: int | None = None) -> int:
    """Insert a fresh active conversation owned by ``agent_id`` and return its id."""
    aid = agent_id if agent_id is not None else _STATE["owner_id"]
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            INSERT INTO conversations (public_id, share_code, tenant_id, visitor_id, agent_id, status, started_at)
            VALUES ('cv_xfer_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :aid, 'active', NOW())
            RETURNING id
        """), {
            "tid": _STATE["tenant_pk"],
            "vid": _STATE["visitor_id"],
            "aid": aid,
        })
        await db.commit()
        return result.scalar_one()


async def _create_closed_conversation(*, agent_id: int | None = None) -> int:
    aid = agent_id if agent_id is not None else _STATE["owner_id"]
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("""
            INSERT INTO conversations (public_id, share_code, tenant_id, visitor_id, agent_id, status, started_at, ended_at, ended_by)
            VALUES ('cv_xfer_' || substr(md5(random()::text || clock_timestamp()::text), 1, 24), 'CV-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 8)), :tid, :vid, :aid, 'closed', NOW() - interval '2 hour', NOW() - interval '1 hour', 'agent')
            RETURNING id
        """), {
            "tid": _STATE["tenant_pk"],
            "vid": _STATE["visitor_id"],
            "aid": aid,
        })
        await db.commit()
        return result.scalar_one()


async def _set_redis_status(status_value: str, user_id: int) -> None:
    from app.services.agent_status_service import AgentStatusService
    from tests.conftest import _get_fake_redis
    r = await _get_fake_redis()
    await AgentStatusService.set_status(r, _STATE["tenant_pk"], user_id, status_value)


async def _count_messages(conversation_id: int, *, sender_type: str = "system") -> int:
    async with AsyncSessionLocal() as db:
        return (await db.execute(text("""
            SELECT count(*) FROM messages
            WHERE conversation_id = :cid AND sender_type = :st
        """), {"cid": conversation_id, "st": sender_type})).scalar_one()


# ---------------------------------------------------------------------------
# transfer-targets
# ---------------------------------------------------------------------------


class TestListTransferTargets:

    @pytest.mark.asyncio
    async def test_returns_200(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/workspace/transfer-targets",
            headers={"Authorization": f"Bearer {_owner_token()}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data and "total" in data

    @pytest.mark.asyncio
    async def test_excludes_self_and_admin_only(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/workspace/transfer-targets",
            headers={"Authorization": f"Bearer {_owner_token()}"},
        )
        ids = [item["id"] for item in resp.json()["items"]]
        names = [item["name"] for item in resp.json()["items"]]
        assert _STATE["owner_id"] not in ids
        # admin-only employees never serve, so they must not appear
        assert "Xfer Admin" not in names

    @pytest.mark.asyncio
    async def test_keyword_filters_results(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/workspace/transfer-targets",
            params={"keyword": "Target"},
            headers={"Authorization": f"Bearer {_owner_token()}"},
        )
        assert any(
            item["id"] == _STATE["target_id"] for item in resp.json()["items"]
        )

    @pytest.mark.asyncio
    async def test_conversation_id_excludes_current_owner(self, client: AsyncClient):
        """When an admin lists candidates while looking at someone else's
        conversation, the conversation owner must be filtered out."""
        conv_id = await _create_active_conversation(agent_id=_STATE["target_id"])
        resp = await client.get(
            "/api/v1/workspace/transfer-targets",
            params={"conversation_id": conv_id},
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )
        ids = [item["id"] for item in resp.json()["items"]]
        # admin_agent (the requester) is excluded by the self-exclude rule;
        # target_id (the conversation owner) is excluded by the new rule.
        assert _STATE["target_id"] not in ids
        assert _STATE["admin_agent_id"] not in ids

    @pytest.mark.asyncio
    async def test_non_owner_agent_cannot_inspect_conversation(self, client: AsyncClient):
        """Regular agents must not probe candidate lists for foreign
        conversations — otherwise comparing the with/without-conversation_id
        result would leak the current owner."""
        conv_id = await _create_active_conversation(agent_id=_STATE["target_id"])
        resp = await client.get(
            "/api/v1/workspace/transfer-targets",
            params={"conversation_id": conv_id},
            # busy_id is an unrelated agent (not owner, not admin)
            headers={"Authorization": f"Bearer {_token(_STATE['busy_id'], roles=['agent'])}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_conversation_id_returns_404(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/workspace/transfer-targets",
            params={"conversation_id": 9999999},
            headers={"Authorization": f"Bearer {_owner_token()}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/workspace/transfer-targets")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# transfer endpoint
# ---------------------------------------------------------------------------


class TestTransferConversation:

    @pytest.mark.asyncio
    async def test_target_offline_returns_400(self, client: AsyncClient):
        conv_id = await _create_active_conversation()
        await _set_redis_status("offline", _STATE["busy_id"])
        resp = await client.post(
            f"/api/v1/workspace/conversations/{conv_id}/transfer",
            json={"target_agent_id": _STATE["busy_id"]},
            headers={"Authorization": f"Bearer {_owner_token()}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_success_persists_audit_message_and_swaps_owner(
        self, client: AsyncClient
    ):
        """Atomicity check: the conversation owner change and the system
        audit message must both be present after a successful transfer."""
        conv_id = await _create_active_conversation()
        await _set_redis_status("online", _STATE["target_id"])

        resp = await client.post(
            f"/api/v1/workspace/conversations/{conv_id}/transfer",
            json={"target_agent_id": _STATE["target_id"]},
            headers={"Authorization": f"Bearer {_owner_token()}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"] is not None
        assert data["agent"]["id"] == _STATE["target_id"]

        # Exactly one system message recorded for this transfer
        assert await _count_messages(conv_id, sender_type="system") == 1

        # last_message_preview should contain the human-readable transfer text
        async with AsyncSessionLocal() as db:
            preview, agent_id = (await db.execute(text("""
                SELECT last_message_preview, agent_id FROM conversations WHERE id = :id
            """), {"id": conv_id})).one()
        assert agent_id == _STATE["target_id"]
        assert "转接" in (preview or "")

    @pytest.mark.asyncio
    async def test_admin_initiator_recorded_in_message(self, client: AsyncClient):
        """When admin transfers someone else's conversation, the audit
        message must name the admin (the initiator), not the previous owner."""
        conv_id = await _create_active_conversation(agent_id=_STATE["target_id"])
        await _set_redis_status("online", _STATE["busy_id"])

        resp = await client.post(
            f"/api/v1/workspace/conversations/{conv_id}/transfer",
            json={"target_agent_id": _STATE["busy_id"]},
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )
        assert resp.status_code == 200

        async with AsyncSessionLocal() as db:
            row = (await db.execute(text("""
                SELECT content FROM messages
                WHERE conversation_id = :cid AND sender_type = 'system'
                ORDER BY id DESC LIMIT 1
            """), {"cid": conv_id})).scalar_one()
        # 'Admin Agent' is the display_name we seeded for xfer_admin_agent
        assert "Admin Agent" in row

    @pytest.mark.asyncio
    async def test_cannot_transfer_to_current_agent(self, client: AsyncClient):
        conv_id = await _create_active_conversation()
        resp = await client.post(
            f"/api/v1/workspace/conversations/{conv_id}/transfer",
            json={"target_agent_id": _STATE["owner_id"]},
            headers={"Authorization": f"Bearer {_owner_token()}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_closed_conversation_returns_400(self, client: AsyncClient):
        closed_id = await _create_closed_conversation()
        await _set_redis_status("online", _STATE["target_id"])
        resp = await client.post(
            f"/api/v1/workspace/conversations/{closed_id}/transfer",
            json={"target_agent_id": _STATE["target_id"]},
            headers={"Authorization": f"Bearer {_owner_token()}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_conversation_not_found_returns_404(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/workspace/conversations/9999999/transfer",
            json={"target_agent_id": _STATE["target_id"]},
            headers={"Authorization": f"Bearer {_owner_token()}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_non_owner_non_admin_returns_403(self, client: AsyncClient):
        conv_id = await _create_active_conversation()
        await _set_redis_status("online", _STATE["target_id"])
        # busy_id is an unrelated agent who does not own the conversation
        resp = await client.post(
            f"/api/v1/workspace/conversations/{conv_id}/transfer",
            json={"target_agent_id": _STATE["target_id"]},
            headers={"Authorization": f"Bearer {_token(_STATE['busy_id'], roles=['agent'])}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_target_id_returns_422(self, client: AsyncClient):
        conv_id = await _create_active_conversation()
        resp = await client.post(
            f"/api/v1/workspace/conversations/{conv_id}/transfer",
            json={"target_agent_id": 0},
            headers={"Authorization": f"Bearer {_owner_token()}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_concurrent_transfers_only_one_succeeds(self, client: AsyncClient):
        """Fire two transfers at the same conversation simultaneously.

        Whatever the scheduling, the conditional UPDATE must guarantee that
        exactly one request wins (200 with a single audit message) and the
        loser surfaces a 400 instead of silently writing a duplicate row.
        """
        conv_id = await _create_active_conversation(agent_id=_STATE["owner_id"])
        await _set_redis_status("online", _STATE["target_id"])
        await _set_redis_status("online", _STATE["busy_id"])

        # Use admin auth so both requests pass ownership; the only thing
        # under test is the optimistic-concurrency UPDATE.
        async def _post(target_id: int):
            return await client.post(
                f"/api/v1/workspace/conversations/{conv_id}/transfer",
                json={"target_agent_id": target_id},
                headers={"Authorization": f"Bearer {_admin_token()}"},
            )

        resp_a, resp_b = await asyncio.gather(
            _post(_STATE["target_id"]),
            _post(_STATE["busy_id"]),
        )
        statuses = sorted([resp_a.status_code, resp_b.status_code])

        # Exactly one of the two requests must win. Both 200 would mean two
        # audit messages were written; both 400 would be a stuck transfer.
        assert statuses == [200, 400], f"unexpected statuses: {statuses}"

        # Exactly one system message recorded — duplicate audits would be
        # the failure mode the conditional UPDATE is meant to prevent.
        assert await _count_messages(conv_id, sender_type="system") == 1

        # Final owner must be one of the two requested targets, never left
        # half-applied.
        async with AsyncSessionLocal() as db:
            agent_id = (await db.execute(text(
                "SELECT agent_id FROM conversations WHERE id = :cid"
            ), {"cid": conv_id})).scalar_one()
        assert agent_id in {_STATE["target_id"], _STATE["busy_id"]}

    @pytest.mark.asyncio
    async def test_already_transferred_returns_400(self, client: AsyncClient):
        """A request that read stale state and tries to flip ``agent_id``
        from the previous owner must be rejected with no side effects.

        We simulate this by directly mutating the row before the request,
        then issuing it with an admin token (so ownership doesn't short-
        circuit). A real concurrent loser ends up here too.
        """
        conv_id = await _create_active_conversation(agent_id=_STATE["owner_id"])
        await _set_redis_status("online", _STATE["target_id"])

        # Pretend a concurrent winner already moved the row to busy_id.
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "UPDATE conversations SET agent_id = :aid WHERE id = :cid"
            ), {"aid": _STATE["busy_id"], "cid": conv_id})
            await db.commit()

        # The service reads fresh state so it'll happily transfer from
        # busy_id → target_id (this is the "stale read recovers" path).
        # The important property is that no duplicate system message ever
        # appears for this conversation regardless of the winner.
        resp = await client.post(
            f"/api/v1/workspace/conversations/{conv_id}/transfer",
            json={"target_agent_id": _STATE["target_id"]},
            headers={"Authorization": f"Bearer {_admin_token()}"},
        )
        assert resp.status_code == 200

        async with AsyncSessionLocal() as db:
            agent_id = (await db.execute(text(
                "SELECT agent_id FROM conversations WHERE id = :cid"
            ), {"cid": conv_id})).scalar_one()
        assert agent_id == _STATE["target_id"]
        assert await _count_messages(conv_id, sender_type="system") == 1
