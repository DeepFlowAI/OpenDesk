"""
Unit tests for the rule-based scheduling engine: violation detection and
the deterministic generation algorithm (pure functions, no DB).
"""
from datetime import date, timedelta

import pytest

from app.services.scheduling_rule_engine import (
    GenerationAborted,
    ShiftInfo,
    detect_coverage_violations,
    detect_employee_violations,
    detect_fairness_violations,
    generate_plan,
    iter_days,
)

MORNING = ShiftInfo(id=1, name="早班", start_min=9 * 60, end_min=13 * 60)
EVENING = ShiftInfo(id=2, name="晚班", start_min=18 * 60, end_min=22 * 60)
NIGHT = ShiftInfo(id=3, name="夜班", start_min=22 * 60, end_min=2 * 60)  # overnight
SHIFT_MAP = {s.id: s for s in (MORNING, EVENING, NIGHT)}

# 2026-08-03 is a Monday.
MON = date(2026, 8, 3)
DAYS = iter_days(MON, MON + timedelta(days=6))


def hard(key: str, value: int | None = None) -> dict:
    cfg = {"enabled": True, "level": "hard"}
    if value is not None:
        cfg["value"] = value
    return {key: cfg}


def soft(key: str, value: int | None = None) -> dict:
    cfg = {"enabled": True, "level": "soft"}
    if value is not None:
        cfg["value"] = value
    return {key: cfg}


def band(min_n: int, target_n: int | None = None, max_n: int | None = None) -> dict[str, list[int]]:
    target_n = min_n if target_n is None else target_n
    max_n = target_n if max_n is None else max_n
    return {"min": [min_n] * 7, "target": [target_n] * 7, "max": [max_n] * 7}


# ------------------------------------------------------------------
# Employee-bound constraints
# ------------------------------------------------------------------


class TestConsecutiveDays:
    def test_run_over_limit_flags_first_excess_day(self):
        keys = {(1, 1, MON + timedelta(days=i)) for i in range(5)}
        violations = detect_employee_violations(keys, SHIFT_MAP, hard("max_consecutive_days", 3), [1])
        assert len(violations) == 1
        v = violations[0]
        assert v.constraint == "max_consecutive_days"
        assert v.date == MON + timedelta(days=3)
        assert v.detail == {"limit": 3, "actual": 5}
        assert len(v.related_dates) == 5

    def test_run_within_limit_passes(self):
        keys = {(1, 1, MON + timedelta(days=i)) for i in range(3)}
        assert detect_employee_violations(keys, SHIFT_MAP, hard("max_consecutive_days", 3), [1]) == []

    def test_broken_run_passes(self):
        keys = {(1, 1, MON), (1, 1, MON + timedelta(days=1)), (1, 1, MON + timedelta(days=3))}
        assert detect_employee_violations(keys, SHIFT_MAP, hard("max_consecutive_days", 2), [1]) == []


class TestMinRestHours:
    def test_short_rest_between_days(self):
        keys = {(1, 2, MON), (1, 1, MON + timedelta(days=1))}  # 22:00 -> 09:00 = 11h
        violations = detect_employee_violations(keys, SHIFT_MAP, hard("min_rest_hours", 12), [1])
        assert len(violations) == 1
        assert violations[0].date == MON + timedelta(days=1)
        assert violations[0].shift_id == 1
        assert violations[0].detail["actual"] == 11.0

    def test_enough_rest_passes(self):
        keys = {(1, 2, MON), (1, 1, MON + timedelta(days=1))}
        assert detect_employee_violations(keys, SHIFT_MAP, hard("min_rest_hours", 8), [1]) == []

    def test_overnight_shift_counts_rest_to_next_day(self):
        # Night shift ends 02:00 the next day; a 09:00 shift that day leaves 7h.
        keys = {(1, 3, MON), (1, 1, MON + timedelta(days=1))}
        violations = detect_employee_violations(keys, SHIFT_MAP, hard("min_rest_hours", 8), [1])
        assert len(violations) == 1
        assert violations[0].detail["actual"] == 7.0

    def test_same_day_back_to_back_shifts_violate(self):
        keys = {(1, 1, MON), (1, 2, MON)}  # 13:00 -> 18:00 = 5h
        violations = detect_employee_violations(keys, SHIFT_MAP, hard("min_rest_hours", 8), [1])
        assert len(violations) == 1
        assert violations[0].date == MON


