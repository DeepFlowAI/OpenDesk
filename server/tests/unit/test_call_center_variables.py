"""
Unit tests for the IVR variable evaluator (call-center).
"""
from app.services.call_center.variables import (
    evaluate_group,
)


def g(conds, logic="AND"):
    return {"id": "g1", "name": "X", "logic": logic, "conditions": conds}


class TestEvaluateCondition:

    def test_eq_text(self):
        ctx = {"sys.caller_number": "10086"}
        assert evaluate_group(
            g([{"variable": "sys.caller_number", "operator": "eq", "value": "10086"}]),
            ctx,
        ) is True
        assert evaluate_group(
            g([{"variable": "sys.caller_number", "operator": "eq", "value": "999"}]),
            ctx,
        ) is False

    def test_neq(self):
        ctx = {"sys.caller_number": "10086"}
        assert evaluate_group(
            g([{"variable": "sys.caller_number", "operator": "neq", "value": "999"}]),
            ctx,
        ) is True

    def test_any_eq(self):
        ctx = {"user_input": "2"}
        assert evaluate_group(
            g([{"variable": "user_input", "operator": "any_eq", "value": ["1", "2", "3"]}]),
            ctx,
        ) is True
        assert evaluate_group(
            g([{"variable": "user_input", "operator": "any_eq", "value": ["8", "9"]}]),
            ctx,
        ) is False

    def test_any_neq(self):
        ctx = {"user_input": "5"}
        assert evaluate_group(
            g([{"variable": "user_input", "operator": "any_neq", "value": ["1", "2"]}]),
            ctx,
        ) is True

    def test_is_empty_and_not_empty(self):
        assert evaluate_group(
            g([{"variable": "missing", "operator": "is_empty", "value": None}]),
            {},
        ) is True
        assert evaluate_group(
            g([{"variable": "missing", "operator": "is_not_empty", "value": None}]),
            {},
        ) is False

    def test_time_in_uses_precomputed_flag(self):
        ctx = {"sys._time_in_schedule": {1: True}}
        assert evaluate_group(
            g([{"variable": "sys.current_time", "operator": "time_in", "value": 1}]),
            ctx,
        ) is True
        # Without precomputation, time_in is False (safe default)
        assert evaluate_group(
            g([{"variable": "sys.current_time", "operator": "time_in", "value": 2}]),
            ctx,
        ) is False

    def test_and_logic(self):
        ctx = {"a": "1", "b": "2"}
        assert evaluate_group(
            g(
                [
                    {"variable": "a", "operator": "eq", "value": "1"},
                    {"variable": "b", "operator": "eq", "value": "2"},
                ]
            ),
            ctx,
        ) is True
        assert evaluate_group(
            g(
                [
                    {"variable": "a", "operator": "eq", "value": "1"},
                    {"variable": "b", "operator": "eq", "value": "X"},
                ]
            ),
            ctx,
        ) is False

    def test_or_logic(self):
        ctx = {"a": "1", "b": "X"}
        assert evaluate_group(
            g(
                [
                    {"variable": "a", "operator": "eq", "value": "1"},
                    {"variable": "b", "operator": "eq", "value": "2"},
                ],
                logic="OR",
            ),
            ctx,
        ) is True
