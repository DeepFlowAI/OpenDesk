"""Unit tests for filter_ringable_call_center_candidates."""
from __future__ import annotations

import pytest

from app.services.queue_resource_provider import filter_ringable_call_center_candidates
from app.services.queue_strategy import QueueCandidate


@pytest.mark.asyncio
async def test_filter_keeps_only_connected_available_agents(monkeypatch):
    candidates = [
        QueueCandidate(employee_id=1, name="web-live", available=True),
        QueueCandidate(employee_id=2, name="web-ghost", available=True),
        QueueCandidate(employee_id=3, name="busy", available=False),
    ]

    async def fake_connected(_r, _tenant_id, employee_id):
        return employee_id == 1

    monkeypatch.setattr(
        "app.services.agent_status_service.AgentStatusService.is_connected",
        fake_connected,
    )

    ringable = await filter_ringable_call_center_candidates(
        r=object(), tenant_id=7, candidates=candidates
    )
    assert [c.employee_id for c in ringable] == [1]


@pytest.mark.asyncio
async def test_filter_excludes_sip_agent_without_browser_connection(monkeypatch):
    """SIP desk-phone agents still need is_connected — same as pick_ready_agent.

    Gate/count filters must not promise agents the wait-loop picker cannot select.
    Whether SIP-only agents should be pickable without a browser is a broader
    inbound-routing question and is intentionally out of scope here.
    """
    candidates = [QueueCandidate(employee_id=9, name="sip", available=True)]

    async def fake_connected(*_a, **_k):
        return False

    monkeypatch.setattr(
        "app.services.agent_status_service.AgentStatusService.is_connected",
        fake_connected,
    )

    ringable = await filter_ringable_call_center_candidates(
        r=object(), tenant_id=7, candidates=candidates
    )
    assert ringable == []