class TestWeeklyWorkDays:
    def test_over_limit_flags_monday(self):
        keys = {(1, 1, day) for day in DAYS}  # 7 days
        violations = detect_employee_violations(keys, SHIFT_MAP, hard("max_weekly_work_days", 6), [1])
        assert len(violations) == 1
        assert violations[0].date == MON
        assert violations[0].detail == {"limit": 6, "actual": 7}

    def test_within_limit_passes(self):
        keys = {(1, 1, DAYS[i]) for i in range(6)}
        assert detect_employee_violations(keys, SHIFT_MAP, hard("max_weekly_work_days", 6), [1]) == []


class TestDailyShifts:
    def test_over_limit(self):
        keys = {(1, 1, MON), (1, 2, MON), (1, 3, MON)}
        violations = detect_employee_violations(keys, SHIFT_MAP, hard("max_daily_shifts", 2), [1])
        assert len(violations) == 1
        assert violations[0].detail == {"limit": 2, "actual": 3}


# ------------------------------------------------------------------
# Coverage & fairness
# ------------------------------------------------------------------


class TestCoverage:
    def test_gap_and_overflow(self):
        # Morning min=2 empty -> gap; evening max=1 with 2 people -> overflow.
        targets = {1: band(2), 2: band(1)}
        keys = {(1, 2, MON), (2, 2, MON)}
        constraints = {**soft("coverage_gap"), **soft("coverage_overflow")}
        violations = detect_coverage_violations(
            keys, [MORNING, EVENING], constraints, targets, [MON], {1, 2}
        )
        by_constraint = {(v.constraint, v.shift_id) for v in violations}
        assert ("coverage_gap", 1) in by_constraint
        assert ("coverage_overflow", 2) in by_constraint
        assert all(v.level == "soft" for v in violations)

    def test_gap_uses_min_overflow_uses_max(self):
        targets = {1: band(2, 3, 4)}
        keys = {(1, 1, MON)}  # actual 1 < min 2
        constraints = {**soft("coverage_gap"), **soft("coverage_overflow")}
        violations = detect_coverage_violations(
            keys, [MORNING], constraints, targets, [MON], {1, 2, 3, 4, 5}
        )
        assert len(violations) == 1 and violations[0].constraint == "coverage_gap"
        assert violations[0].detail["target"] == 2

        keys = {(i, 1, MON) for i in range(1, 6)}  # actual 5 > max 4
        violations = detect_coverage_violations(
            keys, [MORNING], constraints, targets, [MON], set(range(1, 6))
        )
        assert len(violations) == 1 and violations[0].constraint == "coverage_overflow"
        assert violations[0].detail["target"] == 4

    def test_met_target_has_no_violation(self):
        targets = {1: band(2)}
        keys = {(1, 1, MON), (2, 1, MON)}
        constraints = {**soft("coverage_gap"), **soft("coverage_overflow")}
        assert detect_coverage_violations(keys, [MORNING], constraints, targets, [MON], {1, 2}) == []

    def test_zero_target_cells_are_ignored(self):
        constraints = {**soft("coverage_gap"), **soft("coverage_overflow")}
        assert detect_coverage_violations(set(), [MORNING], constraints, {1: band(0)}, [MON], {1}) == []

    def test_targets_disabled_skips_coverage(self):
        targets = {1: band(2)}
        constraints = {**soft("coverage_gap"), **soft("coverage_overflow")}
        assert (
            detect_coverage_violations(
                set(),
                [MORNING],
                constraints,
                targets,
                [MON],
                {1},
                targets_enabled=False,
            )
            == []
        )


class TestFairness:
    def test_deviation_over_limit(self):
        keys = {(1, 1, DAYS[i]) for i in range(5)}  # emp1: 5 days, emp2: 0
        violations = detect_fairness_violations(keys, soft("fairness_deviation", 2), DAYS, {1, 2})
        assert {v.employee_id for v in violations} == {1, 2}

    def test_balanced_passes(self):
        keys = {(1, 1, DAYS[0]), (2, 1, DAYS[0])}
        assert detect_fairness_violations(keys, soft("fairness_deviation", 2), DAYS, {1, 2}) == []


