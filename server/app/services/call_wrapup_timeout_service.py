"""Server-side sweep that ends after-call work when its deadline passes.

The wrap-up countdown must not depend on the agent's browser: a closed tab or
lost connection still has to free the agent for new calls. This worker scans
the Redis resource hashes, flips expired ``after_call_work`` resources back to
ready, syncs the persistent status, and pushes a socket event so an open
workbench exits the wrap-up panel immediately.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis

from app.constants.call_center import CcSocketEvent
from app.core.exceptions import ConflictError
from app.db.session import AsyncSessionLocal
from app.services.call_center.agent_notify import emit_to_agent
from app.services.cc_agent_resource_service import CcAgentResourceService
from app.services.cc_agent_status_service import CcAgentStatusService

logger = logging.getLogger(__name__)


class CallWrapupTimeoutService:
    @staticmethod
    async def process_expired(redis: aioredis.Redis, *, limit: int = 200) -> int:
        expired = await CcAgentResourceService.list_expired_wrapups(redis, limit=limit)
        processed = 0
        for tenant_id, employee_id, call_id in expired:
            try:
                await CcAgentResourceService.set_visible_status(
                    redis, tenant_id, employee_id, "ready"
                )
            except ConflictError:
                # A new call was reserved between the scan and the flip; the
                # agent is occupied again and no longer needs the sweep.
                continue
            except Exception:
                logger.exception(
                    "wrap-up timeout: redis flip failed tenant=%s employee=%s",
                    tenant_id,
                    employee_id,
                )
                continue
            try:
                async with AsyncSessionLocal() as db:
                    from app.services.call_agent_fact_service import CallAgentFactService

                    try:
                        await CallAgentFactService.close_after_call_work(
                            db,
                            tenant_id=tenant_id,
                            agent_id=employee_id,
                            call_id=call_id,
                            end_reason="timeout",
                        )
                    except Exception:
                        logger.exception(
                            "wrap-up timeout: fact close failed tenant=%s employee=%s",
                            tenant_id,
                            employee_id,
                        )
                    await CcAgentStatusService.sync_pg_status(
                        db,
                        tenant_id,
                        employee_id,
                        "ready",
                        reason="wrap_up_timeout",
                    )
            except Exception:
                logger.exception(
                    "wrap-up timeout: pg sync failed tenant=%s employee=%s",
                    tenant_id,
                    employee_id,
                )
            await emit_to_agent(
                tenant_id=tenant_id,
                employee_id=employee_id,
                method=CcSocketEvent.WRAP_UP_TIMEOUT.value,
                payload={"call_id": call_id},
            )
            processed += 1
        return processed
