"""
Unit tests for the Scheduling Center Excel export.
"""
import io
import zipfile
from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from xml.etree import ElementTree as ET

import pytest

from app.libs.excel import parse_xlsx, xlsx_content_disposition
from app.models.scheduling import ScheduleAssignment, ScheduleShift
from app.services.scheduling_service import SchedulingService

TENANT = 1
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def shift(
    shift_id: int,
    name: str,
    enabled: bool = True,
    shift_type: str = "work",
) -> ScheduleShift:
    return ScheduleShift(
        id=shift_id,
        tenant_id=TENANT,
        name=name,
        shift_type=shift_type,
        start_time=time(9, 0),
        end_time=time(13, 0),
        color="#4B9CF5",
        sort_order=shift_id,
        is_enabled=enabled,
    )


def assignment(record_id: int, employee_id: int, shift_id: int, day: date):
    return ScheduleAssignment(
        id=record_id,
        tenant_id=TENANT,
        employee_id=employee_id,
        shift_id=shift_id,
        date=day,
    )


def sheet_names(content: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root = ET.fromstring(archive.read("xl/workbook.xml"))
    return [el.attrib["name"] for el in root.findall("m:sheets/m:sheet", _NS)]


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _db_with_groups(names: list[str]):
    """Async db mock whose execute() returns group names for the name query."""
    db = AsyncMock()
    db.add = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = names
    db.execute = AsyncMock(return_value=result)
    return db


def _patch(shifts, records, pool):
    ns = SimpleNamespace()
    shift_repo = patch(
        "app.services.scheduling_service.ScheduleShiftRepository"
    ).start()
    assignment_repo = patch(
        "app.services.scheduling_service.ScheduleAssignmentRepository"
    ).start()
    ns.list_pool_members = patch(
        "app.services.scheduling_service.list_pool_members", new_callable=AsyncMock
    ).start()
    ns.list_employees_by_ids = patch(
        "app.services.scheduling_service.list_employees_by_ids", new_callable=AsyncMock
    ).start()
    shift_repo.list_by_tenant = AsyncMock(return_value=shifts)
    assignment_repo.list_by_date_range = AsyncMock(return_value=records)
    ns.list_pool_members.return_value = pool
    return ns


@pytest.mark.asyncio
async def test_export_builds_three_sheets_with_records():
    monday = date(2026, 8, 10)
    sunday = date(2026, 8, 16)
    shifts = [shift(1, "早班"), shift(2, "晚班")]
    records = [
        assignment(1, employee_id=1, shift_id=1, day=monday),
        assignment(2, employee_id=2, shift_id=1, day=monday),
        assignment(3, employee_id=1, shift_id=2, day=monday + timedelta(days=1)),
    ]
    ns = _patch(
        shifts,
        records,
        pool=[(1, "Alice", "A001"), (2, "Bob", None)],
    )
    ns.list_employees_by_ids.return_value = {
        1: (1, "Alice", "A001"),
        2: (2, "Bob", None),
    }

    content, filename = await SchedulingService.export_assignments_xlsx(
        _db_with_groups(["一组"]), TENANT, monday, sunday, [1], lang="zh"
    )

    assert filename.startswith("排班_一组_2026-08-10_2026-08-16_")
    assert filename.endswith(".xlsx")
    assert sheet_names(content) == ["班次日期表", "员工日期表", "明细"]

    # parse_xlsx reads the first sheet: shift × day matrix.
    headers, rows = parse_xlsx(content)
    assert headers[0] == "班次 \\ 日期"
    assert headers[1] == "2026-08-10 周一"
    assert rows[0][0].startswith("早班")
    assert rows[0][1] == "Alice\nBob"  # two people on Monday, newline-joined
    assert rows[1][2] == "Alice"  # 晚班 Tuesday


@pytest.mark.asyncio
async def test_export_month_range_uses_month_in_filename():
    ns = _patch([shift(1, "早班")], [], pool=[])
    ns.list_employees_by_ids.return_value = {}
    content, filename = await SchedulingService.export_assignments_xlsx(
        _db_with_groups([]), TENANT, date(2026, 8, 1), date(2026, 8, 31), [1], lang="zh"
    )
    assert content
    assert "_2026-08_" in filename


@pytest.mark.asyncio
async def test_export_appends_disabled_shift_with_records():
    monday = date(2026, 8, 10)
    shifts = [shift(1, "早班"), shift(2, "旧班", enabled=False)]
    records = [assignment(1, employee_id=1, shift_id=2, day=monday)]
    ns = _patch(shifts, records, pool=[])
    ns.list_employees_by_ids.return_value = {1: (1, "Gone", None)}

    content, _ = await SchedulingService.export_assignments_xlsx(
        _db_with_groups([]), TENANT, monday, date(2026, 8, 16), [1], lang="zh"
    )
    _, rows = parse_xlsx(content)
    # Disabled shift appended after enabled ones; off-pool employee still shown.
    assert rows[1][0].startswith("旧班")
    assert rows[1][1] == "Gone"


@pytest.mark.asyncio
async def test_export_marks_leave_in_all_three_sheets():
    monday = date(2026, 8, 10)
    shifts = [shift(1, "早班"), shift(2, "请假", shift_type="leave")]
    records = [assignment(1, employee_id=1, shift_id=2, day=monday)]
    ns = _patch(shifts, records, pool=[(1, "Alice", "A001")])
    ns.list_employees_by_ids.return_value = {1: (1, "Alice", "A001")}

    content, _ = await SchedulingService.export_assignments_xlsx(
        _db_with_groups(["一组"]), TENANT, monday, monday, [1], lang="zh"
    )

    _, rows = parse_xlsx(content)
    assert rows[1][0] == "[假期] 请假 全天"
    assert rows[1][1] == "Alice"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        employee_sheet = archive.read("xl/worksheets/sheet2.xml").decode()
        detail_sheet = archive.read("xl/worksheets/sheet3.xml").decode()
    assert "[假期] 请假" in employee_sheet
    assert all(value in detail_sheet for value in ["类型", "假期类型", "请假", "全天"])


def test_content_disposition_rfc5987():
    header = xlsx_content_disposition("排班_一组_2026-08-10_2026-08-16_20260808-0300.xlsx")
    assert header.startswith("attachment;")
    assert "filename*=UTF-8''" in header
    assert "%E6%8E%92%E7%8F%AD" in header  # URL-encoded 排班
