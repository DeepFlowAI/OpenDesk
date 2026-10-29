"""Database access for persisted call queue facts."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_queue_fact import CallQueueOffer, CallQueueVisit


class CallQueueFactRepository:
    """Upsert queue facts by immutable source event identifiers."""

    @staticmethod
    async def upsert_visits(db: AsyncSession, rows: list[dict]) -> dict[str, int]:
        visit_ids: dict[str, int] = {}
        mutable = {
            "exited_event_id",
            "queue_name_snapshot",
            "entry_kind",
            "exited_at",
            "wait_duration_ms",
            "result",
            "result_reliable",
            "is_short_abandon",
        }
        for row in rows:
            statement = insert(CallQueueVisit).values(**row)
            statement = statement.on_conflict_do_update(
                index_elements=[CallQueueVisit.entered_event_id],
                set_={key: getattr(statement.excluded, key) for key in mutable}
                | {"updated_at": func.now()},
            ).returning(CallQueueVisit.id)
            visit_id = (await db.execute(statement)).scalar_one()
            visit_ids[row["entered_event_id"]] = int(visit_id)
        return visit_ids

    @staticmethod
    async def upsert_offers(
        db: AsyncSession,
        rows: list[dict],
        visit_ids: dict[str, int],
    ) -> None:
        mutable = {
            "ended_event_id",
            "operation_id",
            "agent_id",
            "agent_ref_id",
            "agent_name_snapshot",
            "ended_at",
            "duration_ms",
            "result",
            "result_reliable",
        }
        for source_row in rows:
            row = dict(source_row)
            visit_event_id = row.pop("visit_entered_event_id")
            visit_id = visit_ids.get(visit_event_id)
            if visit_id is None:
                continue
            row["queue_visit_id"] = visit_id
            statement = insert(CallQueueOffer).values(**row)
            statement = statement.on_conflict_do_update(
                index_elements=[CallQueueOffer.started_event_id],
                set_={key: getattr(statement.excluded, key) for key in mutable}
                | {
                    "queue_visit_id": statement.excluded.queue_visit_id,
                    "updated_at": func.now(),
                },
            )
            await db.execute(statement)
