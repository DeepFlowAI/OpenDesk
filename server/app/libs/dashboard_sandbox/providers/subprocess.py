"""Dashboard sandbox provider backed by a resource-limited Python process."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import resource
import signal
import sys
from pathlib import Path

from app.core.exceptions import ValidationError
from app.libs.dashboard_sandbox.base import (
    CancelChecker,
    QueryHandler,
    SandboxExecutionError,
    SandboxLimits,
    SandboxResult,
)
from app.libs.dashboard_sandbox.runner import CodeValidationError, validate_code

logger = logging.getLogger(__name__)


class SubprocessDashboardSandbox:
    """Execute validated component code in an isolated child interpreter."""

    async def execute(
        self,
        *,
        code: str,
        context: dict,
        filters: dict,
        query_handler: QueryHandler,
        cancel_checker: CancelChecker,
        limits: SandboxLimits,
    ) -> SandboxResult:
        try:
            validate_code(code)
        except CodeValidationError as exc:
            raise SandboxExecutionError("unsafe_code", exc.message, line=exc.line) from exc

        runner_path = Path(__file__).resolve().parents[1] / "runner.py"
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            str(runner_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            preexec_fn=_resource_limiter(limits),
        )
        assert process.stdin is not None
        assert process.stdout is not None
        process.stdin.write(
            (
                json.dumps(
                    {"code": code, "context": context, "filters": filters},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
        )
        await process.stdin.drain()

        query_count = 0
        loop = asyncio.get_running_loop()
        deadline = loop.time() + limits.wall_seconds
        try:
            while True:
                raw = await _readline_with_cancel(
                    process,
                    deadline=deadline,
                    cancel_checker=cancel_checker,
                )
                if not raw:
                    return_code = await process.wait()
                    if return_code < 0 and -return_code in {signal.SIGKILL, signal.SIGXCPU}:
                        raise SandboxExecutionError(
                            "resource_limit",
                            "Component exceeded its CPU or memory limit",
                        )
                    raise SandboxExecutionError("runtime_error", "Sandbox process ended unexpectedly")
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise SandboxExecutionError("runtime_error", "Invalid sandbox response") from exc

                match message.get("type"):
                    case "query":
                        query_count += 1
                        if query_count > limits.max_queries:
                            await _send_query_response(
                                process,
                                message,
                                ok=False,
                                error="Component query limit exceeded",
                            )
                            continue
                        remaining = deadline - loop.time()
                        if remaining <= 0:
                            raise asyncio.TimeoutError
                        try:
                            # Bound each query by the remaining wall budget so a slow
                            # database call cannot outlive the component deadline.
                            result = await asyncio.wait_for(
                                query_handler(
                                    str(message.get("method") or ""),
                                    message.get("params") or {},
                                ),
                                timeout=remaining,
                            )
                        except asyncio.TimeoutError:
                            raise
                        except ValidationError as exc:
                            await _send_query_response(
                                process,
                                message,
                                ok=False,
                                error=exc.message[:300] or "Query failed",
                            )
                        except Exception:
                            # Internal failures (e.g. database errors) may embed SQL or
                            # infrastructure details; only log them server-side.
                            logger.warning("Dashboard component query failed", exc_info=True)
                            await _send_query_response(
                                process,
                                message,
                                ok=False,
                                error="Query failed",
                            )
                        else:
                            await _send_query_response(process, message, ok=True, result=result)
                    case "result":
                        logs = str(message.get("logs") or "")
                        encoded_logs = logs.encode("utf-8")
                        truncated = len(encoded_logs) > limits.max_log_bytes
                        if truncated:
                            logs = encoded_logs[: limits.max_log_bytes].decode("utf-8", errors="ignore")
                        await process.wait()
                        return SandboxResult(
                            output=message.get("result"),
                            logs=logs,
                            query_count=query_count,
                            truncated=truncated,
                        )
                    case "error":
                        raise SandboxExecutionError(
                            str(message.get("code") or "runtime_error"),
                            str(message.get("message") or "Component failed")[:500],
                            line=message.get("line"),
                        )
                    case _:
                        raise SandboxExecutionError("runtime_error", "Unknown sandbox response")
        except asyncio.TimeoutError as exc:
            raise SandboxExecutionError("runtime_timeout", "Component execution timed out") from exc
        finally:
            if process.returncode is None:
                _terminate_process(process)
                try:
                    await asyncio.wait_for(process.wait(), timeout=1)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()


def _resource_limiter(limits: SandboxLimits):
    def apply_limits() -> None:
        cpu_soft = max(1, math.ceil(limits.cpu_seconds))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_soft, cpu_soft + 1))
        memory_bytes = limits.memory_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except (OSError, ValueError):
            # macOS reserves a very large virtual address space before exec;
            # Linux production workers enforce RLIMIT_AS normally.
            pass
        resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))

    return apply_limits


async def _readline_with_cancel(
    process: asyncio.subprocess.Process,
    *,
    deadline: float,
    cancel_checker: CancelChecker,
) -> bytes:
    assert process.stdout is not None
    loop = asyncio.get_running_loop()
    read_task = asyncio.create_task(process.stdout.readline())
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            done, _ = await asyncio.wait({read_task}, timeout=min(0.1, remaining))
            if done:
                return read_task.result()
            if await cancel_checker():
                raise SandboxExecutionError("cancelled", "Component execution was cancelled")
    finally:
        if not read_task.done():
            read_task.cancel()


async def _send_query_response(
    process: asyncio.subprocess.Process,
    request: dict,
    *,
    ok: bool,
    result: object | None = None,
    error: str | None = None,
) -> None:
    assert process.stdin is not None
    payload = {"id": request.get("id"), "ok": ok}
    if ok:
        payload["result"] = result
    else:
        payload["error"] = error or "Query failed"
    process.stdin.write(
        (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    )
    await process.stdin.drain()


def _terminate_process(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
