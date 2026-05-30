"""
Variable evaluator — evaluates a ConditionGroup against the current
runtime context (sys.* + flow variables) for the IVR condition node.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def evaluate_group(group: dict, ctx: dict[str, Any]) -> bool:
    """
    Returns True if the group's conditions are satisfied under the given ctx.
    `group` is the raw dict from graph_json (groups[i]).
    """

    conditions = group.get("conditions", [])
    if not conditions:
        return False
    results = [_evaluate_condition(c, ctx) for c in conditions]
    logic = group.get("logic", "AND")
    if logic == "OR":
        return any(results)
    return all(results)


def _evaluate_condition(cond: dict, ctx: dict[str, Any]) -> bool:
    op = cond.get("operator")
    var_name = cond.get("variable", "")
    value = cond.get("value")
    cur = ctx.get(var_name)

    if op == "eq":
        return _coerce_to_str(cur) == _coerce_to_str(value)
    if op == "neq":
        return _coerce_to_str(cur) != _coerce_to_str(value)
    if op == "any_eq":
        return _coerce_to_str(cur) in _to_str_list(value)
    if op == "any_neq":
        return _coerce_to_str(cur) not in _to_str_list(value)
    if op == "is_empty":
        return cur is None or _coerce_to_str(cur) == ""
    if op == "is_not_empty":
        return cur is not None and _coerce_to_str(cur) != ""
    if op == "time_in":
        return _time_in_schedule(ctx, value, expect=True)
    if op == "time_not_in":
        return _time_in_schedule(ctx, value, expect=False)
    return False


def _coerce_to_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _to_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [_coerce_to_str(x) for x in v]
    return [_coerce_to_str(v)]


def _time_in_schedule(ctx: dict[str, Any], service_hours_id: Any, expect: bool) -> bool:
    """
    Time-in-schedule evaluation. Reads precomputed flag from ctx if the
    orchestrator has already evaluated it (avoids re-querying service_hours
    inside the variable evaluator). Convention: ctx["sys._time_in_schedule"]
    is a dict[int, bool] keyed by service_hours_id.
    """

    try:
        sid = int(service_hours_id)
    except (TypeError, ValueError):
        return False
    flags = ctx.get("sys._time_in_schedule", {})
    flag = flags.get(sid)
    if flag is None:
        # Not yet evaluated — refuse the match for safety (caller should
        # precompute relevant schedules before calling).
        return False
    return flag == expect


def now_in_schedule(now: datetime, schedule: dict) -> bool:
    """
    Returns True if `now` falls within the schedule definition.

    The schedule dict mirrors `ServiceHours`'s weekly_schedules / holidays /
    makeup_days structure. Priority (per 服务时间 §5):
        makeup_days > holidays > weekly_schedules.
    """

    iso_date = now.date().isoformat()
    hhmm = now.strftime("%H:%M")

    # 1. Makeup days override everything
    for md in schedule.get("makeup_days", []):
        if md.get("date") == iso_date:
            return _in_any_slot(hhmm, md.get("slots", []))

    # 2. Holidays: in a holiday → not in service
    for h in schedule.get("holidays", []):
        if h.get("date") == iso_date:
            return False

    # 3. Weekly schedule (Monday=1 .. Sunday=7)
    iso_weekday = now.isoweekday()
    for ws in schedule.get("weekly_schedules", []):
        if ws.get("day_of_week") == iso_weekday:
            return _in_any_slot(hhmm, ws.get("slots", []))
    return False


def _in_any_slot(hhmm: str, slots: list[dict]) -> bool:
    for s in slots:
        if s.get("start", "") <= hhmm <= s.get("end", ""):
            return True
    return False
