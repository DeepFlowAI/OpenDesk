"""
Bulk SMS send engine: scans scheduled/sending tasks, claims pending targets
in batches, submits them through the SMS channel and advances task state.

DB sessions are held only around claim/persist steps — never across channel
calls (see CLAUDE.md §8). A crashed worker is recovered by sweeping targets
stuck in `sending` back to `pending`.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.configs.settings import settings
from app.db.session import AsyncSessionLocal
from app.libs.sms import get_sms_client
from app.libs.sms.base import SmsSendResult
from app.models.sms import (
    SMS_SEND_SOURCE_BULK,
    SMS_SEND_STATUS_FAILED,
    SMS_SEND_STATUS_PENDING,
    SMS_SEND_STATUS_SUBMITTED,
)
from app.models.sms_bulk_task import (
    SMS_BULK_PAUSE_REASON_CHANNEL_ERROR,
    SMS_BULK_TASK_STATUS_PAUSED,
    SMS_BULK_TASK_STATUS_SENDING,
)
from app.repositories.sms_bulk_task_repository import SmsBulkTargetRepository, SmsBulkTaskRepository
from app.repositories.sms_repository import SmsSendRecordRepository
from app.services.sms_service import _format_fail_reason, _render_body_snapshot

logger = logging.getLogger(__name__)


class SmsBulkSendService:
    @staticmethod
    async def run_tick() -> dict:
        """One engine iteration: start due tasks, sweep stale claims, send batches."""
        now = datetime.now(timezone.utc)
        stats = {"started": 0, "swept": 0, "sent": 0, "failed": 0, "completed": 0, "auto_paused": 0}

        async with AsyncSessionLocal() as db:
            due_ids = await SmsBulkTaskRepository.list_due_scheduled(db, now)
        for task_id in due_ids:
            async with AsyncSessionLocal() as db:
                if await SmsBulkTaskRepository.start_scheduled_task(db, task_id, now):
                    stats["started"] += 1

        # A claimed row must outlive the worst-case batch send duration,
        # otherwise the sweep reclaims rows a live worker is still sending.
        stale_seconds = max(
            settings.SMS_BULK_SEND_CLAIM_STALE_SECONDS,
            settings.SMS_BULK_SEND_BATCH_SIZE * settings.SMS_BULK_SEND_TIMEOUT_SECONDS + 60,
        )
        stale_before = now - timedelta(seconds=stale_seconds)
        async with AsyncSessionLocal() as db:
            stats["swept"] = await SmsBulkTargetRepository.sweep_stale_claimed(
                db, stale_before=stale_before, now=now
            )

        async with AsyncSessionLocal() as db:
            sending_ids = await SmsBulkTaskRepository.list_sending_task_ids(db)
        for task_id in sending_ids:
            outcome = await SmsBulkSendService._process_task(task_id, now)
            stats["sent"] += outcome["sent"]
            stats["failed"] += outcome["failed"]
            stats["auto_paused"] += outcome["auto_paused"]
            async with AsyncSessionLocal() as db:
                if await SmsBulkTaskRepository.complete_if_finished(db, task_id, datetime.now(timezone.utc)):
                    stats["completed"] += 1
        return stats

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    async def _process_task(task_id: int, now: datetime) -> dict:
        outcome = {"sent": 0, "failed": 0, "auto_paused": 0}
        async with AsyncSessionLocal() as db:
            task = await SmsBulkTaskRepository.get_by_id(db, task_id)
            if task is None:
                return outcome
            snapshot = {
                "tenant_id": task.tenant_id,
                "template_id": task.template_id,
                "template_name": task.template_name,
                "template_type": task.template_type,
                "sign_name": task.sign_name,
                "provider_sign_name": task.provider_sign_name,
                "body": task.body,
                "provider": task.provider,
                "provider_template_code": task.provider_template_code,
                "created_by_id": task.created_by_id,
            }
            targets = await SmsBulkTargetRepository.claim_pending_targets(
                db, task_id=task_id, limit=settings.SMS_BULK_SEND_BATCH_SIZE, now=now
            )
            claimed = [
                {"id": target.id, "phone": target.phone, "variable_values": target.variable_values or {}}
                for target in targets
            ]

        consecutive_failures = 0
        for item in claimed:
            if consecutive_failures >= settings.SMS_BULK_SEND_AUTO_PAUSE_CONSECUTIVE_FAILURES:
                await SmsBulkSendService._auto_pause(task_id)
                outcome["auto_paused"] = 1
                break
            success = await SmsBulkSendService._send_one(task_id, snapshot, item)
            if success is None:
                # Task left `sending` mid-batch (manual pause/archive); stop
                # now and release the rest of this claim back to pending.
                async with AsyncSessionLocal() as db:
                    await SmsBulkTargetRepository.release_task_claimed(
                        db, task_id=task_id, now=datetime.now(timezone.utc)
                    )
                break
            if success:
                outcome["sent"] += 1
                consecutive_failures = 0
            else:
                outcome["failed"] += 1
                consecutive_failures += 1
        return outcome

    @staticmethod
    async def _send_one(task_id: int, snapshot: dict, item: dict) -> bool | None:
        """Persist a send record, call the channel without a DB session, then persist the result.

        Returns None when the task is no longer sending — nothing was sent and
        the caller should stop the batch.
        """
        now = datetime.now(timezone.utc)
        params = item["variable_values"]
        async with AsyncSessionLocal() as db:
            if await SmsBulkTaskRepository.get_status(db, task_id) != SMS_BULK_TASK_STATUS_SENDING:
                return None
            record = await SmsSendRecordRepository.create(
                db,
                {
                    "tenant_id": snapshot["tenant_id"],
                    "phone": item["phone"],
                    "template_id": snapshot["template_id"],
                    "template_name": snapshot["template_name"],
                    "template_type": snapshot["template_type"],
                    "sign_name": snapshot["sign_name"],
                    "body_snapshot": _render_body_snapshot(snapshot["body"], params),
                    "variables_snapshot": params,
                    "status": SMS_SEND_STATUS_PENDING,
                    "employee_id": snapshot["created_by_id"],
                    "source": SMS_SEND_SOURCE_BULK,
                    "bulk_task_id": task_id,
                    "provider": snapshot["provider"],
                },
            )
            await db.commit()
            record_id = record.id
            await SmsBulkTargetRepository.bind_send_record(db, target_id=item["id"], record_id=record_id)

        try:
            result = await asyncio.wait_for(
                get_sms_client().send_sms(
                    phone=item["phone"],
                    sign_name=snapshot["provider_sign_name"],
                    template_code=snapshot["provider_template_code"],
                    template_params=params,
                ),
                timeout=settings.SMS_BULK_SEND_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("Bulk SMS channel call timed out (task_id=%s target_id=%s)", task_id, item["id"])
            result = SmsSendResult(success=False, error_code="TIMEOUT", error_message="channel call timed out")
        except Exception as exc:  # defensive: never leave the target stuck
            logger.exception("Bulk SMS channel call raised (task_id=%s target_id=%s)", task_id, item["id"])
            result = SmsSendResult(success=False, error_code="INTERNAL", error_message=str(exc)[:200])

        finished_at = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            if result.success:
                await SmsSendRecordRepository.update_send_result(
                    db, record_id=record_id, status=SMS_SEND_STATUS_SUBMITTED, biz_id=result.biz_id
                )
                await SmsBulkTargetRepository.mark_submitted(
                    db, target_id=item["id"], biz_id=result.biz_id, now=finished_at
                )
                return True
            fail_reason = _format_fail_reason(result.error_code, result.error_message)
            await SmsSendRecordRepository.update_send_result(
                db,
                record_id=record_id,
                status=SMS_SEND_STATUS_FAILED,
                biz_id=result.biz_id,
                fail_reason=fail_reason,
            )
            await SmsBulkTargetRepository.mark_failed(
                db, target_id=item["id"], fail_reason=fail_reason, now=finished_at
            )
            return False

    @staticmethod
    async def _auto_pause(task_id: int) -> None:
        """Pause a task whose channel calls keep failing; release claimed targets."""
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            await SmsBulkTargetRepository.release_task_claimed(db, task_id=task_id, now=now)
            task = await SmsBulkTaskRepository.get_by_id(db, task_id)
            if task is not None and task.status == SMS_BULK_TASK_STATUS_SENDING:
                await SmsBulkTaskRepository.update(
                    db,
                    task,
                    {
                        "status": SMS_BULK_TASK_STATUS_PAUSED,
                        "pause_reason": SMS_BULK_PAUSE_REASON_CHANNEL_ERROR,
                    },
                )
        logger.warning("Bulk SMS task auto-paused on consecutive channel failures (task_id=%s)", task_id)
