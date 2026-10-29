"""Durable export execution and authenticated file delivery."""
import asyncio
import hashlib
import logging
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import PurePath
from uuid import UUID

from app.core.exceptions import BusinessError
from app.db.session import AsyncSessionLocal
from app.libs.export_types import get_export_type
from app.libs.storage import create_storage_client
from app.repositories.export_task_repository import ExportTaskRepository as Repo
from app.schemas.permission import EffectivePrincipal
from app.services.employee_session_service import EmployeeSessionService
from app.services.export_task_service import ExportTaskService, effective_status, export_error

logger = logging.getLogger(__name__)


class ExportStopped(Exception):
    """The persisted task is no longer executing."""


class ExportTaskWorker:
    @staticmethod
    async def checkpoint(task_id: UUID) -> None:
        async with AsyncSessionLocal() as db:
            task = await Repo.get(db, task_id)
            if not task or task.status != "running":
                raise ExportStopped()
            if task.started_at <= datetime.now(timezone.utc) - timedelta(minutes=30):
                raise TimeoutError()

    @staticmethod
    async def fail(task_id: UUID, code: str, states: tuple[str, ...] = ("running",)) -> None:
        async with AsyncSessionLocal() as db:
            await Repo.transition(db, task_id, states, dict(
                status="failed", error_code=code, completed_at=datetime.now(timezone.utc),
            ))
            await db.commit()

    @staticmethod
    async def generate(task_id: UUID) -> None:
        async with AsyncSessionLocal() as db:
            task = await Repo.get(db, task_id)
            if not task or task.status != "running":
                return
            snapshot, key, kind_name = task.snapshot, task.storage_key, task.kind
            owner = EffectivePrincipal(user_id=task.employee_id, tenant_id=task.tenant_id)
        principal = await ExportTaskService.current(owner)
        kind = get_export_type(kind_name)
        if not kind or not principal.has_all_permissions(list(kind.permissions)):
            raise export_error("permission_lost", 403)
        result = await kind.generate(snapshot, principal, lambda: ExportTaskWorker.checkpoint(task_id))
        await ExportTaskWorker.checkpoint(task_id)
        if not result.data or result.row_count < 0 or len(result.data) > kind.max_file_bytes:
            raise export_error("file_limit")
        filename = result.filename
        if (not filename or len(filename) > 255 or PurePath(filename).name != filename
                or "\\" in filename or any(ord(char) < 32 for char in filename)
                or not result.content_type or len(result.content_type) > 128
                or any(ord(char) < 32 for char in result.content_type)):
            raise export_error("configuration_invalid")
        # Authorize even header-only files and catch access changes during generation.
        principal = await ExportTaskService.current(owner)
        if not principal.has_all_permissions(list(kind.permissions)):
            raise export_error("permission_lost", 403)
        if not await kind.can_download(principal, snapshot, result.manifest):
            raise export_error("access_changed", 403)
        storage = create_storage_client()
        await storage.upload_private(key, result.data, result.content_type)
        await ExportTaskWorker.checkpoint(task_id)
        principal = await ExportTaskService.current(owner)
        if not principal.has_all_permissions(list(kind.permissions)):
            raise export_error("permission_lost", 403)
        if not await kind.can_download(principal, snapshot, result.manifest):
            raise export_error("access_changed", 403)
        # The conditional write is the only place an upload becomes downloadable.
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            await Repo.transition(db, task_id, ("running",), dict(
                status="completed", completed_at=now, expires_at=now + timedelta(days=7),
                row_count=result.row_count, file_name=filename, content_type=result.content_type,
                file_size=len(result.data), file_sha256=hashlib.sha256(result.data).hexdigest(),
                manifest=result.manifest, scope_reduced=result.scope_reduced,
            ))
            await db.commit()

    @staticmethod
    async def execute(task_id: UUID) -> None:
        work = asyncio.create_task(ExportTaskWorker.generate(task_id))
        try:
            async with asyncio.timeout(30 * 60):
                while not work.done():
                    await asyncio.wait({work}, timeout=1)
                    if not work.done():
                        await ExportTaskWorker.checkpoint(task_id)
                await work
        except ExportStopped:
            pass
        except TimeoutError:
            await ExportTaskWorker.fail(task_id, "execution_timeout")
        except BusinessError as exc:
            code = exc.code.removeprefix("EXPORT_").lower()
            allowed = {"permission_lost", "access_changed", "configuration_invalid", "file_limit", "row_limit", "column_limit"}
            if code.startswith("cell_limit_") and code.removeprefix("cell_limit_").isdigit():
                allowed.add(code)
            await ExportTaskWorker.fail(task_id, code if code in allowed else "permission_lost"
                                        if exc.status_code in (401, 403) else "generation_failed")
        except asyncio.CancelledError:
            # A terminated worker leaves a durable running job for timeout recovery.
            raise
        except Exception:
            logger.exception("Export execution failed task_id=%s", task_id)
            await ExportTaskWorker.fail(task_id, "generation_failed")
        finally:
            if not work.done():
                work.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await work

    @staticmethod
    async def cleanup() -> None:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            tasks = await Repo.cleanup_candidates(db, now)
            candidates = [(task.id, task.storage_key) for task in tasks]
        if candidates:
            storage = create_storage_client()
            for task_id, key in candidates:
                try:
                    await storage.delete(key)
                    async with AsyncSessionLocal() as db:
                        await Repo.cleaned(db, task_id, now)
                        await db.commit()
                except Exception:
                    logger.exception("Export cleanup failed task_id=%s", task_id)
        async with AsyncSessionLocal() as db:
            await Repo.prune(db, now)
            await db.commit()

    @staticmethod
    async def run() -> None:
        running: set[asyncio.Task] = set()
        cleanup_at = datetime.min.replace(tzinfo=timezone.utc)
        try:
            while True:
                for work in tuple(running):
                    if work.done():
                        running.remove(work)
                        if not work.cancelled() and work.exception():
                            logger.error("Export worker task failed", exc_info=work.exception())
                try:
                    now = datetime.now(timezone.utc)
                    async with AsyncSessionLocal() as db:
                        await Repo.expire_timeouts(db, now)
                        await db.commit()
                    if now >= cleanup_at:
                        await ExportTaskWorker.cleanup()
                        cleanup_at = now + timedelta(minutes=1)
                    while len(running) < 2:
                        async with AsyncSessionLocal() as db:
                            task = await Repo.claim_next(db, datetime.now(timezone.utc))
                            task_id = task.id if task else None
                            await db.commit()
                        if task_id is None:
                            break
                        running.add(asyncio.create_task(ExportTaskWorker.execute(task_id)))
                except Exception:
                    logger.exception("Export scheduler scan failed")
                await asyncio.sleep(5)
        finally:
            for work in running:
                work.cancel()
            await asyncio.gather(*running, return_exceptions=True)

    @staticmethod
    async def authorized_file(principal: EffectivePrincipal, task_id: UUID) -> object:
        principal = await ExportTaskService.current(principal)
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            task = await Repo.get_owned(db, principal.tenant_id, principal.user_id, task_id, now)
        if not task:
            raise export_error("not_found", 404)
        status = effective_status(task, now)
        if status != "completed":
            raise export_error("expired" if status == "expired" else "file_unavailable", 409)
        kind = get_export_type(task.kind)
        if (task.error_code == "access_changed" or not kind or not principal.has_all_permissions(list(kind.permissions))
                or not await kind.can_download(principal, task.snapshot, task.manifest or {})):
            async with AsyncSessionLocal() as db:
                await Repo.transition(db, task_id, ("completed",), {"error_code": "access_changed"})
                await db.commit()
            raise export_error("access_changed", 403)
        return task

    @staticmethod
    async def download(principal: EffectivePrincipal, task_id: UUID, user_payload: dict) -> str:
        task = await ExportTaskWorker.authorized_file(principal, task_id)
        if not task.storage_key or not task.file_size or not task.file_name:
            await ExportTaskWorker.fail(task_id, "file_unavailable", ("completed",))
            raise export_error("file_unavailable", 409)
        async with AsyncSessionLocal() as db:
            await EmployeeSessionService.validate_payload(db, user_payload)
        # Signed links remain usable until expiry, even if access is later revoked.
        expires_seconds = min(120, int((task.expires_at - datetime.now(timezone.utc)).total_seconds()))
        if expires_seconds <= 0:
            raise export_error("expired", 409)
        try:
            return await create_storage_client().get_temporary_url(
                task.storage_key, expires_seconds=expires_seconds, download_name=task.file_name,
            )
        except Exception:
            logger.exception("Export download signing failed task_id=%s", task_id)
            raise export_error("download_failed", 503) from None
