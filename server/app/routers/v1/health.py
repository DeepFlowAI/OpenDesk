"""
Health check router.

`/health` is the lightweight liveness probe — always returns 200 with the
overall status. Subsystem details (currently: FlowKit Telecom Catalog sync)
are nested under `subsystems.*` so monitoring can scrape one endpoint and
alert on staleness of any background loop.
"""
from fastapi import APIRouter


router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """Health check endpoint.

    The base liveness signal stays "ok" even when a subsystem is degraded;
    callers wanting strict gating should inspect `subsystems.*` fields.
    Returning 200 for degraded subsystems prevents load balancers from
    pulling the pod for transient FlowKit outages — the catalog stale
    window already handles graceful eviction.
    """
    subsystems: dict[str, dict | None] = {}
    # Lazy-import to avoid a circular dependency at module load time:
    # orchestrator imports from many app.services.* paths, several of
    # which transitively pull routes during application startup.
    try:
        from app.services.call_center.orchestrator import get_orchestrator

        orch = get_orchestrator()
        subsystems["telecom_catalog"] = orch.catalog_health()
    except Exception:  # noqa: BLE001 — health must never raise
        subsystems["telecom_catalog"] = {"error": "introspection_failed"}

    return {"status": "ok", "subsystems": subsystems}
