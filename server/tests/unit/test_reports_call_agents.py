"""Unit tests for employee call report metric and coverage rules."""
from datetime import date
import importlib

import app.extensions  # noqa: F401 - activates installed report extensions
from app.extensions.reports.schemas import (
    CallAgentOverviewMetrics,
    CallEmployeeOverviewRow,
    EmployeeBrief,
)


registry = importlib.import_module("app.extensions.reports.lib.call_agent_metric_groups")
service = importlib.import_module("app.extensions.reports.services.call_employees_service")


def test_registry_preserves_employee_product_group_order():
    assert [group.key for group in registry.all_groups()] == [
        "workload",
        "offer_response",
        "efficiency",
        "collaboration",
    ]


def test_groups_recompute_rates_and_millisecond_averages():
    raw = {
        "handled_call_count": 4,
        "offer_accepted_count": 3,
        "offer_timeout_count": 1,
        "offer_rate_denominator": 5,
        "offer_response_total_ms": 9_001,
        "offer_response_count": 3,
        "talk_total_ms": 120_001,
        "talk_count": 2,
        "hold_total_ms": 30_000,
        "hold_count": 2,
        "acw_total_ms": 12_000,
        "acw_count": 3,
        "handle_total_ms": 180_000,
        "handle_count": 3,
        "transfer_completed_count": 2,
        "transfer_terminal_count": 4,
        "consult_connected_count": 2,
        "consult_terminal_count": 3,
    }
    values = service._all_metric_values(raw)

    assert values["handled_call_count"] == 4
    assert values["offer_accept_rate"] == 0.6
    assert values["offer_timeout_rate"] == 0.2
    assert values["avg_offer_response_seconds"] == 9_001 / 3 / 1000
    assert values["total_talk_seconds"] == 120.001
    assert values["avg_talk_seconds"] == 120_001 / 2 / 1000
    assert values["avg_handle_seconds"] == 60.0
    assert values["transfer_success_rate"] == 0.5
    assert values["consult_success_rate"] == 2 / 3


def test_zero_denominators_remain_null_instead_of_zero():
    values = service._all_metric_values({})

    assert values["handled_call_count"] == 0
    assert values["offer_accept_rate"] is None
    assert values["avg_talk_seconds"] is None
    assert values["avg_handle_seconds"] is None
    assert values["transfer_success_rate"] is None


def test_coverage_reports_unavailable_partial_and_available():
    *_, unavailable = service._range_and_coverage(
        7, date(2026, 8, 30), date(2026, 8, 30)
    )
    *_, partial = service._range_and_coverage(
        7, date(2026, 8, 31), date(2026, 9, 1)
    )
    *_, available = service._range_and_coverage(
        7, date(2026, 9, 2), date(2026, 9, 2)
    )

    assert unavailable.status == "unavailable"
    assert partial.status == "partial"
    assert partial.truncated is True
    assert available.status == "available"


def test_default_sort_uses_handled_then_participated_then_name():
    lower_participation = CallEmployeeOverviewRow(
        employee=EmployeeBrief(id=1, name="B"),
        metrics=CallAgentOverviewMetrics(
            handled_call_count=4, participated_call_count=5
        ),
    )
    higher_participation = CallEmployeeOverviewRow(
        employee=EmployeeBrief(id=2, name="A"),
        metrics=CallAgentOverviewMetrics(
            handled_call_count=4, participated_call_count=7
        ),
    )
    rows = [lower_participation, higher_participation]
    rows.sort(
        key=service.cmp_to_key(
            lambda left, right: service._compare_rows(
                left, right, "handled_call_count", "desc"
            )
        )
    )

    assert rows == [higher_participation, lower_participation]


def test_unavailable_metric_sorts_last_in_both_directions():
    with_value = CallEmployeeOverviewRow(
        employee=EmployeeBrief(id=1, name="A"),
        metrics=CallAgentOverviewMetrics(offer_accept_rate=0.5),
    )
    unavailable = CallEmployeeOverviewRow(
        employee=EmployeeBrief(id=2, name="B"),
        metrics=CallAgentOverviewMetrics(offer_accept_rate=None),
    )
    for order in ("asc", "desc"):
        rows = [unavailable, with_value]
        rows.sort(
            key=service.cmp_to_key(
                lambda left, right: service._compare_rows(
                    left, right, "offer_accept_rate", order
                )
            )
        )
        assert rows == [with_value, unavailable]
