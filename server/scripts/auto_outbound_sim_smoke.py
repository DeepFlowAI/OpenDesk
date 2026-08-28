#!/usr/bin/env python3
"""
Local smoke helper for auto-outbound simulation mode.

Usage (from server/):
  # Syntax / import check (no DB):
  python scripts/auto_outbound_sim_smoke.py --dry-run

  # Live demo against local DATABASE_URL (simulation must be enabled):
  python scripts/auto_outbound_sim_smoke.py --seconds 15
  python scripts/auto_outbound_sim_smoke.py --seconds 15 --keep

Requires AUTO_OUTBOUND_SIMULATION_ENABLED=true in env (or server/.env.dev /
private/env/server.env.dev). Does not call FlowKit.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def _ensure_sys_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


async def _dry_run() -> int:
    """Import + construct engine/simulator without touching the database."""
    from app.configs.settings import ENV, settings
    from app.services.auto_outbound.engine import AutoOutboundDialEngine
    from app.services.auto_outbound.pacing import DefaultPacingResolver
    from app.services.auto_outbound.simulator import CallSimulator, SimulationProfile, profile_from_settings

    print("auto_outbound_sim_smoke dry-run")
    print(f"  APP_ENV={ENV}")
    print(f"  SIMULATION_ENABLED={settings.AUTO_OUTBOUND_SIMULATION_ENABLED}")
    print(f"  DIAL_WORKER_ENABLED={settings.AUTO_OUTBOUND_DIAL_WORKER_ENABLED}")
    print(f"  ANSWER_RATE={settings.AUTO_OUTBOUND_SIMULATION_ANSWER_RATE}")
    print(f"  DATABASE_URL set={bool(getattr(settings, 'DATABASE_URL', None))}")

    profile = profile_from_settings()
    sim = CallSimulator(
        profile=SimulationProfile(
            answer_rate=profile.answer_rate,
            min_ring_seconds=0.0,
            max_ring_seconds=0.0,
            min_talk_seconds=0.0,
            max_talk_seconds=0.0,
            weight_no_answer=profile.weight_no_answer,
            weight_busy=profile.weight_busy,
            weight_power_off=profile.weight_power_off,
            weight_invalid=profile.weight_invalid,
        )
    )
    engine = AutoOutboundDialEngine(
        redis=None,
        pacing_resolver=DefaultPacingResolver(),
        simulator=sim,
    )
    print(f"  engine={type(engine).__name__} simulator={type(sim).__name__}")
    print("dry-run ok")
    return 0


async def _live(seconds: float, keep: bool) -> int:
    from app.configs.settings import settings
    from app.db.session import AsyncSessionLocal
    from app.models.auto_outbound import AutoOutboundTask
    from app.repositories.auto_outbound_repository import AutoOutboundRepository
    from app.services.auto_outbound.engine import AutoOutboundDialEngine
    from app.services.auto_outbound.pacing import DefaultPacingResolver
    from app.services.auto_outbound.simulator import CallSimulator, profile_from_settings
    from sqlalchemy import select

    if not settings.AUTO_OUTBOUND_SIMULATION_ENABLED:
        print(
            "ERROR: AUTO_OUTBOUND_SIMULATION_ENABLED is false. "
            "Enable it in private/env/server.env.dev (or .env.dev) before live smoke.",
            file=sys.stderr,
        )
        return 2

    demo_name = f"[sim-smoke] {datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    tenant_id = 1
    task_id: int | None = None

    async with AsyncSessionLocal() as db:
        task = await AutoOutboundRepository.create_task(
            db,
            {
                "tenant_id": tenant_id,
                "name": demo_name,
                "template_name": "sim-smoke",
                "fields": [],
                "status": "active",
                "execution_mode": "ivr",
                "voice_flow_id": 0,
                "voice_flow_name": "sim",
                "start_date": date.today() - timedelta(days=1),
                "end_date": date.today() + timedelta(days=7),
                "daily_time_windows": [{"start": "00:00", "end": "23:59"}],
                "caller_number_id": None,
                "max_concurrency": 3,
                "retry_policy": {"no_answer": {"max_retries": 0, "interval_minutes": 1}},
                "daily_per_number_limit": 3,
                "wrapup_seconds": 60,
                "started_at": datetime.now(timezone.utc),
            },
        )
        task_id = task.id
        for i in range(5):
            await AutoOutboundRepository.create_target(
                db,
                {
                    "tenant_id": tenant_id,
                    "task_id": task.id,
                    "phone_number": f"1990000{i:04d}",
                    "status": "pending",
                    "field_values": {"source": "sim-smoke"},
                    "retry_counts": {},
                },
            )
        print(f"created demo task id={task_id} name={demo_name!r} targets=5")

    profile = profile_from_settings()
    sim = CallSimulator(profile=profile)
    engine = AutoOutboundDialEngine(
        pacing_resolver=DefaultPacingResolver(),
        simulator=sim,
    )

    deadline = asyncio.get_event_loop().time() + max(1.0, seconds)
    ticks = 0
    while asyncio.get_event_loop().time() < deadline:
        stats = await engine.scan_once()
        ticks += 1
        print(f"  tick={ticks} stats={stats}")
        await asyncio.sleep(max(0.2, float(settings.AUTO_OUTBOUND_DIAL_SCAN_INTERVAL_SECONDS)))

    await sim.drain(timeout=10.0)

    async with AsyncSessionLocal() as db:
        records = await AutoOutboundRepository.list_records_for_stats(db, tenant_id, task_id)
        terminals = Counter(r.terminal_state or "pending" for r in records)
        answered = terminals.get("answered", 0)
        total = sum(terminals.values()) or 1
        task = await AutoOutboundRepository.get_task(db, task_id)
        print("── results ──")
        print(f"  task_status={task.status if task else None}")
        print(f"  records={len(records)} terminals={dict(terminals)}")
        print(f"  answer_rate={answered / total:.2%}")

        if not keep and task is not None:
            # Soft cleanup: archive task; leave rows for audit unless deleted by ops.
            await AutoOutboundRepository.update_task(
                db, task, {"status": "archived", "name": f"{demo_name} (archived)"}
            )
            print(f"  cleaned: task {task_id} archived (use --keep to retain active/demo status)")
        elif keep:
            print(f"  kept demo task id={task_id}")

    return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_sys_path()
    parser = argparse.ArgumentParser(description="Auto-outbound simulation smoke helper")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only validate imports / settings (no database)",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=10.0,
        help="How long to run the dial engine in live mode",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Do not archive the demo task after live run",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        return asyncio.run(_dry_run())
    return asyncio.run(_live(args.seconds, args.keep))


if __name__ == "__main__":
    raise SystemExit(main())
