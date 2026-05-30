"""
Unit tests for FlowKit Catalog sync wire shape.

Validates the dict-shape we PUT to FlowKit, without hitting the network.
The network path is exercised via the real FlowKit kernel in higher-level
integration runs (excluded from `pytest` per dev-workflow §4.5.2).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.libs.telephony.providers.flowkit.telecom_client import (
    TelecomAPIError,
)
from app.services.call_center.catalog_sync import CatalogSyncService


@pytest.mark.asyncio
async def test_push_snapshot_increments_revision():
    """Each push_snapshot bumps the revision (monotonic across the process)."""
    client = MagicMock()
    client.put_snapshot = AsyncMock(return_value={"revision": 1, "trunk_count": 0})
    client.provider_id = "opendesk-test"

    sync = CatalogSyncService(
        telecom_client=client,
        lease_ttl_sec=90,
        stale_acceptable_sec=30,
    )
    # Bypass DB by stubbing the row-builder
    sync._build_wire_trunks = AsyncMock(return_value=[])

    await sync.push_snapshot()
    first_rev = client.put_snapshot.await_args.kwargs["revision"]
    await sync.push_snapshot()
    second_rev = client.put_snapshot.await_args.kwargs["revision"]

    assert second_rev > first_rev


@pytest.mark.asyncio
async def test_push_snapshot_passes_lease_and_stale():
    client = MagicMock()
    client.put_snapshot = AsyncMock(return_value={"revision": 1, "trunk_count": 0})
    client.provider_id = "opendesk-test"

    sync = CatalogSyncService(
        telecom_client=client,
        lease_ttl_sec=120,
        stale_acceptable_sec=45,
    )
    sync._build_wire_trunks = AsyncMock(return_value=[])

    await sync.push_snapshot()
    kwargs = client.put_snapshot.await_args.kwargs
    assert kwargs["lease_ttl_sec"] == 120
    assert kwargs["stale_acceptable_sec"] == 45


@pytest.mark.asyncio
async def test_stop_is_noop_when_not_started():
    """Calling stop() before start() must not raise (orchestrator shutdown)."""
    client = MagicMock()
    client.aclose = AsyncMock()
    client.delete = AsyncMock()
    client.provider_id = "opendesk-test"

    sync = CatalogSyncService(
        telecom_client=client,
        lease_ttl_sec=90,
        stale_acceptable_sec=30,
    )
    await sync.stop()  # not started → no-op
    client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_lease_expired_event_logged_as_warning(caplog):
    """telecom.trunk.deregistered with reason=lease_expired should warn-log
    (admin signal: a Provider went silent). Other reasons stay at info."""
    from app.libs.telephony.base import CallEvent
    import logging

    client = MagicMock()
    client.provider_id = "opendesk-test"
    sync = CatalogSyncService(
        telecom_client=client,
        lease_ttl_sec=90,
        stale_acceptable_sec=30,
    )

    with caplog.at_level(logging.WARNING, logger="app.services.call_center.catalog_sync"):
        await sync.on_trunk_deregistered(
            CallEvent(
                method="telecom.trunk.deregistered",
                data={"trunk_id": "trunk_x", "reason": "lease_expired"},
            )
        )
    assert any("lease_expired" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_build_wire_trunks_derives_outbound_from_peer_endpoints():
    """Outbound trunks: catalog snapshot's outbound.server/port comes from
    peer_endpoints[0] — same gateway handles inbound + outbound."""
    from types import SimpleNamespace
    from unittest.mock import patch

    client = MagicMock()
    client.provider_id = "opendesk-test"
    sync = CatalogSyncService(
        telecom_client=client, lease_ttl_sec=90, stale_acceptable_sec=30,
    )

    rows = [
        SimpleNamespace(
            id="t1", trunk_types=["inbound", "outbound"], status="enabled",
            peer_endpoints=[{"ip": "120.33.34.240", "port": 5060}],
        ),
        SimpleNamespace(
            id="t2", trunk_types=["inbound"], status="enabled",
            peer_endpoints=[{"ip": "36.152.234.146", "port": 5060}],
        ),
    ]

    class _Session:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return None
        async def execute(self, _stmt):
            class _R:
                @staticmethod
                def scalars():
                    class _S:
                        @staticmethod
                        def all():
                            return rows
                    return _S()
            return _R()

    with patch(
        "app.services.call_center.catalog_sync.AsyncSessionLocal", _Session,
    ):
        wire = await sync._build_wire_trunks()

    assert len(wire) == 2
    t1 = next(w for w in wire if w["id"] == "t1")
    assert t1["outbound"] == {"server": "120.33.34.240", "port": 5060}
    t2 = next(w for w in wire if w["id"] == "t2")
    assert "outbound" not in t2


@pytest.mark.asyncio
async def test_build_wire_trunks_demotes_outbound_without_endpoints():
    """Declared outbound but no peer_endpoints → demoted to inbound-only."""
    from types import SimpleNamespace
    from unittest.mock import patch

    client = MagicMock()
    client.provider_id = "opendesk-test"
    sync = CatalogSyncService(
        telecom_client=client, lease_ttl_sec=90, stale_acceptable_sec=30,
    )
    rows = [SimpleNamespace(
        id="bad", trunk_types=["outbound"], status="enabled", peer_endpoints=[],
    )]

    class _Session:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return None
        async def execute(self, _stmt):
            class _R:
                @staticmethod
                def scalars():
                    class _S:
                        @staticmethod
                        def all():
                            return rows
                    return _S()
            return _R()

    with patch(
        "app.services.call_center.catalog_sync.AsyncSessionLocal", _Session,
    ):
        wire = await sync._build_wire_trunks()
    assert "outbound" not in wire[0]["trunk_types"]


def test_telecom_api_error_repr():
    err = TelecomAPIError(409, {"error": "stale_revision"})
    assert "409" in str(err)
    assert err.status == 409


# ─────────────── Observability + watchdog ───────────────


@pytest.mark.asyncio
async def test_health_snapshot_before_any_activity():
    client = MagicMock()
    client.provider_id = "opendesk-test"
    sync = CatalogSyncService(
        telecom_client=client, lease_ttl_sec=90, stale_acceptable_sec=30,
    )
    snap = sync.health_snapshot()
    assert snap["provider_id"] == "opendesk-test"
    assert snap["started"] is False
    assert snap["last_heartbeat_age_sec"] is None
    assert snap["last_heartbeat_error"] is None
    assert snap["heartbeat_restart_count"] == 0
    assert snap["heartbeat_task_alive"] is False


@pytest.mark.asyncio
async def test_health_snapshot_records_snapshot_age():
    client = MagicMock()
    client.put_snapshot = AsyncMock(return_value={"revision": 1, "trunk_count": 0})
    client.provider_id = "opendesk-test"
    sync = CatalogSyncService(
        telecom_client=client, lease_ttl_sec=90, stale_acceptable_sec=30,
    )
    sync._build_wire_trunks = AsyncMock(return_value=[])
    await sync.push_snapshot()
    snap = sync.health_snapshot()
    assert snap["last_snapshot_age_sec"] is not None
    assert snap["last_snapshot_error"] is None


@pytest.mark.asyncio
async def test_health_snapshot_records_snapshot_error():
    client = MagicMock()
    client.put_snapshot = AsyncMock(side_effect=TelecomAPIError(409, "stale"))
    client.provider_id = "opendesk-test"
    sync = CatalogSyncService(
        telecom_client=client, lease_ttl_sec=90, stale_acceptable_sec=30,
    )
    sync._build_wire_trunks = AsyncMock(return_value=[])
    with pytest.raises(TelecomAPIError):
        await sync.push_snapshot()
    snap = sync.health_snapshot()
    assert snap["last_snapshot_error"] is not None
    assert "409" in snap["last_snapshot_error"]


@pytest.mark.asyncio
async def test_watchdog_respawns_dead_heartbeat():
    """If the heartbeat task ends (we simulate by replacing it with a done
    Future), the watchdog must respawn it and increment the restart counter."""
    import asyncio as aio

    client = MagicMock()
    client.put_snapshot = AsyncMock(return_value={"revision": 1, "trunk_count": 0})
    client.heartbeat = AsyncMock(return_value={})
    client.delete = AsyncMock()
    client.aclose = AsyncMock()
    client.provider_id = "opendesk-test"

    sync = CatalogSyncService(
        telecom_client=client, lease_ttl_sec=90, stale_acceptable_sec=30,
    )
    sync._build_wire_trunks = AsyncMock(return_value=[])
    # Speed the watchdog up for the test (default 60s).
    sync._WATCHDOG_INTERVAL_SEC = 0.05

    await sync.start()
    try:
        # Simulate "heartbeat task died" by force-cancelling it.
        sync._heartbeat_task.cancel()
        try:
            await sync._heartbeat_task
        except aio.CancelledError:
            pass

        # Wait long enough for the watchdog to wake and respawn.
        deadline = aio.get_event_loop().time() + 1.0
        while aio.get_event_loop().time() < deadline:
            if sync._heartbeat_restart_count >= 1:
                break
            await aio.sleep(0.02)

        assert sync._heartbeat_restart_count >= 1
        assert sync._heartbeat_task is not None
        assert not sync._heartbeat_task.done()
    finally:
        await sync.stop()
