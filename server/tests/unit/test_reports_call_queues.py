"""Unit tests for call queue report metric and coverage rules."""
from datetime import date
import importlib

from sqlalchemy.dialects import postgresql

import app.extensions  # noqa: F401 - activates installed report extensions
from app.schemas.permission import EffectivePrincipal
from app.services.data_scope_service import DataScopeService
from app.extensions.reports.schemas import (
    CallQueueBrief,
    CallQueueOverviewMetrics,
    CallQueueOverviewRow,
)


registry = importlib.import_module("app.extensions.reports.lib.call_queue_metric_groups")
queries = importlib.import_module("app.extensions.reports.lib.call_queue_queries")
service = importlib.import_module("app.extensions.reports.services.call_queues_service")


def test_registry_preserves_queue_product_group_order():
    assert [group.key for group in registry.all_groups()] == [
        "queue_flow",
        "queue_outcomes",
        "queue_waiting",
        "agent_response",
    ]


def test_groups_recompute_rates_and_millisecond_averages():
    raw = {
        "queue_answered_count": 6,
        "queue_abandoned_count": 2,
        "queue_short_abandon_count": 1,
        "queue_timeout_count": 1,
        "queue_transfer_out_count": 1,
        "valid_result_count": 10,
        "answer_wait_total_ms": 60_001,
        "answer_wait_count": 3,
        "abandon_wait_total_ms": 8_000,
        "abandon_wait_count": 2,
        "queue_wait_total_ms": 90_000,
        "queue_wait_count": 9,
        "max_queue_wait_ms": 45_000,
        "service_level_answered_count": 5,
        "service_level_count": 8,
        "offer_accepted_count": 4,
        "offer_rejected_count": 2,
        "offer_timeout_count": 2,
        "offer_rate_denominator": 8,
    }
    values = {}
    for group in registry.all_groups():
        values.update(group.values(raw))

    assert values["queue_answer_rate"] == 0.6
    assert values["queue_abandon_rate"] == 0.2
    assert values["queue_short_abandon_rate"] == 0.1
    assert values["avg_answer_wait_seconds"] == 60_001 / 3 / 1000
    assert values["avg_queue_wait_seconds"] == 10.0
    assert values["queue_service_level_20s"] == 5 / 8
    assert values["offer_accept_rate"] == 0.5


def test_zero_denominators_remain_null_instead_of_zero():
    values = service._all_metric_values({})
    assert values["queue_entry_count"] == 0
    assert values["queue_answer_rate"] is None
    assert values["avg_answer_wait_seconds"] is None
    assert values["queue_service_level_20s"] is None
    assert values["offer_accept_rate"] is None


def test_coverage_reports_unavailable_partial_and_available():
    _, _, _, unavailable = service._range_and_coverage(
        7, date(2026, 8, 30), date(2026, 8, 30)
    )
    _, _, _, partial = service._range_and_coverage(
        7, date(2026, 8, 31), date(2026, 9, 1)
    )
    _, _, _, available = service._range_and_coverage(
        7, date(2026, 9, 2), date(2026, 9, 2)
    )
    assert unavailable.status == "unavailable"
    assert partial.status == "partial"
    assert available.status == "available"
    assert partial.truncated is False


def test_call_scope_predicate_compiles_to_access_scope_exists():
    principal = EffectivePrincipal(
        user_id=42,
        tenant_id=7,
        data_scopes={"call_record": "group"},
        group_ids=[3, 4],
    )
    predicate = DataScopeService.build_call_record_predicate(principal)
    compiled = str(
        predicate.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "exists" in compiled
    assert "call_record_access_scopes" in compiled
    assert "subject_type = 'employee_group'" in compiled
    assert "subject_id in (3, 4)" in compiled


def test_wait_distribution_uses_fixed_product_buckets():
    compiled = str(
        queries._wait_bucket().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "5000" in compiled
    assert "20000" in compiled
    assert "60000" in compiled
    assert "180000" in compiled


def test_queue_sort_keeps_unavailable_metrics_last_in_both_directions():
    with_value = CallQueueOverviewRow(
        queue=CallQueueBrief(queue_type="employee", queue_id=1, name="A"),
        metrics=CallQueueOverviewMetrics(queue_answer_rate=0.5),
    )
    unavailable = CallQueueOverviewRow(
        queue=CallQueueBrief(queue_type="employee", queue_id=2, name="B"),
        metrics=CallQueueOverviewMetrics(queue_answer_rate=None),
    )
    for order in ("asc", "desc"):
        rows = [unavailable, with_value]
        rows.sort(
            key=service.cmp_to_key(
                lambda left, right: service._compare_rows(
                    left, right, "queue_answer_rate", order
                )
            )
        )
        assert rows == [with_value, unavailable]
