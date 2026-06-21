"""
Small XLSX writer and lightweight spreadsheet parser for imports/exports.
"""
from __future__ import annotations

import csv
import html
import re
from datetime import date, datetime
from io import BytesIO, StringIO
from urllib.parse import quote
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from app.core.exceptions import ValidationError


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_CELL_REF_PATTERN = re.compile(r"^([A-Z]+)(\d+)$")
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def build_xlsx(
    headers: list[str],
    rows: list[list[object]],
    sheet_name: str = "Sheet1",
    extra_sheets: list[tuple[str, list[str], list[list[object]]]] | None = None,
) -> bytes:
    """Build a minimal XLSX workbook with one or more sheets."""
    sheets: list[tuple[str, list[str], list[list[object]]]] = [(sheet_name, headers, rows)]
    if extra_sheets:
        sheets.extend(extra_sheets)

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(len(sheets)))
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml(sheets))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheets)))
        for index, (_, sheet_headers, sheet_rows) in enumerate(sheets, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _worksheet_xml(sheet_headers, sheet_rows),
            )
    return buffer.getvalue()


def parse_spreadsheet(content: bytes, filename: str) -> tuple[list[str], list[list[str]]]:
    """Parse the first worksheet from a CSV or XLSX upload."""
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        return parse_csv(content)
    if lower_name.endswith(".xlsx"):
        return parse_xlsx(content)
    raise ValidationError("Unsupported file format")


def parse_csv(content: bytes) -> tuple[list[str], list[list[str]]]:
    """Parse UTF-8 CSV with optional BOM."""
    text = content.decode("utf-8-sig")
    reader = csv.reader(StringIO(text))
    rows = [[cell.strip() for cell in row] for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return [], []
    headers = rows[0]
    return headers, rows[1:]


def parse_xlsx(content: bytes) -> tuple[list[str], list[list[str]]]:
    """Parse the first worksheet from a minimal OOXML workbook."""
    with ZipFile(BytesIO(content)) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_names = archive.namelist()
        sheet_path = next((name for name in sheet_names if name == "xl/worksheets/sheet1.xml"), None)
        if not sheet_path:
            raise ValidationError("Invalid spreadsheet file")
        sheet_root = ET.fromstring(archive.read(sheet_path))

    row_map: dict[int, dict[int, str]] = {}
    max_col = 0
    for row_el in sheet_root.findall("m:sheetData/m:row", _NS):
        row_idx = int(row_el.attrib.get("r", "0") or "0")
        col_map: dict[int, str] = {}
        for cell_el in row_el.findall("m:c", _NS):
            ref = cell_el.attrib.get("r", "")
            match = _CELL_REF_PATTERN.match(ref)
            if not match:
                continue
            col_idx = _column_index(match.group(1))
            col_map[col_idx] = _read_cell_value(cell_el, shared_strings)
            max_col = max(max_col, col_idx)
        if col_map:
            row_map[row_idx] = col_map

    if not row_map:
        return [], []

    min_row = min(row_map)
    max_row = max(row_map)
    table: list[list[str]] = []
    for row_idx in range(min_row, max_row + 1):
        cells = row_map.get(row_idx, {})
        table.append([cells.get(col_idx, "").strip() for col_idx in range(1, max_col + 1)])

    while table and not any(table[-1]):
        table.pop()
    if not table:
        return [], []

    headers = table[0]
    data_rows = table[1:]
    return headers, data_rows


def xlsx_content_disposition(filename: str) -> str:
    """Return a browser-compatible attachment disposition header."""
    return f"attachment; filename*=UTF-8''{quote(filename)}"


def _read_shared_strings(archive: ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    root = ET.fromstring(archive.read(path))
    values: list[str] = []
    for item in root.findall("m:si", _NS):
        parts = [node.text or "" for node in item.findall(".//m:t", _NS)]
        values.append("".join(parts))
    return values


def _read_cell_value(cell_el: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell_el.attrib.get("t")
    if cell_type == "inlineStr":
        text_el = cell_el.find("m:is/m:t", _NS)
        return text_el.text if text_el is not None and text_el.text else ""
    if cell_type == "s":
        value_el = cell_el.find("m:v", _NS)
        if value_el is None or value_el.text is None:
            return ""
        try:
            return shared_strings[int(value_el.text)]
        except (ValueError, IndexError):
            return value_el.text
    value_el = cell_el.find("m:v", _NS)
    return value_el.text if value_el is not None and value_el.text is not None else ""


def _column_index(letters: str) -> int:
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index


def _content_types_xml(sheet_count: int) -> str:
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{overrides}"
        "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_rels_xml(sheet_count: int) -> str:
    rels = "".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{rels}"
        "</Relationships>"
    )


def _workbook_xml(sheets: list[tuple[str, list[str], list[list[object]]]]) -> str:
    sheet_xml = "".join(
        f'<sheet name="{_escape_text(name[:31] or f"Sheet{index}")}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _, _) in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        f"{sheet_xml}"
        "</sheets>"
        "</workbook>"
    )


def _worksheet_xml(headers: list[str], rows: list[list[object]]) -> str:
    all_rows = [headers, *rows]
    row_xml = []
    for row_idx, row in enumerate(all_rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            ref = f"{_column_name(col_idx)}{row_idx}"
            cells.append(_cell_xml(ref, value))
        row_xml.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        f'{"".join(row_xml)}'
        "</sheetData>"
        "</worksheet>"
    )


def _cell_xml(ref: str, value: object) -> str:
    text = _format_cell_value(value)
    return f'<c r="{ref}" t="inlineStr"><is><t>{_escape_text(text)}</t></is></c>'


def _format_cell_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _escape_text(value: str) -> str:
    return html.escape(value, quote=True)


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name
