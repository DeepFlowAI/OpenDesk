"""
Data access for auto outbound tasks.
"""
from datetime import date, datetime, timedelta, time, timezone

from sqlalchemy import Select, and_, case, cast, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import DATE
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auto_outbound import AutoOutboundCallRecord, AutoOutboundTarget, AutoOutboundTask
from app.models.call_record import CallRecord
from app.models.user import User


def _paginate_statement(stmt: Select, page: int, per_page: int) -> Select:
    return stmt.offset((page - 1) * per_page).limit(per_page)


def _max_policy_retries(retry_policy: dict | None) -> int:
    if not isinstance(retry_policy, dict):
        return 0
    max_retries = 0
    for item in retry_policy.values():
        if isinstance(item, dict):
            max_retries = max(max_retries, int(item.get("max_retries", 0) or 0))
    return max_retries


def _used_retry_total(retry_counts: dict | None) -> int:
    if not isinstance(retry_counts, dict):
        return 0
    return sum(int(v or 0) for v in retry_counts.values())


class AutoOutboundRepository:
    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        tenant_id: int,
        page: int,
        per_page: int,
        q: str | None = None,
        status: str | None = None,
        mode: str | None = None,
        creator_id: int | None = None,
    ) -> tuple[list[AutoOutboundTask], int]:
        filters = [AutoOutboundTask.tenant_id == tenant_id]
        if q:
            filters.append(AutoOutboundTask.name.ilike(f"%{q}%"))
        if status:
            filters.append(AutoOutboundTask.status == status)
        else:
            # Default list excludes archived tasks.
            filters.append(AutoOutboundTask.status != "archived")
        if mode:
            filters.append(AutoOutboundTask.execution_mode == mode)
        if creator_id is not None:
            filters.append(AutoOutboundTask.created_by_id == creator_id)

        stmt = select(AutoOutboundTask).where(*filters)
        count_stmt = select(func.count()).select_from(AutoOutboundTask).where(*filters)
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            _paginate_statement(stmt.order_by(AutoOutboundTask.updated_at.desc()), page, per_page)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_task(db: AsyncSession, task_id: int) -> AutoOutboundTask | None:
        return await db.get(AutoOutboundTask, task_id)

    @staticmethod
    async def get_task_for_update(
        db: AsyncSession, task_id: int
    ) -> AutoOutboundTask | None:
        result = await db.execute(
            select(AutoOutboundTask)
            .where(AutoOutboundTask.id == task_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_task(db: AsyncSession, data: dict) -> AutoOutboundTask:
        item = AutoOutboundTask(**data)
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    async def update_task(
        db: AsyncSession,
        item: AutoOutboundTask,
        data: dict,
        *,
        commit: bool = True,
    ) -> AutoOutboundTask:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        if commit:
            await db.commit()
        else:
            await db.flush()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete_task(
        db: AsyncSession, item: AutoOutboundTask, *, commit: bool = True
    ) -> None:
        await db.delete(item)
        if commit:
            await db.commit()
        else:
            await db.flush()

    @staticmethod
    async def count_targets(db: AsyncSession, tenant_id: int, task_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(AutoOutboundTarget).where(
                AutoOutboundTarget.tenant_id == tenant_id,
                AutoOutboundTarget.task_id == task_id,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def task_stats(db: AsyncSession, tenant_id: int, task_ids: list[int]) -> dict[int, dict]:
        if not task_ids:
            return {}
        result = await db.execute(
            select(
                AutoOutboundTarget.task_id,
                func.count(AutoOutboundTarget.id).label("total_targets"),
                func.count()
                .filter(AutoOutboundTarget.status.in_(["completed", "invalid"]))
                .label("finished_targets"),
                func.coalesce(func.sum(AutoOutboundTarget.call_count), 0).label("call_count"),
                func.coalesce(func.sum(AutoOutboundTarget.answered_count), 0).label("answered_count"),
            )
            .where(AutoOutboundTarget.tenant_id == tenant_id, AutoOutboundTarget.task_id.in_(task_ids))
            .group_by(AutoOutboundTarget.task_id)
        )
        stats: dict[int, dict] = {
            row.task_id: {
                "total_targets": row.total_targets,
                "finished_targets": row.finished_targets,
                "call_count": int(row.call_count or 0),
                "answered_count": int(row.answered_count or 0),
                "answer_rate": None,
                "transfer_count": 0,
                "abandon_count": 0,
            }
            for row in result
        }
        for row in stats.values():
            call_count = row["call_count"]
            answered = row["answered_count"]
            row["answer_rate"] = (answered / call_count) if call_count else None

        # transfer_count: agent reception with assigned/transferred/handoff marker.
        # abandon_count: reception_result.abandoned == true (no abandoned terminal_state).
        transfer_or_abandon = await db.execute(
            select(
                AutoOutboundCallRecord.task_id,
                func.count()
                .filter(
                    AutoOutboundCallRecord.reception_type == "agent",
                    or_(
                        AutoOutboundCallRecord.reception_result["assigned"].astext == "true",
                        AutoOutboundCallRecord.reception_result["transferred"].astext == "true",
                        AutoOutboundCallRecord.reception_result["handoff"].astext == "true",
                    ),
                )
                .label("transfer_count"),
                func.count()
                .filter(AutoOutboundCallRecord.reception_result["abandoned"].astext == "true")
                .label("abandon_count"),
            )
            .where(
                AutoOutboundCallRecord.tenant_id == tenant_id,
                AutoOutboundCallRecord.task_id.in_(task_ids),
            )
            .group_by(AutoOutboundCallRecord.task_id)
        )
        for row in transfer_or_abandon:
            bucket = stats.setdefault(
                row.task_id,
                {
                    "total_targets": 0,
                    "finished_targets": 0,
                    "call_count": 0,
                    "answered_count": 0,
                    "answer_rate": None,
                    "transfer_count": 0,
                    "abandon_count": 0,
                },
            )
            bucket["transfer_count"] = int(row.transfer_count or 0)
            bucket["abandon_count"] = int(row.abandon_count or 0)
        return stats

    @staticmethod
    async def list_targets(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        page: int,
        per_page: int,
        q: str | None = None,
        status: str | None = None,
    ) -> tuple[list[AutoOutboundTarget], int]:
        """
        List targets with ``user_name`` and ``remaining_retries`` attached.

        - user_name: LEFT JOIN users on target.user_id → users.name (None when missing)
        - remaining_retries: max(0, max_policy_retries - sum(retry_counts values))
        """
        task = await AutoOutboundRepository.get_task(db, task_id)
        max_policy = _max_policy_retries(task.retry_policy if task is not None else None)

        filters = [AutoOutboundTarget.tenant_id == tenant_id, AutoOutboundTarget.task_id == task_id]
        if q:
            filters.append(AutoOutboundTarget.phone_number.ilike(f"%{q}%"))
        if status:
            filters.append(AutoOutboundTarget.status == status)

        stmt = (
            select(AutoOutboundTarget, User.name)
            .outerjoin(User, User.id == AutoOutboundTarget.user_id)
            .where(*filters)
        )
        count_stmt = select(func.count()).select_from(AutoOutboundTarget).where(*filters)
        total = (await db.execute(count_stmt)).scalar_one()
        result = await db.execute(
            _paginate_statement(stmt.order_by(AutoOutboundTarget.updated_at.desc()), page, per_page)
        )
        items: list[AutoOutboundTarget] = []
        for target, user_name in result.all():
            # Ephemeral attributes for API serialization (not ORM columns).
            target.user_name = user_name  # type: ignore[attr-defined]
            target.remaining_retries = max(  # type: ignore[attr-defined]
                0, max_policy - _used_retry_total(target.retry_counts)
            )
            items.append(target)
        return items, total

    @staticmethod
    async def get_target(db: AsyncSession, target_id: int) -> AutoOutboundTarget | None:
        return await db.get(AutoOutboundTarget, target_id)

    @staticmethod
    async def create_target(
        db: AsyncSession, data: dict, *, commit: bool = True
    ) -> AutoOutboundTarget:
        item = AutoOutboundTarget(**data)
        db.add(item)
        if commit:
            await db.commit()
        else:
            await db.flush()
        await db.refresh(item)
        return item

    @staticmethod
    async def create_targets_bulk(
        db: AsyncSession, rows: list[dict], *, commit: bool = True
    ) -> list[AutoOutboundTarget]:
        items = [AutoOutboundTarget(**row) for row in rows]
        db.add_all(items)
        await db.flush()
        if commit:
            await db.commit()
        return items

    @staticmethod
    async def update_target(
        db: AsyncSession,
        item: AutoOutboundTarget,
        data: dict,
        *,
        commit: bool = True,
    ) -> AutoOutboundTarget:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        if commit:
            await db.commit()
        else:
            await db.flush()
        await db.refresh(item)
        return item

    @staticmethod
    async def delete_target(db: AsyncSession, item: AutoOutboundTarget) -> None:
        await db.delete(item)
        await db.commit()

    @staticmethod
    async def count_records_for_number_on_day(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        phone_number: str,
        day: date,
    ) -> int:
        day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        day_end = datetime.combine(day, time.max, tzinfo=timezone.utc)
        result = await db.execute(
            select(func.count()).select_from(AutoOutboundCallRecord).where(
                AutoOutboundCallRecord.tenant_id == tenant_id,
                AutoOutboundCallRecord.task_id == task_id,
                AutoOutboundCallRecord.phone_number == phone_number,
                AutoOutboundCallRecord.started_at >= day_start,
                AutoOutboundCallRecord.started_at <= day_end,
            )
        )
        return result.scalar_one()

    @staticmethod
    async def count_records_for_numbers_on_day(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        phone_numbers: list[str],
        day: date,
    ) -> dict[str, int]:
        if not phone_numbers:
            return {}
        day_start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        day_end = datetime.combine(day, time.max, tzinfo=timezone.utc)
        result = await db.execute(
            select(
                AutoOutboundCallRecord.phone_number,
                func.count(AutoOutboundCallRecord.id),
            )
            .where(
                AutoOutboundCallRecord.tenant_id == tenant_id,
                AutoOutboundCallRecord.task_id == task_id,
                AutoOutboundCallRecord.phone_number.in_(phone_numbers),
                AutoOutboundCallRecord.started_at >= day_start,
                AutoOutboundCallRecord.started_at <= day_end,
            )
            .group_by(AutoOutboundCallRecord.phone_number)
        )
        return {phone: count for phone, count in result.all()}

    @staticmethod
    async def list_records(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        page: int,
        per_page: int,
    ) -> tuple[list[AutoOutboundCallRecord], int]:
        filters = [
            AutoOutboundCallRecord.tenant_id == tenant_id,
            AutoOutboundCallRecord.task_id == task_id,
        ]
        total = (
            await db.execute(select(func.count()).select_from(AutoOutboundCallRecord).where(*filters))
        ).scalar_one()
        result = await db.execute(
            _paginate_statement(
                select(AutoOutboundCallRecord).where(*filters).order_by(AutoOutboundCallRecord.started_at.desc()),
                page,
                per_page,
            )
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def create_record(
        db: AsyncSession, data: dict, *, commit: bool = True
    ) -> AutoOutboundCallRecord:
        item = AutoOutboundCallRecord(**data)
        db.add(item)
        if commit:
            await db.commit()
        else:
            await db.flush()
        await db.refresh(item)
        return item

    @staticmethod
    async def daily_trend(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
    ) -> list[dict]:
        day_col = cast(AutoOutboundCallRecord.started_at, DATE).label("day")
        result = await db.execute(
            select(
                day_col,
                func.count(AutoOutboundCallRecord.id).label("call_count"),
                func.count()
                .filter(AutoOutboundCallRecord.terminal_state == "answered")
                .label("answered_count"),
            )
            .where(
                AutoOutboundCallRecord.tenant_id == tenant_id,
                AutoOutboundCallRecord.task_id == task_id,
            )
            .group_by(day_col)
            .order_by(day_col.asc())
        )
        rows = []
        for row in result:
            call_count = int(row.call_count or 0)
            answered_count = int(row.answered_count or 0)
            rows.append(
                {
                    "date": row.day,
                    "call_count": call_count,
                    "answered_count": answered_count,
                    "answer_rate": (answered_count / call_count) if call_count else None,
                }
            )
        return rows

    @staticmethod
    async def terminal_state_distribution(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
    ) -> list[dict]:
        result = await db.execute(
            select(
                AutoOutboundCallRecord.terminal_state,
                func.count(AutoOutboundCallRecord.id),
            )
            .where(
                AutoOutboundCallRecord.tenant_id == tenant_id,
                AutoOutboundCallRecord.task_id == task_id,
                AutoOutboundCallRecord.terminal_state.is_not(None),
            )
            .group_by(AutoOutboundCallRecord.terminal_state)
        )
        return [{"terminal_state": state, "count": count} for state, count in result.all()]

    @staticmethod
    async def count_in_progress_calls(db: AsyncSession, tenant_id: int, task_id: int) -> int:
        result = await db.execute(
            select(func.count()).select_from(AutoOutboundCallRecord).where(
                AutoOutboundCallRecord.tenant_id == tenant_id,
                AutoOutboundCallRecord.task_id == task_id,
                AutoOutboundCallRecord.ended_at.is_(None),
            )
        )
        return result.scalar_one()

    @staticmethod
    async def mark_targets_status(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        target_ids: list[int],
        status: str,
    ) -> int:
        result = await db.execute(
            update(AutoOutboundTarget)
            .where(
                AutoOutboundTarget.tenant_id == tenant_id,
                AutoOutboundTarget.task_id == task_id,
                AutoOutboundTarget.id.in_(target_ids),
            )
            .values(status=status)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        return result.rowcount or 0

    @staticmethod
    async def delete_targets(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
        target_ids: list[int],
    ) -> int:
        result = await db.execute(
            delete(AutoOutboundTarget).where(
                AutoOutboundTarget.tenant_id == tenant_id,
                AutoOutboundTarget.task_id == task_id,
                AutoOutboundTarget.id.in_(target_ids),
            )
        )
        await db.commit()
        return result.rowcount or 0

    # ── Dial engine helpers (Wave B1) ──────────────────────────────────────

    @staticmethod
    async def list_active_tasks(db: AsyncSession) -> list[AutoOutboundTask]:
        result = await db.execute(
            select(AutoOutboundTask).where(AutoOutboundTask.status == "active")
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_paused_tasks(db: AsyncSession) -> list[AutoOutboundTask]:
        """Paused tasks are scanned only for end_date expiry completion."""
        result = await db.execute(
            select(AutoOutboundTask).where(AutoOutboundTask.status == "paused")
        )
        return list(result.scalars().all())

    @staticmethod
    async def is_task_active(db: AsyncSession, task_id: int) -> bool:
        """Return whether a task still allows new calls to be originated."""
        result = await db.execute(
            select(AutoOutboundTask.status).where(AutoOutboundTask.id == task_id)
        )
        return result.scalar_one_or_none() == "active"

    @staticmethod
    async def claim_due_targets(
        db: AsyncSession,
        *,
        task_id: int,
        now: datetime,
        limit: int,
    ) -> list[tuple[AutoOutboundTarget, str]]:
        """
        Claim due targets with ``FOR UPDATE SKIP LOCKED``.

        Selects status IN (pending, redial_pending) where next_call_at is null
        or <= now, marks them ``calling``, and returns ``(target, previous_status)``.
        """
        if limit <= 0:
            return []
        result = await db.execute(
            select(AutoOutboundTarget)
            .where(
                AutoOutboundTarget.task_id == task_id,
                AutoOutboundTarget.status.in_(["pending", "redial_pending"]),
                or_(
                    AutoOutboundTarget.next_call_at.is_(None),
                    AutoOutboundTarget.next_call_at <= now,
                ),
            )
            .order_by(
                AutoOutboundTarget.next_call_at.asc().nullsfirst(),
                AutoOutboundTarget.id.asc(),
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(result.scalars().all())
        claimed: list[tuple[AutoOutboundTarget, str]] = []
        for row in rows:
            previous = row.status
            row.status = "calling"
            claimed.append((row, previous))
        if claimed:
            await db.commit()
            for row, _prev in claimed:
                await db.refresh(row)
        return claimed

    @staticmethod
    async def restore_claimed_targets(
        db: AsyncSession,
        claims: list[tuple[int, str]],
    ) -> int:
        """Return unprocessed claims to the status they had before claiming."""
        target_ids_by_status: dict[str, list[int]] = {
            "pending": [],
            "redial_pending": [],
        }
        for target_id, previous_status in claims:
            target_ids_by_status[previous_status].append(target_id)

        restored = 0
        for status, target_ids in target_ids_by_status.items():
            if not target_ids:
                continue
            result = await db.execute(
                update(AutoOutboundTarget)
                .where(
                    AutoOutboundTarget.id.in_(target_ids),
                    AutoOutboundTarget.status == "calling",
                )
                .values(status=status)
            )
            restored += result.rowcount or 0
        if claims:
            await db.commit()
        return restored

    @staticmethod
    async def get_record(db: AsyncSession, record_id: int) -> AutoOutboundCallRecord | None:
        return await db.get(AutoOutboundCallRecord, record_id)

    @staticmethod
    async def update_record(
        db: AsyncSession,
        item: AutoOutboundCallRecord,
        data: dict,
        *,
        commit: bool = True,
    ) -> AutoOutboundCallRecord:
        for key, value in data.items():
            if hasattr(item, key):
                setattr(item, key, value)
        if commit:
            await db.commit()
        else:
            await db.flush()
        await db.refresh(item)
        return item

    @staticmethod
    async def set_call_record_id_if_empty(
        db: AsyncSession,
        record_id: int,
        call_record_id: int,
    ) -> bool:
        """Link a CDR without clobbering a value written by a concurrent updater."""
        result = await db.execute(
            update(AutoOutboundCallRecord)
            .where(
                AutoOutboundCallRecord.id == record_id,
                AutoOutboundCallRecord.call_record_id.is_(None),
            )
            .values(call_record_id=call_record_id)
        )
        await db.commit()
        return (result.rowcount or 0) > 0

    @staticmethod
    async def list_call_record_public_ids(
        db: AsyncSession,
        tenant_id: int,
        call_record_ids: list[int],
    ) -> dict[int, str]:
        ids = sorted({call_record_id for call_record_id in call_record_ids if call_record_id})
        if not ids:
            return {}
        result = await db.execute(
            select(CallRecord.id, CallRecord.public_id).where(
                CallRecord.tenant_id == tenant_id,
                CallRecord.id.in_(ids),
            )
        )
        return {row.id: str(row.public_id) for row in result.all()}

    @staticmethod
    async def mark_answered_once(
        db: AsyncSession,
        *,
        record_id: int,
        target_id: int,
        answered_at: datetime,
        commit: bool = True,
    ) -> bool:
        """Atomically claim the first answered event and increment its target."""
        record_result = await db.execute(
            update(AutoOutboundCallRecord)
            .where(
                AutoOutboundCallRecord.id == record_id,
                AutoOutboundCallRecord.answered_at.is_(None),
                AutoOutboundCallRecord.ended_at.is_(None),
            )
            .values(answered_at=answered_at)
        )
        if record_result.rowcount != 1:
            await db.rollback()
            return False

        target_result = await db.execute(
            update(AutoOutboundTarget)
            .where(AutoOutboundTarget.id == target_id)
            .values(answered_count=AutoOutboundTarget.answered_count + 1)
        )
        if target_result.rowcount != 1:
            await db.rollback()
            return False

        if commit:
            await db.commit()
        else:
            await db.flush()
        return True

    @staticmethod
    async def finalize_record_once(
        db: AsyncSession,
        *,
        record_id: int,
        ended_at: datetime,
        duration_ms: int,
        terminal_state: str,
        fail_reason: str | None,
        commit: bool = True,
    ) -> str | None:
        """Atomically claim terminal handling and return the persisted terminal state."""
        resolved_terminal = case(
            (AutoOutboundCallRecord.answered_at.is_not(None), "answered"),
            else_=terminal_state,
        )
        resolved_fail_reason = case(
            (AutoOutboundCallRecord.answered_at.is_not(None), None),
            else_=fail_reason,
        )
        result = await db.execute(
            update(AutoOutboundCallRecord)
            .where(
                AutoOutboundCallRecord.id == record_id,
                AutoOutboundCallRecord.ended_at.is_(None),
            )
            .values(
                ended_at=ended_at,
                duration_ms=duration_ms,
                terminal_state=resolved_terminal,
                fail_reason=resolved_fail_reason,
            )
            .returning(AutoOutboundCallRecord.terminal_state)
        )
        persisted_terminal = result.scalar_one_or_none()
        if persisted_terminal is None:
            await db.rollback()
            return None

        if commit:
            await db.commit()
        else:
            await db.flush()
        return str(persisted_terminal)

    @staticmethod
    async def count_targets_by_status(
        db: AsyncSession,
        task_id: int,
        *,
        statuses: list[str],
    ) -> int:
        if not statuses:
            return 0
        result = await db.execute(
            select(func.count()).select_from(AutoOutboundTarget).where(
                AutoOutboundTarget.task_id == task_id,
                AutoOutboundTarget.status.in_(statuses),
            )
        )
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_records_for_stats(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
    ) -> list[AutoOutboundCallRecord]:
        result = await db.execute(
            select(AutoOutboundCallRecord).where(
                AutoOutboundCallRecord.tenant_id == tenant_id,
                AutoOutboundCallRecord.task_id == task_id,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def abandon_counts(
        db: AsyncSession,
        tenant_id: int,
        task_id: int,
    ) -> dict[str, int]:
        """Count answered vs abandoned (reception_result.abandoned == true)."""
        result = await db.execute(
            select(
                AutoOutboundCallRecord.answered_at,
                AutoOutboundCallRecord.reception_result,
            ).where(
                AutoOutboundCallRecord.tenant_id == tenant_id,
                AutoOutboundCallRecord.task_id == task_id,
            )
        )
        answered = 0
        abandoned = 0
        for answered_at, reception_result in result.all():
            if answered_at is not None:
                answered += 1
            if isinstance(reception_result, dict) and reception_result.get("abandoned") is True:
                abandoned += 1
        return {"answered": answered, "abandoned": abandoned}

    @staticmethod
    async def list_stale_calling_targets(
        db: AsyncSession,
        *,
        updated_before: datetime,
        limit: int = 200,
    ) -> list[AutoOutboundTarget]:
        """Targets stuck in ``calling`` with updated_at older than the cutoff."""
        if updated_before.tzinfo is None:
            updated_before = updated_before.replace(tzinfo=timezone.utc)
        result = await db.execute(
            select(AutoOutboundTarget)
            .where(
                AutoOutboundTarget.status == "calling",
                AutoOutboundTarget.updated_at < updated_before,
            )
            .order_by(AutoOutboundTarget.updated_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_open_record_for_target(
        db: AsyncSession,
        *,
        target_id: int,
    ) -> AutoOutboundCallRecord | None:
        """Latest call record for a target that has not reached a terminal state."""
        result = await db.execute(
            select(AutoOutboundCallRecord)
            .where(
                AutoOutboundCallRecord.target_id == target_id,
                AutoOutboundCallRecord.terminal_state.is_(None),
            )
            .order_by(AutoOutboundCallRecord.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_record_for_task(
        db: AsyncSession,
        *,
        tenant_id: int,
        task_id: int,
        record_id: int,
        for_update: bool = False,
    ) -> AutoOutboundCallRecord | None:
        statement = select(AutoOutboundCallRecord).where(
            AutoOutboundCallRecord.id == record_id,
            AutoOutboundCallRecord.tenant_id == tenant_id,
            AutoOutboundCallRecord.task_id == task_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_record_by_call_record_id(
        db: AsyncSession,
        *,
        tenant_id: int,
        task_id: int | None = None,
        call_record_id: int,
    ) -> AutoOutboundCallRecord | None:
        conditions = [
            AutoOutboundCallRecord.tenant_id == tenant_id,
            AutoOutboundCallRecord.call_record_id == call_record_id,
        ]
        if task_id is not None:
            conditions.append(AutoOutboundCallRecord.task_id == task_id)
        result = await db.execute(
            select(AutoOutboundCallRecord)
            .where(*conditions)
            .order_by(AutoOutboundCallRecord.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_records_by_call_record_ids(
        db: AsyncSession,
        *,
        tenant_id: int,
        call_record_ids: list[int],
    ) -> dict[int, AutoOutboundCallRecord]:
        if not call_record_ids:
            return {}
        result = await db.execute(
            select(AutoOutboundCallRecord)
            .where(
                AutoOutboundCallRecord.tenant_id == tenant_id,
                AutoOutboundCallRecord.call_record_id.in_(call_record_ids),
            )
            .order_by(
                AutoOutboundCallRecord.started_at.desc(),
                AutoOutboundCallRecord.id.desc(),
            )
        )
        records: dict[int, AutoOutboundCallRecord] = {}
        for record in result.scalars().all():
            call_record_id = record.call_record_id
            if call_record_id is not None and call_record_id not in records:
                records[call_record_id] = record
        return records

    @staticmethod
    async def list_agent_records_for_phone(
        db: AsyncSession,
        *,
        tenant_id: int,
        task_id: int,
        phone_number: str,
        agent_id: int,
        limit: int = 20,
    ) -> list[AutoOutboundCallRecord]:
        result = await db.execute(
            select(AutoOutboundCallRecord)
            .where(
                AutoOutboundCallRecord.tenant_id == tenant_id,
                AutoOutboundCallRecord.task_id == task_id,
                AutoOutboundCallRecord.phone_number == phone_number,
                AutoOutboundCallRecord.agent_id == agent_id,
            )
            .order_by(AutoOutboundCallRecord.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
