"""Security and isolation tests for the custom dashboard subprocess sandbox."""

import asyncio

import pytest

from app.core.exceptions import ValidationError
from app.libs.dashboard_sandbox.base import SandboxExecutionError, SandboxLimits
from app.libs.dashboard_sandbox.providers.subprocess import SubprocessDashboardSandbox
from app.services.custom_dashboard_run_service import _validate_output


async def _not_cancelled() -> bool:
    return False


@pytest.mark.asyncio
async def test_sandbox_executes_read_only_ticket_query():
    async def query_handler(method: str, params: dict) -> object:
        assert method == "count"
        assert params["where"]["system:status"]["eq"] == "open"
        return 7

    result = await SubprocessDashboardSandbox().execute(
        code=(
            "from opendesk import query\n"
            "def run():\n"
            "    value = query.tickets.count(where={'system:status': {'eq': 'open'}})\n"
            "    return {'type': 'metric', 'value': value}\n"
        ),
        context={},
        filters={},
        query_handler=query_handler,
        cancel_checker=_not_cancelled,
        limits=SandboxLimits(wall_seconds=2),
    )

    assert result.output == {"type": "metric", "value": 7}
    assert result.query_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "import os\ndef run():\n    return {'type': 'metric', 'value': 1}",
        "def run():\n    return (1).__class__",
        "def helper():\n    return 1\ndef run():\n    return helper()",
        "def run():\n    return open('/etc/passwd').read()",
        # str.format resolves attributes at runtime and bypasses AST checks
        "def run():\n    return {'type': 'markdown', 'content': '{0.__globals__}'.format(run)}",
        "def run():\n    return {'type': 'markdown', 'content': ''.format_map({})}",
    ],
)
async def test_sandbox_rejects_unsafe_code_before_execution(code: str):
    async def query_handler(_method: str, _params: dict) -> object:
        raise AssertionError("query must not run")

    with pytest.raises(SandboxExecutionError) as exc_info:
        await SubprocessDashboardSandbox().execute(
            code=code,
            context={},
            filters={},
            query_handler=query_handler,
            cancel_checker=_not_cancelled,
            limits=SandboxLimits(wall_seconds=1),
        )

    assert exc_info.value.code == "unsafe_code"


@pytest.mark.asyncio
async def test_sandbox_terminates_infinite_loop():
    async def query_handler(_method: str, _params: dict) -> object:
        return None

    with pytest.raises(SandboxExecutionError) as exc_info:
        await SubprocessDashboardSandbox().execute(
            code="def run():\n    while True:\n        pass",
            context={},
            filters={},
            query_handler=query_handler,
            cancel_checker=_not_cancelled,
            limits=SandboxLimits(wall_seconds=0.2, cpu_seconds=1),
        )

    assert exc_info.value.code == "runtime_timeout"


@pytest.mark.asyncio
async def test_sandbox_terminates_slow_query_at_wall_deadline():
    async def slow_query_handler(_method: str, _params: dict) -> object:
        await asyncio.sleep(5)
        return None

    with pytest.raises(SandboxExecutionError) as exc_info:
        await SubprocessDashboardSandbox().execute(
            code=(
                "from opendesk import query\n"
                "def run():\n"
                "    value = query.tickets.count()\n"
                "    return {'type': 'metric', 'value': value}\n"
            ),
            context={},
            filters={},
            query_handler=slow_query_handler,
            cancel_checker=_not_cancelled,
            limits=SandboxLimits(wall_seconds=0.5),
        )

    assert exc_info.value.code == "runtime_timeout"


@pytest.mark.asyncio
async def test_sandbox_hides_internal_query_error_details():
    async def failing_query_handler(_method: str, _params: dict) -> object:
        raise RuntimeError('relation "tickets" does not exist: SELECT ...')

    with pytest.raises(SandboxExecutionError) as exc_info:
        await SubprocessDashboardSandbox().execute(
            code=(
                "from opendesk import query\n"
                "def run():\n"
                "    return {'type': 'metric', 'value': query.tickets.count()}\n"
            ),
            context={},
            filters={},
            query_handler=failing_query_handler,
            cancel_checker=_not_cancelled,
            limits=SandboxLimits(wall_seconds=2),
        )

    assert exc_info.value.code == "runtime_error"
    assert "SELECT" not in exc_info.value.message
    assert "Query failed" in exc_info.value.message


@pytest.mark.asyncio
async def test_sandbox_passes_through_validation_error_messages():
    async def rejecting_query_handler(_method: str, _params: dict) -> object:
        raise ValidationError("Query candidate range exceeds 200000 tickets")

    with pytest.raises(SandboxExecutionError) as exc_info:
        await SubprocessDashboardSandbox().execute(
            code=(
                "from opendesk import query\n"
                "def run():\n"
                "    return {'type': 'metric', 'value': query.tickets.count()}\n"
            ),
            context={},
            filters={},
            query_handler=rejecting_query_handler,
            cancel_checker=_not_cancelled,
            limits=SandboxLimits(wall_seconds=2),
        )

    assert exc_info.value.code == "runtime_error"
    assert "candidate range" in exc_info.value.message


def test_output_validation_rejects_html_external_urls_and_large_table():
    with pytest.raises(SandboxExecutionError):
        _validate_output({"type": "markdown", "content": "<script>alert(1)</script>"})
    with pytest.raises(SandboxExecutionError):
        _validate_output(
            {"type": "echarts", "option": {"series": [{"data": ["https://example.com"]}]}}
        )
    with pytest.raises(SandboxExecutionError):
        _validate_output(
            {
                "type": "table",
                "columns": ["value"],
                "rows": [{"value": index} for index in range(201)],
            }
        )
