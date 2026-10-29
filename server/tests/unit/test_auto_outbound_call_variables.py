"""Unit tests for mapping auto-outbound task fields to voice bot call variables."""
from zoneinfo import ZoneInfo

import pytest

from app.services.auto_outbound.call_variables import (
    MAX_CALL_VARIABLES,
    build_call_variables,
    format_field_value,
    plan_field_variables,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _field(key: str, name: str, field_type: str = "single_line_text", **extra) -> dict:
    return {"key": key, "name": name, "field_type": field_type, "enabled": True, **extra}


class TestPlanFieldVariables:
    @pytest.mark.parametrize(
        ("name", "field_type", "reason"),
        [
            ("customer_name", "single_line_text", None),
            ("备注", "single_line_text", "invalid_name"),
            ("CustomerName", "single_line_text", "invalid_name"),
            ("customer name", "single_line_text", "invalid_name"),
            ("1st", "single_line_text", "invalid_name"),
            ("a" * 33, "single_line_text", "too_long"),
            ("a" * 32, "single_line_text", None),
            ("search_results", "single_line_text", "reserved"),
            ("phone_number", "single_line_text", "phone_column"),
            ("mobile", "single_line_text", "phone_column"),
            ("phonenumber", "single_line_text", "phone_column"),
            ("attachment", "file", "unsupported_type"),
            ("intro", "rich_text", "unsupported_type"),
        ],
    )
    def test_skip_reasons(self, name, field_type, reason):
        [plan] = plan_field_variables([_field("field_1", name, field_type)])
        assert plan.skip_reason == reason

    def test_disabled_fields_are_left_out(self):
        plans = plan_field_variables([_field("field_1", "a", enabled=False), _field("field_2", "b")])
        assert [plan.name for plan in plans] == ["b"]

    def test_legacy_duplicate_keeps_earliest_by_sort_order(self):
        plans = plan_field_variables(
            [
                _field("field_1", "customer_name", sort_order=2),
                _field("field_2", "customername", sort_order=1),
            ]
        )
        assert [(plan.key, plan.skip_reason) for plan in plans] == [
            ("field_2", None),
            ("field_1", "duplicate"),
        ]

    def test_only_first_twenty_eligible_fields_pass(self):
        fields = [_field("bad", "备注", sort_order=0)] + [
            _field(f"field_{i}", f"var_{i}", sort_order=i + 1) for i in range(MAX_CALL_VARIABLES + 2)
        ]
        plans = plan_field_variables(fields)
        assert sum(plan.passed for plan in plans) == MAX_CALL_VARIABLES
        assert [plan.skip_reason for plan in plans[-2:]] == ["over_limit", "over_limit"]
        assert plans[0].skip_reason == "invalid_name"


class TestFormatFieldValue:
    @pytest.mark.parametrize(
        ("field_type", "raw", "expected"),
        [
            ("single_line_text", "  张三 ", "  张三 "),
            ("single_line_text", "   ", ""),
            ("single_line_text", None, ""),
            ("number", "12.500", "12.5"),
            ("number", "1E+3", "1000"),
            ("number", 100, "100"),
            ("number", "-0.0", "0"),
            ("number", "about 5", "about 5"),
            ("date", "2026/10/1", "2026-10-01"),
            ("date", "2026-10-01", "2026-10-01"),
            ("date", "下周一", "下周一"),
            ("time", "9:05", "09:05"),
            ("time", "09:05:30", "09:05"),
            ("time", "noon", "noon"),
            ("datetime", "2026/10/1 9:30", "2026-10-01 09:30"),
            ("datetime", "2026-10-01T01:30:00Z", "2026-10-01 09:30"),
            ("datetime", "2026-10-01T09:30:00", "2026-10-01 09:30"),
            ("datetime", "tomorrow", "tomorrow"),
        ],
    )
    def test_scalar_types(self, field_type, raw, expected):
        assert format_field_value({"field_type": field_type}, raw, SHANGHAI) == expected

    def test_single_select_uses_label_and_falls_back_to_raw(self):
        field = {
            "field_type": "single_select",
            "type_config": {"options": [{"label": "有意向", "value": "yes"}]},
        }
        assert format_field_value(field, "yes", SHANGHAI) == "有意向"
        assert format_field_value(field, "有意向", SHANGHAI) == "有意向"
        assert format_field_value(field, "unknown", SHANGHAI) == "unknown"

    def test_tree_single_select_searches_children(self):
        field = {
            "field_type": "single_select_tree",
            "type_config": {
                "tree_nodes": [
                    {"label": "华东", "value": "east", "children": [{"label": "上海", "value": "sh", "children": []}]}
                ]
            },
        }
        assert format_field_value(field, "sh", SHANGHAI) == "上海"

    def test_multi_select_joins_labels_in_option_order(self):
        field = {
            "field_type": "multi_select",
            "type_config": {
                "options": [
                    {"label": "红", "value": "r"},
                    {"label": "绿", "value": "g"},
                    {"label": "蓝", "value": "b"},
                ]
            },
        }
        assert format_field_value(field, ["b", "r", "x"], SHANGHAI) == "红、蓝、x"
        assert format_field_value(field, "蓝,绿", SHANGHAI) == "绿、蓝"
        assert format_field_value(field, [], SHANGHAI) == ""


class TestBuildCallVariables:
    def test_builds_passed_fields_with_empty_and_truncated_values(self):
        fields = [
            _field("field_1", "customer_name", sort_order=0),
            _field("field_2", "备注", sort_order=1),
            _field("field_3", "note", sort_order=2),
            _field("field_4", "story", sort_order=3),
        ]
        items = build_call_variables(
            fields,
            {"field_1": "张三", "field_2": "VIP", "field_4": "长" * 501},
            SHANGHAI,
        )
        assert items == [
            {"name": "customer_name", "value": "张三", "truncated": False},
            {"name": "note", "value": "", "truncated": False},
            {"name": "story", "value": "长" * 500, "truncated": True},
        ]

    def test_no_eligible_fields_returns_empty(self):
        assert build_call_variables([_field("field_1", "备注")], {"field_1": "x"}, SHANGHAI) == []