# ------------------------------------------------------------------
# Generation
# ------------------------------------------------------------------


def make_template(shift_id: int = 1, cycle: int = 2) -> dict:
    days = []
    for i in range(cycle):
        days.append({"kind": "shift", "shift_id": shift_id} if i % 2 == 0 else {"kind": "off"})
    return {"id": "t1", "name": "做一休一", "is_default": True, "days": days}


class TestGenerateFill:
    def test_fills_targets_with_fairness_rotation(self):
        plan = generate_plan(
            pool=[(1, "甲"), (2, "乙")],
            existing_keys=set(),
            shifts=[MORNING],
            targets={1: band(1)},
            constraints={},
            template=None,
            start=MON,
            end=MON + timedelta(days=6),
            mode="fill",
            use_template=False,
            on_hard_conflict="skip",
        )
        assert len(plan.to_create) == 7
        assert plan.target_met == 7 and plan.target_total == 7
        per_emp = {1: 0, 2: 0}
        for emp, _, _ in plan.to_create:
            per_emp[emp] += 1
        # Fairness order alternates members: 4 vs 3, not 7 vs 0.
        assert per_emp == {1: 4, 2: 3} or per_emp == {1: 3, 2: 4}

    def test_fill_keeps_existing_and_only_tops_up(self):
        existing = {(9, 1, MON)}  # off-pool member already covers Monday
        plan = generate_plan(
            pool=[(1, "甲")],
            existing_keys=existing,
            shifts=[MORNING],
            targets={1: band(1)},
            constraints={},
            template=None,
            start=MON,
            end=MON + timedelta(days=1),
            mode="fill",
            use_template=False,
            on_hard_conflict="skip",
        )
        # Monday cell is met by the existing (off-pool) row? No: coverage counts
        # pool members only, so Monday still needs one pool member.
        assert (1, 1, MON) in plan.to_create
        assert (1, 1, MON + timedelta(days=1)) in plan.to_create
        assert plan.to_delete == []

    def test_fill_stops_at_max(self):
        plan = generate_plan(
            pool=[(1, "甲"), (2, "乙"), (3, "丙")],
            existing_keys=set(),
            shifts=[MORNING],
            targets={1: band(1, 2, 2)},
            constraints={},
            template=None,
            start=MON,
            end=MON,
            mode="clear",
            use_template=False,
            on_hard_conflict="skip",
        )
        assert len(plan.to_create) == 2
        assert plan.target_met == 1

    def test_leave_day_is_unavailable_without_counting_as_work(self):
        plan = generate_plan(
            pool=[(1, "甲"), (2, "乙")],
            existing_keys=set(),
            shifts=[MORNING],
            targets={1: band(2)},
            constraints={},
            template=None,
            start=MON,
            end=MON,
            mode="fill",
            use_template=False,
            on_hard_conflict="skip",
            unavailable_emp_dates={(1, MON)},
        )
        assert plan.to_create == [(2, 1, MON)]
        assert plan.leave_skipped == 1
        assert plan.skipped_cells == 1


class TestGenerateClear:
    def test_clear_removes_pool_rows_in_range_only(self):
        in_range = (1, 1, MON)
        out_of_range = (1, 1, MON - timedelta(days=10))
        other_pool = (9, 1, MON)
        plan = generate_plan(
            pool=[(1, "甲")],
            existing_keys={in_range, out_of_range, other_pool},
            shifts=[MORNING],
            targets={1: band(1)},
            constraints={},
            template=None,
            start=MON,
            end=MON,
            mode="clear",
            use_template=False,
            on_hard_conflict="skip",
        )
        assert plan.to_delete == [in_range]
        assert plan.to_create == [(1, 1, MON)]


