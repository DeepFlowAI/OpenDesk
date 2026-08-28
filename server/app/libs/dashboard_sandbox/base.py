"""Contracts shared by dashboard sandbox providers."""

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol


QueryHandler = Callable[[str, dict], Awaitable[object]]
CancelChecker = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class SandboxLimits:
    """Per-component operating-system and protocol limits."""

    wall_seconds: float = 8.0
    cpu_seconds: int = 2
    memory_mb: int = 128
    max_queries: int = 8
    max_log_bytes: int = 16 * 1024


@dataclass(frozen=True)
class SandboxResult:
    """Successful result returned by an isolated provider."""

    output: object
    logs: str = ""
    query_count: int = 0
    truncated: bool = False
    metadata: dict = field(default_factory=dict)


class SandboxExecutionError(Exception):
    """Safe, product-facing sandbox failure."""

    def __init__(self, code: str, message: str, *, line: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = line


class DashboardSandbox(Protocol):
    """Provider-neutral isolated code execution contract."""

    async def execute(
        self,
        *,
        code: str,
        context: dict,
        filters: dict,
        query_handler: QueryHandler,
        cancel_checker: CancelChecker,
        limits: SandboxLimits,
    ) -> SandboxResult: ...
