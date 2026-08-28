"""
Rule-based scheduling engine: pure-function violation detection and generation.

No DB access — the plan service loads data and passes plain structures in,
which keeps the constraint math deterministic and unit-testable.

Conventions:
- AssignmentKey = (employee_id, shift_id, date)
- targets maps shift_id -> {"min"|"target"|"max": [7 ints]} indexed by date.weekday() (Mon=0)
- constraints maps constraint key -> {"enabled": bool, "level": "hard"|"soft", "value": int?}
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

AssignmentKey = tuple[int, int, date]
# shift_id -> {"min": [...], "target": [...], "max": [...]} each length 7
TargetsMap = dict[int, dict[str, list[int]]]

COVERAGE_KEYS = ("coverage_gap", "coverage_overflow")
_ZERO_WEEK = (0, 0, 0, 0, 0, 0, 0)


def _band(targets: TargetsMap, shift_id: int, kind: str, weekday: int) -> int:
    days = targets.get(shift_id, {}).get(kind) or _ZERO_WEEK
    return days[weekday] if weekday < len(days) else 0


@dataclass(frozen=True)
class ShiftInfo:
    id: int
    name: str
    start_min: int  # minutes from midnight
    end_min: int  # <= start_min means the shift ends after midnight


@dataclass
class Violation:
    level: str  # "hard" | "soft"
    constraint: str
    date: date
    employee_id: int | None = None
    shift_id: int | None = None
    detail: dict = field(default_factory=dict)
    related_dates: list[date] = field(default_factory=list)


class GenerationAborted(Exception):
    """Raised when on_hard_conflict='abort' and a candidate breaks a hard constraint."""

    def __init__(self, violation: Violation):
        self.violation = violation
        super().__init__(violation.constraint)


@dataclass
class GeneratePlan:
    to_create: list[AssignmentKey]
    to_delete: list[AssignmentKey]
    skipped_cells: int
    leave_skipped: int
    target_met: int
    target_total: int
    soft_violations: list[Violation]
    # First changed cells for the preview sample: (shift_id, day) -> added employee ids.
    added_by_cell: dict[tuple[int, date], list[int]]
    # Planned pool headcount per cell, for cells that have a target.
    cell_counts: dict[tuple[int, date], int]


def iter_days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _enabled(constraints: dict, key: str) -> dict | None:
    cfg = constraints.get(key)
    if isinstance(cfg, dict) and cfg.get("enabled"):
        return cfg
    return None


def _employee_intervals(
    emp_keys: list[AssignmentKey], shift_map: dict[int, ShiftInfo]
) -> list[tuple[datetime, datetime, int, date]]:
    intervals: list[tuple[datetime, datetime, int, date]] = []
    for _, shift_id, day in emp_keys:
        shift = shift_map.get(shift_id)
        if not shift:
            continue
        start_dt = datetime(day.year, day.month, day.day) + timedelta(minutes=shift.start_min)
        end_dt = datetime(day.year, day.month, day.day) + timedelta(minutes=shift.end_min)
        if shift.end_min <= shift.start_min:
            end_dt += timedelta(days=1)
        intervals.append((start_dt, end_dt, shift_id, day))
    intervals.sort(key=lambda item: item[0])
    return intervals


def detect_employee_violations(
    keys: set[AssignmentKey] | list[AssignmentKey],
    shift_map: dict[int, ShiftInfo],
    constraints: dict,
    employee_ids: list[int] | set[int],
) -> list[Violation]:
    """Employee-bound constraints: consecutive days, rest, weekly days, daily shifts."""
    wanted = set(employee_ids)
    by_emp: dict[int, list[AssignmentKey]] = {e: [] for e in wanted}
    for key in keys:
        if key[0] in wanted:
            by_emp[key[0]].append(key)

    out: list[Violation] = []
    for emp, emp_keys in by_emp.items():
        work_days = sorted({d for _, _, d in emp_keys})

        cfg = _enabled(constraints, "max_consecutive_days")
        if cfg and work_days:
            limit = cfg["value"]
            run = [work_days[0]]
            for day in work_days[1:]:
                if (day - run[-1]).days == 1:
                    run.append(day)
                else:
                    out.extend(_consecutive_violations(emp, run, cfg, limit))
                    run = [day]
            out.extend(_consecutive_violations(emp, run, cfg, limit))

        cfg = _enabled(constraints, "min_rest_hours")
        if cfg:
            required = cfg["value"]
            intervals = _employee_intervals(emp_keys, shift_map)
            for prev, nxt in zip(intervals, intervals[1:]):
                gap_hours = (nxt[0] - prev[1]).total_seconds() / 3600
                if gap_hours < required:
                    out.append(
                        Violation(
                            level=cfg["level"],
                            constraint="min_rest_hours",
                            date=nxt[3],
                            employee_id=emp,
                            shift_id=nxt[2],
                            detail={"required": required, "actual": round(gap_hours, 1)},
                            related_dates=[prev[3], nxt[3]],
                        )
                    )

        cfg = _enabled(constraints, "max_weekly_work_days")
        if cfg:
            limit = cfg["value"]
            by_week: dict[date, list[date]] = {}
            for day in work_days:
                monday = day - timedelta(days=day.weekday())
                by_week.setdefault(monday, []).append(day)
            for monday, days in by_week.items():
                if len(days) > limit:
                    out.append(
                        Violation(
                            level=cfg["level"],
                            constraint="max_weekly_work_days",
                            date=monday,
                            employee_id=emp,
                            detail={"limit": limit, "actual": len(days)},
                            related_dates=list(days),
                        )
                    )

        cfg = _enabled(constraints, "max_daily_shifts")
        if cfg:
            limit = cfg["value"]
            by_day: dict[date, int] = {}
            for _, _, day in emp_keys:
                by_day[day] = by_day.get(day, 0) + 1
            for day, count in by_day.items():
                if count > limit:
                    out.append(
                        Violation(
                            level=cfg["level"],
                            constraint="max_daily_shifts",
                            date=day,
                            employee_id=emp,
                            detail={"limit": limit, "actual": count},
                            related_dates=[day],
                        )
                    )
    return out


def _consecutive_violations(emp: int, run: list[date], cfg: dict, limit: int) -> list[Violation]:
    if len(run) <= limit:
        return []
    return [
        Violation(
            level=cfg["level"],
            constraint="max_consecutive_days",
            date=run[limit],
            employee_id=emp,
            detail={"limit": limit, "actual": len(run)},
            related_dates=list(run),
        )
    ]


def detect_coverage_violations(
    keys: set[AssignmentKey] | list[AssignmentKey],
    shifts: list[ShiftInfo],
    constraints: dict,
    targets: TargetsMap,
    days: list[date],
    pool_ids: set[int],
    cells: set[tuple[int, date]] | None = None,
    *,
    targets_enabled: bool = True,
) -> list[Violation]:
    """Per-cell headcount vs min/max; both directions are soft-only by schema."""
    if not targets_enabled:
        return []
    gap_cfg = _enabled(constraints, "coverage_gap")
    overflow_cfg = _enabled(constraints, "coverage_overflow")
    if not gap_cfg and not overflow_cfg:
        return []
    out: list[Violation] = []
    for day in days:
        weekday = day.weekday()
        for shift in shifts:
            min_n = _band(targets, shift.id, "min", weekday)
            target_n = _band(targets, shift.id, "target", weekday)
            max_n = _band(targets, shift.id, "max", weekday)
            if min_n <= 0 and target_n <= 0 and max_n <= 0:
                continue
            if cells is not None and (shift.id, day) not in cells:
                continue
            actual = len(
                {e for (e, s, d) in keys if s == shift.id and d == day and e in pool_ids}
            )
            if gap_cfg and min_n > 0 and actual < min_n:
                out.append(
                    Violation(
                        level=gap_cfg.get("level", "soft"),
                        constraint="coverage_gap",
                        date=day,
                        shift_id=shift.id,
                        detail={"target": min_n, "actual": actual, "band": "min"},
                        related_dates=[day],
                    )
                )
            elif overflow_cfg and max_n > 0 and actual > max_n:
                out.append(
                    Violation(
                        level=overflow_cfg.get("level", "soft"),
                        constraint="coverage_overflow",
                        date=day,
                        shift_id=shift.id,
                        detail={"target": max_n, "actual": actual, "band": "max"},
                        related_dates=[day],
                    )
                )
    return out


def detect_fairness_violations(
    keys: set[AssignmentKey] | list[AssignmentKey],
    constraints: dict,
    days: list[date],
    pool_ids: set[int],
) -> list[Violation]:
    cfg = _enabled(constraints, "fairness_deviation")
    if not cfg or len(pool_ids) < 2 or not days:
        return []
    limit = cfg["value"]
    day_set = set(days)
    counts = {
        emp: len({d for (e, _, d) in keys if e == emp and d in day_set}) for emp in pool_ids
    }
    mean = sum(counts.values()) / len(counts)
    out: list[Violation] = []
    for emp, count in counts.items():
        if abs(count - mean) > limit:
            out.append(
                Violation(
                    level=cfg["level"],
                    constraint="fairness_deviation",
                    date=days[0],
                    employee_id=emp,
                    detail={"limit": limit, "actual": count, "mean": round(mean, 1)},
                    related_dates=[days[0]],
                )
            )
    return out


def detect_violations(
    keys: set[AssignmentKey] | list[AssignmentKey],
    shifts: list[ShiftInfo],
    constraints: dict,
    targets: TargetsMap,
    days: list[date],
    pool_ids: set[int],
    *,
    targets_enabled: bool = True,
) -> list[Violation]:
    shift_map = {s.id: s for s in shifts}
    return (
        detect_employee_violations(keys, shift_map, constraints, pool_ids)
        + detect_coverage_violations(
            keys,
            shifts,
            constraints,
            targets,
            days,
            pool_ids,
            targets_enabled=targets_enabled,
        )
        + detect_fairness_violations(keys, constraints, days, pool_ids)
    )


def generate_plan(
    *,
    pool: list[tuple[int, str]],
    existing_keys: set[AssignmentKey],
    shifts: list[ShiftInfo],
    targets: TargetsMap,
    constraints: dict,
    template: dict | None,
    start: date,
    end: date,
    mode: str,
    use_template: bool,
    on_hard_conflict: str,
    targets_enabled: bool = True,
    unavailable_emp_dates: set[tuple[int, date]] | None = None,
) -> GeneratePlan:
    """Deterministic plan: fairness order -> template offset -> target filling.

    When targets are enabled, cell headcount never exceeds ``max`` (idle is
    preferred over overflow). Target filling tops up toward ``target``.
    Every candidate is simulated against the enabled hard constraints; on
    conflict it is skipped (or aborts the whole run) per on_hard_conflict.
    """
    days = iter_days(start, end)
    day_set = set(days)
    shift_map = {s.id: s for s in shifts}
    pool_ids = {emp for emp, _ in pool}
    names = dict(pool)
    unavailable = unavailable_emp_dates or set()

    base = set(existing_keys)
    if mode == "clear":
        to_delete = sorted(
            k for k in base if k[0] in pool_ids and k[2] in day_set
        )
    else:
        to_delete = []
    planned = base - set(to_delete)

    # Fairness: members with fewer workdays in range get picked first.
    workdays = {
        emp: len({d for (e, _, d) in planned if e == emp and d in day_set})
        for emp in pool_ids
    }
    order = sorted(pool_ids, key=lambda e: (workdays[e], names.get(e, ""), e))

    hard_constraints = {
        k: v
        for k, v in constraints.items()
        if isinstance(v, dict) and v.get("enabled") and v.get("level") == "hard"
    }

    def passes_hard(emp: int) -> bool:
        if not hard_constraints:
            return True
        return not detect_employee_violations(planned, shift_map, hard_constraints, [emp])

    def cell_count(shift_id: int, day: date) -> int:
        return len(
            {e for (e, s, d) in planned if s == shift_id and d == day and e in pool_ids}
        )

    def at_max(shift_id: int, day: date) -> bool:
        if not targets_enabled:
            return False
        max_n = _band(targets, shift_id, "max", day.weekday())
        return max_n > 0 and cell_count(shift_id, day) >= max_n

    added_by_cell: dict[tuple[int, date], list[int]] = {}
    skipped_cells = 0

    def try_add(emp: int, shift_id: int, day: date) -> str:
        """Returns 'ok', 'exists', 'max', 'hard', or 'unavailable'."""
        if (emp, day) in unavailable:
            return "unavailable"
        key = (emp, shift_id, day)
        if key in planned:
            return "exists"
        if at_max(shift_id, day):
            return "max"
        planned.add(key)
        if passes_hard(emp):
            added_by_cell.setdefault((shift_id, day), []).append(emp)
            return "ok"
        planned.discard(key)
        return "hard"

    def abort_or_skip(emp: int, shift_id: int, day: date) -> None:
        if on_hard_conflict == "abort":
            planned.add((emp, shift_id, day))
            violations = detect_employee_violations(planned, shift_map, hard_constraints, [emp])
            planned.discard((emp, shift_id, day))
            raise GenerationAborted(violations[0])

    # Step 1: rotation template with per-member day offset.
    template_days = (template or {}).get("days") if use_template else None
    if template_days:
        cycle = len(template_days)
        for index, emp in enumerate(order):
            offset = index % cycle
            for day_index, day in enumerate(days):
                if (emp, day) in unavailable:
                    continue
                entry = template_days[(day_index + offset) % cycle]
                if entry.get("kind") != "shift":
                    continue
                shift_id = entry.get("shift_id")
                if shift_id not in shift_map:
                    continue
                if any(k[0] == emp and k[2] == day for k in planned):
                    continue  # one shift per member per day in auto-generation
                result = try_add(emp, shift_id, day)
                if result == "hard":
                    abort_or_skip(emp, shift_id, day)
                # 'max' / 'exists': leave member idle or already covered

    # Step 2: fill remaining gaps towards the per-cell targets. The fairness
    # order is re-evaluated per cell so assignments alternate as counts grow.
    if targets_enabled:
        for day in days:
            weekday = day.weekday()
            for shift in shifts:
                target = _band(targets, shift.id, "target", weekday)
                max_n = _band(targets, shift.id, "max", weekday)
                if target <= 0:
                    continue
                cell_members = {
                    e
                    for (e, s, d) in planned
                    if s == shift.id and d == day and e in pool_ids
                }
                cap = max_n if max_n > 0 else target
                need = min(target, cap) - len(cell_members)
                if need <= 0:
                    continue
                candidates = sorted(
                    pool_ids,
                    key=lambda e: (
                        len({d for (e2, _, d) in planned if e2 == e and d in day_set}),
                        names.get(e, ""),
                        e,
                    ),
                )
                for emp in candidates:
                    if need == 0:
                        break
                    if emp in cell_members:
                        continue
                    if (emp, day) in unavailable:
                        continue
                    if any(k[0] == emp and k[2] == day for k in planned):
                        continue
                    result = try_add(emp, shift.id, day)
                    if result in ("ok", "exists"):
                        cell_members.add(emp)
                        need -= 1
                    elif result == "hard":
                        abort_or_skip(emp, shift.id, day)
                    else:
                        break  # at max — stop filling this cell
                if need > 0:
                    skipped_cells += 1

    # Target achievement over cells that have a target band.
    target_met = 0
    target_total = 0
    cell_counts: dict[tuple[int, date], int] = {}
    if targets_enabled:
        for day in days:
            weekday = day.weekday()
            for shift in shifts:
                target = _band(targets, shift.id, "target", weekday)
                if target <= 0:
                    continue
                target_total += 1
                actual = cell_count(shift.id, day)
                cell_counts[(shift.id, day)] = actual
                if actual >= target:
                    target_met += 1

    soft_constraints = {
        k: v
        for k, v in constraints.items()
        if isinstance(v, dict) and v.get("enabled") and v.get("level") != "hard"
    }
    soft_violations = detect_violations(
        planned,
        shifts,
        soft_constraints,
        targets,
        days,
        pool_ids,
        targets_enabled=targets_enabled,
    )

    return GeneratePlan(
        # In clear mode a re-created key may coincide with a deleted one, so
        # diff against the post-delete base rather than the original base.
        to_create=sorted(planned - (base - set(to_delete)), key=lambda k: (k[2], k[1], k[0])),
        to_delete=to_delete,
        skipped_cells=skipped_cells,
        leave_skipped=len(
            {
                (employee_id, day)
                for employee_id, day in unavailable
                if employee_id in pool_ids and day in day_set
            }
        ),
        target_met=target_met,
        target_total=target_total,
        soft_violations=soft_violations,
        added_by_cell=added_by_cell,
        cell_counts=cell_counts,
    )
