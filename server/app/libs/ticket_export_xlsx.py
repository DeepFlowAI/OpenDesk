"""Lossless, formula-safe ticket workbook formatting."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

from app.core.exceptions import BusinessError

MAX_ROWS = 50_000
MAX_COLUMNS = 200
MAX_BYTES = 20 * 1024 * 1024


def fail(code: str) -> None:
    raise BusinessError("Ticket export could not be completed", code=f"EXPORT_{code.upper()}")


class PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self.hidden += 1
        if not self.hidden and tag in ("br", "p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in ("p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def plain_text(value: str) -> str:
    parser = PlainText()
    parser.feed(value)
    return "".join(parser.parts).strip()


def values(value: object) -> list:
    return value if isinstance(value, list) else [value]


def entity_id(value: object) -> int | None:
    if isinstance(value, dict):
        value = value.get("id")
    try:
        return int(value) if not isinstance(value, bool) else None
    except (ValueError, TypeError):
        return None


def format_value(field: dict, value: object, language: str, tz: str) -> object:
    if value is None or value == "":
        return None
    kind = field["field_type"]
    unavailable = "已失效" if language == "zh" else "Unavailable"
    if kind == "number":
        try:
            number = Decimal(str(value))
            if not number.is_finite():
                return unavailable
            return str(value) if len(number.as_tuple().digits) > 15 else number
        except InvalidOperation:
            return unavailable
    if kind == "datetime":
        try:
            instant = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return instant.replace(tzinfo=instant.tzinfo or timezone.utc).astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return unavailable
    if kind == "date":
        return value.isoformat()[:10] if isinstance(value, date) else str(value)[:10]
    if kind in ("single_select", "multi_select", "single_select_tree", "multi_select_tree"):
        selected = [str(item) for item in values(value)]
        options = field.get("tree_nodes" if kind.endswith("tree") else "options", [])
        ordered = sorted(options, key=lambda item: (item.get("sort_order", 0), item.get("id") or 0))
        by_id = {item.get("id"): item for item in options}
        labels = []
        found = set()
        for option in ordered:
            if str(option["value"]) not in selected:
                continue
            found.add(str(option["value"]))
            path = [option["label"]]
            parent = option.get("parent_id")
            seen = {option.get("id")}
            while parent is not None and parent in by_id and parent not in seen:
                seen.add(parent)
                node = by_id[parent]
                path.insert(0, node["label"])
                parent = node.get("parent_id")
            labels.append(" / ".join(path))
        labels.extend(unavailable for item in selected if item not in found)
        return "\n".join(labels)
    if kind == "file":
        return "\n".join(str(item.get("name") or unavailable) if isinstance(item, dict) else unavailable
                         for item in values(value))
    if kind == "rich_text":
        return plain_text(str(value))
    # Unknown structured values must never expose internal object properties.
    if isinstance(value, (dict, list)):
        return unavailable
    return str(value)


class TicketWorkbook:
    def __init__(self, fields: list[dict], language: str, tz: str) -> None:
        if not 1 <= len(fields) <= MAX_COLUMNS:
            fail("column_limit")
        self.fields, self.language, self.tz = fields, language, tz
        self.book = Workbook(write_only=True)
        self.sheet = self.book.create_sheet("工单" if language == "zh" else "Tickets")
        self.sheet.freeze_panes = "A2"
        self.count = 0
        self.alignment = Alignment(wrap_text=True, vertical="top")
        self.sheet.append([self.cell(field["name"] + (f"（{tz}）" if field["field_type"] == "datetime" else ""), index)
                           for index, field in enumerate(fields)])

    def cell(self, value: object, index: int) -> WriteOnlyCell:
        if isinstance(value, str) and len(value) > 32767:
            fail(f"cell_limit_{index}")
        cell = WriteOnlyCell(self.sheet, value=value)
        if isinstance(value, str):
            cell.data_type = "s"
        elif isinstance(value, Decimal):
            precision = self.fields[index].get("type_config", {}).get("decimal_places", 0)
            cell.number_format = "0" + ("." + "0" * max(0, min(int(precision), 15)) if precision else "")
        cell.alignment = self.alignment
        return cell

    def close(self) -> None:
        """Release the streaming worksheet spool on failure or cancellation."""
        if not self.sheet.closed:
            self.sheet.close()
        writer = self.sheet._writer
        if writer is not None and Path(writer.out).exists():
            writer.cleanup()
        self.book.close()

    def append(self, row: list[object]) -> None:
        if self.count >= MAX_ROWS:
            fail("row_limit")
        self.sheet.append([self.cell(format_value(field, value, self.language, self.tz), index)
                           for index, (field, value) in enumerate(zip(self.fields, row, strict=True))])
        self.count += 1

    def finish(self) -> bytes:
        self.sheet.auto_filter.ref = f"A1:{get_column_letter(len(self.fields))}{self.count + 1}"
        output = BytesIO()
        self.book.save(output)
        data = output.getvalue()
        if len(data) > MAX_BYTES:
            fail("file_limit")
        return data