class TestGenerateTemplate:
    def test_template_offset_staggers_members(self):
        plan = generate_plan(
            pool=[(1, "A"), (2, "B")],
            existing_keys=set(),
            shifts=[MORNING],
            targets={},
            constraints={},
            template=make_template(cycle=2),
            start=MON,
            end=MON + timedelta(days=3),
            mode="clear",
            use_template=True,
            on_hard_conflict="skip",
            targets_enabled=False,
        )
        emp1_days = {d for (e, _, d) in plan.to_create if e == 1}
        emp2_days = {d for (e, _, d) in plan.to_create if e == 2}
        assert emp1_days == {MON, MON + timedelta(days=2)}
        assert emp2_days == {MON + timedelta(days=1), MON + timedelta(days=3)}

    def test_template_respects_max_cap(self):
        # Every member would get morning via a always-on template, but max=1.
        template = {
            "id": "t1",
            "name": "全早",
            "is_default": True,
            "days": [{"kind": "shift", "shift_id": 1}, {"kind": "shift", "shift_id": 1}],
        }
        plan = generate_plan(
            pool=[(1, "A"), (2, "B"), (3, "C")],
            existing_keys=set(),
            shifts=[MORNING],
            targets={1: band(1)},
            constraints={},
            template=template,
            start=MON,
            end=MON,
            mode="clear",
            use_template=True,
            on_hard_conflict="skip",
            targets_enabled=True,
        )
        assert len(plan.to_create) == 1
        assert plan.cell_counts[(1, MON)] == 1

    def test_targets_disabled_skips_fill(self):
        plan = generate_plan(
            pool=[(1, "甲"), (2, "乙")],
            existing_keys=set(),
            shifts=[MORNING],
            targets={1: band(2)},
            constraints=soft("coverage_gap"),
            template=None,
            start=MON,
            end=MON,
            mode="clear",
            use_template=False,
            on_hard_conflict="skip",
            targets_enabled=False,
        )
        assert plan.to_create == []
        assert plan.target_total == 0
        assert plan.soft_violations == []

    def test_use_template_off_skips_template(self):
        plan = generate_plan(
            pool=[(1, "甲")],
            existing_keys=set(),
            shifts=[MORNING],
            targets={1: band(1)},
            constraints={},
            template=make_template(cycle=2),
            start=MON,
            end=MON + timedelta(days=1),
            mode="clear",
            use_template=False,
            on_hard_conflict="skip",
        )
        assert len(plan.to_create) == 2  # target filling covers both days


class TestGenerateHardConflict:
    def test_skip_strategy_skips_conflicting_candidates(self):
        # One member, hard max_consecutive_days=1: alternating days only.
        plan = generate_plan(
            pool=[(1, "甲")],
            existing_keys=set(),
            shifts=[MORNING],
            targets={1: band(1)},
            constraints=hard("max_consecutive_days", 1),
            template=None,
            start=MON,
            end=MON + timedelta(days=2),
            mode="clear",
            use_template=False,
            on_hard_conflict="skip",
        )
        days = [d for _, _, d in plan.to_create]
        assert days == [MON, MON + timedelta(days=2)]
        assert plan.skipped_cells == 1
        assert plan.target_met == 2 and plan.target_total == 3

    def test_abort_strategy_raises(self):
        with pytest.raises(GenerationAborted):
            generate_plan(
                pool=[(1, "甲")],
                existing_keys=set(),
                shifts=[MORNING],
                targets={1: band(1)},
                constraints=hard("max_consecutive_days", 1),
                template=None,
                start=MON,
                end=MON + timedelta(days=2),
                mode="clear",
                use_template=False,
                on_hard_conflict="abort",
            )


class TestGenerateSoftSummary:
    def test_soft_violations_reported_not_blocked(self):
        # Min/target 2 but only 1 pool member -> coverage_gap soft violations.
        plan = generate_plan(
            pool=[(1, "甲")],
            existing_keys=set(),
            shifts=[MORNING],
            targets={1: band(2)},
            constraints=soft("coverage_gap"),
            template=None,
            start=MON,
            end=MON + timedelta(days=1),
            mode="clear",
            use_template=False,
            on_hard_conflict="skip",
        )
        assert len(plan.to_create) == 2
        assert all(v.constraint == "coverage_gap" for v in plan.soft_violations)
