"""
Map auto-outbound task fields to voice bot call variables.

A field's name is the variable name: a field named ``customer_name`` fills
``{{customer_name}}`` in the VoiceSpeed agent prompt with the target's value.
Names VoiceSpeed cannot accept are skipped rather than blocking the call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.schemas.outbound_task import normalize_field_name
from app.services.auto_outbound_task_service import PHONE_HEADER_ALIASES

# VoiceSpeed rejects the whole request beyond these limits.
MAX_CALL_VARIABLES = 20
MAX_CALL_VARIABLE_LENGTH = 500
MAX_VARIABLE_NAME_LENGTH = 32
RESERVED_VARIABLE_NAMES = {"search_results"}

UNSUPPORTED_FIELD_TYPES = {"file", "rich_text"}
SINGLE_CHOICE_TYPES = {"single_select", "single_select_tree"}
MULTI_CHOICE_TYPES = {"multi_select", "multi_select_tree"}

_NAME_CHARS_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_DATE_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$")
_MULTI_VALUE_SPLIT_RE = re.compile(r"[、,，;；]")
_PHONE_ALIASES = {normalize_field_name(alias) for alias in PHONE_HEADER_ALIASES}


@dataclass(frozen=True)
class FieldVariablePlan:
    key: str
    name: str
    field: dict
    skip_reason: str | None

    @property
    def passed(self) -> bool:
        return self.skip_reason is None


def _attr(field: Any, key: str, default: Any = None) -> Any:
    if isinstance(field, dict):
        return field.get(key, default)
    return getattr(field, key, default)


def _as_dict(field: Any) -> dict:
    if isinstance(field, dict):
        return field
    if hasattr(field, "model_dump"):
        return field.model_dump(mode="json")
    return {}


def _name_skip_reason(name: str) -> str | None:
    if not _NAME_CHARS_RE.match(name):
        return "invalid_name"
    if len(name) > MAX_VARIABLE_NAME_LENGTH:
        return "too_long"
    if name in RESERVED_VARIABLE_NAMES:
        return "reserved"
    if normalize_field_name(name) in _PHONE_ALIASES:
        return "phone_column"
    return None


def plan_field_variables(fields: list[Any] | None) -> list[FieldVariablePlan]:
    """Decide, for each enabled field in sort order, whether it is passed."""
    enabled = [
        (index, field)
        for index, field in enumerate(fields or [])
        if bool(_attr(field, "enabled", True))
    ]
    enabled.sort(key=lambda item: (int(_attr(item[1], "sort_order", 0) or 0), item[0]))

    plans: list[FieldVariablePlan] = []
    seen_names: set[str] = set()
    passed_count = 0
    for _index, field in enabled:
        name = str(_attr(field, "name", "") or "").strip()
        field_type = str(_attr(field, "field_type", "") or "")
        normalized = normalize_field_name(name)

        reason: str | None
        if field_type in UNSUPPORTED_FIELD_TYPES:
            reason = "unsupported_type"
        else:
            reason = _name_skip_reason(name)
        if reason is None and normalized in seen_names:
            reason = "duplicate"
        if reason is None and passed_count >= MAX_CALL_VARIABLES:
            reason = "over_limit"
        seen_names.add(normalized)
        if reason is None:
            passed_count += 1

        plans.append(
            FieldVariablePlan(
                key=str(_attr(field, "key", "") or ""),
                name=name,
                field=_as_dict(field),
                skip_reason=reason,
            )
        )
    return plans


def _format_number(text: str) -> str:
    try:
        number = Decimal(text)
    except InvalidOperation:
        return text
    if not number.is_finite():
        return text
    formatted = format(number, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return "0" if formatted in {"-0", ""} else formatted


def _parse_date(text: str) -> date | None:
    match = _DATE_RE.match(text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _format_date(text: str) -> str:
    parsed = _parse_date(text)
    return parsed.isoformat() if parsed else text


def _parse_time(text: str) -> time | None:
    match = _TIME_RE.match(text)
    if not match:
        return None
    try:
        return time(int(match.group(1)), int(match.group(2)))
    except ValueError:
        return None


def _format_time(text: str) -> str:
    parsed = _parse_time(text)
    return parsed.strftime("%H:%M") if parsed else text


def _format_datetime(text: str, tz: ZoneInfo) -> str:
    candidate = text.replace("/", "-")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parts = candidate.split()
        if len(parts) != 2:
            return text
        day = _parse_date(parts[0])
        clock = _parse_time(parts[1])
        if day is None or clock is None:
            return text
        parsed = datetime.combine(day, clock)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(tz)
    return parsed.strftime("%Y-%m-%d %H:%M")


def _choice_labels(field: dict) -> list[tuple[str, str]]:
    """(value, label) pairs in configured option order, flattening trees."""
    config = field.get("type_config") or {}
    pairs: list[tuple[str, str]] = []
    for option in config.get("options") or []:
        if isinstance(option, dict) and option.get("value") is not None:
            pairs.append((str(option["value"]), str(option.get("label") or option["value"])))

    def walk(nodes: Any) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            if node.get("value") is not None:
                pairs.append((str(node["value"]), str(node.get("label") or node["value"])))
            walk(node.get("children"))

    walk(config.get("tree_nodes"))
    return pairs


def _format_single_choice(raw: Any, field: dict) -> str:
    text = str(raw).strip()
    for value, label in _choice_labels(field):
        if value == text:
            return label
    return text


def _format_multi_choice(raw: Any, field: dict) -> str:
    if isinstance(raw, (list, tuple)):
        items = [str(item).strip() for item in raw]
    else:
        items = [part.strip() for part in _MULTI_VALUE_SPLIT_RE.split(str(raw))]
    items = [item for item in items if item]
    if not items:
        return ""

    order = _choice_labels(field)
    labels: list[str] = []
    remaining = list(items)
    for value, label in order:
        if value in remaining:
            labels.append(label)
            remaining = [item for item in remaining if item != value]
        elif label in remaining:
            labels.append(label)
            remaining = [item for item in remaining if item != label]
    return "、".join(labels + remaining)


def format_field_value(field: dict, raw: Any, tz: ZoneInfo) -> str:
    """Render one stored field value as the text VoiceSpeed receives."""
    if raw is None:
        return ""
    field_type = str(field.get("field_type") or "")
    if field_type in MULTI_CHOICE_TYPES:
        return _format_multi_choice(raw, field)
    if isinstance(raw, (list, tuple)):
        raw = "、".join(str(item) for item in raw)
    text = str(raw)
    if not text.strip():
        return ""
    stripped = text.strip()
    if field_type == "number":
        return _format_number(stripped)
    if field_type == "date":
        return _format_date(stripped)
    if field_type == "time":
        return _format_time(stripped)
    if field_type == "datetime":
        return _format_datetime(stripped, tz)
    if field_type in SINGLE_CHOICE_TYPES:
        return _format_single_choice(stripped, field)
    return text


def build_call_variables(
    fields: list[Any] | None,
    field_values: dict[str, Any] | None,
    tz: ZoneInfo,
) -> list[dict[str, Any]]:
    """Snapshot of variables to preset for one call, in field sort order."""
    values = field_values or {}
    items: list[dict[str, Any]] = []
    for plan in plan_field_variables(fields):
        if not plan.passed:
            continue
        value = format_field_value(plan.field, values.get(plan.key), tz)
        truncated = len(value) > MAX_CALL_VARIABLE_LENGTH
        items.append(
            {
                "name": plan.name,
                "value": value[:MAX_CALL_VARIABLE_LENGTH],
                "truncated": truncated,
            }
        )
    return items
