"""Unit tests for the grouped overall call report."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import importlib
from sqlalchemy.dialects import postgresql

import app.extensions  # noqa: F401 - mounts the private reports extension
from app.schemas.permission import EffectivePrincipal

registry = importlib.import_module("app.extensions.reports.lib.call_metric_groups")
base = importlib.import_module("app.extensions.reports.lib.call_metric_groups.base")
call_overview = importlib.import_module(
    "app.extensions.reports.lib.call_metric_groups.call_overview"
)
inbound_service = importlib.import_module(
    "app.extensions.reports.lib.call_metric_groups.inbound_service"
)
outbound_service = importlib.import_module(
    "app.extensions.reports.lib.call_metric_groups.outbound_service"
)
service_efficiency = importlib.import_module(
    "app.extensions.reports.lib.call_metric_groups.service_efficiency"
)
satisfaction = importlib.import_module(
    "app.extensions.reports.lib.call_metric_groups.satisfaction"
)
overall_service = importlib.import_module(
    "app.extensions.reports.services.call_overall_service"
)


def test_registry_preserves_product_group_order():
    assert [group.key for group in registry.all_groups()] == [
        "call_overview",
        "inbound_service",
        "outbound_service",
        "service_efficiency",
        "satisfaction",
    ]
    assert registry.get_group("unknown").key == "call_overview"


def test_ratio_distinguishes_zero_denominator_from_zero_numerator():
    assert base.ratio(0, 4) == 0.0
    assert base.ratio(1, 4) == 0.25
    assert base.ratio(0, 0) is None


def test_call_overview_values_exclude_finalization_metrics():
    values = call_overview.CallOverviewGroup().values_from_row(
        SimpleNamespace(
            call_count=8,
            inbound_call_count=5,
            outbound_call_count=3,
            active_call_count=1,
            ended_call_count=7,
        )
    )
    assert values == {
        "call_count": 8,
        "inbound_call_count": 5,
        "outbound_call_count": 3,
        "active_call_count": 1,
        "ended_call_count": 7,
    }


def test_inbound_values_recompute_rates_and_millisecond_average():
    values = inbound_service.InboundServiceGroup().values_from_row(
        SimpleNamespace(
            human_request_count=10,
            human_wait_count=8,
            ringing_count=7,
            answered_count=6,
            human_answered_count=6,
            queue_answered_count=5,
            short_abandon_count=2,
            wait_ms_sum=60_001,
            wait_sample_count=3,
            service_level_numerator=4,
            service_level_denominator=6,
        )
    )
    assert values["inbound_human_answer_rate"] == 0.6
    assert values["inbound_queue_answer_rate"] == 0.625
    assert values["inbound_avg_wait_seconds"] == 60_001 / 3 / 1000
    assert values["inbound_service_level_20s"] == 4 / 6


def test_outbound_values_keep_customer_and_agent_connections_separate():
    values = outbound_service.OutboundServiceGroup().values_from_row(
        SimpleNamespace(
            attempt_count=12,
            finalized_outbound_count=10,
            customer_connected_count=7,
            agent_connected_count=5,
            ring_ms_sum=21_000,
            ring_sample_count=3,
            talk_ms_sum=600_000,
            talk_sample_count=4,
        )
    )
    assert values["outbound_attempt_count"] == 12
    assert values["outbound_customer_connect_rate"] == 0.7
    assert values["outbound_agent_connected_count"] == 5
    assert values["outbound_avg_talk_seconds"] == 150.0


def test_service_efficiency_values_use_final_projection_totals():
    values = service_efficiency.ServiceEfficiencyGroup().values_from_row(
        SimpleNamespace(
            human_served_count=3,
            human_talk_ms_sum=9_000,
            human_talk_sample_count=2,
            total_duration_ms_sum=20_000,
            total_duration_sample_count=4,
            customer_hangup_count=3,
            hangup_sample_count=5,
        )
    )
    assert values["total_human_talk_seconds"] == 9.0
    assert values["avg_human_talk_seconds"] == 4.5
    assert values["avg_total_duration_seconds"] == 5.0
    assert values["customer_hangup_rate"] == 0.6


def test_satisfaction_values_do_not_treat_answered_as_satisfied():
    values = satisfaction.SatisfactionGroup().values_from_row(
        SimpleNamespace(triggered_count=8, answered_count=5, completed_count=4)
    )
    assert values == {
        "survey_triggered_count": 8,
        "survey_answered_count": 5,
        "survey_participation_rate": 0.625,
        "survey_completed_count": 4,
        "survey_completion_rate": 0.5,
    }


def test_partial_coverage_keeps_requested_range_and_uses_access_scope_exists():
    principal = EffectivePrincipal(
        user_id=42,
        tenant_id=7,
        data_scopes={"call_record": "self"},
    )
    ctx, coverage = overall_service._build_context_and_coverage(
        7,
        date(2026, 8, 31),
        date(2026, 8, 31),
        principal,
    )
    assert ctx is not None
    assert coverage.truncated is False
    assert coverage.status == "partial"
    assert ctx.range_start.isoformat() == "2026-08-31T00:00:00+08:00"
    assert coverage.actual_start == ctx.range_start.isoformat()
    compiled = str(
        ctx.scope_predicate.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "exists" in compiled
    assert "call_record_access_scopes" in compiled
    assert "subject_type = 'employee'" in compiled
    assert "subject_id in (42)" in compiled


def test_coverage_before_effective_time_still_queries_available_history():
    principal = EffectivePrincipal(
        user_id=42,
        tenant_id=7,
        data_scopes={"call_record": "all"},
    )
    ctx, coverage = overall_service._build_context_and_coverage(
        7,
        date(2026, 8, 29),
        date(2026, 8, 29),
        principal,
    )
    assert ctx is not None
    assert coverage.status == "partial"
    assert coverage.truncated is False
    assert coverage.actual_start == ctx.range_start.isoformat()
    assert coverage.actual_end == ctx.range_end.isoformat()


def test_projection_metrics_are_null_before_effective_time():
    provider = inbound_service.InboundServiceGroup()
    values = provider.empty_values()
    values["inbound_agent_answered_count"] = 4

    metrics = overall_service._metric_results(
        provider,
        values,
        interval_end=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )
    by_key = {metric.key: metric.value for metric in metrics}

    assert by_key["inbound_human_request_count"] is None
    assert by_key["inbound_agent_ringing_count"] is None
    assert by_key["inbound_agent_answered_count"] == 4
    assert by_key["inbound_short_abandon_count"] == 0


def test_projection_metrics_keep_available_values_after_effective_time():
    provider = inbound_service.InboundServiceGroup()
    values = provider.empty_values()
    values["inbound_human_request_count"] = 3

    metrics = overall_service._metric_results(
        provider,
        values,
        interval_end=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    by_key = {metric.key: metric.value for metric in metrics}

    assert by_key["inbound_human_request_count"] == 3
