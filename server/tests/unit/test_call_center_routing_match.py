"""Unit tests for inbound call routing condition matching."""
from app.models.inbound_routing_rule import InboundRoutingRule
from app.services.call_center.routing import _number_matches, _rule_matches


def _rule(conditions: list[dict]) -> InboundRoutingRule:
    return InboundRoutingRule(
        id=1,
        tenant_id=1,
        name="t",
        enabled=True,
        priority=1,
        conditions=conditions,
        target_type="voice_flow",
        target_voice_flow_id=1,
    )


def test_number_matches_operators():
    assert _number_matches("4001889250", "eq", "4001889250")
    assert not _number_matches("4001889250", "eq", "4001")
    assert _number_matches("4001889250", "ne", "4001")
    assert _number_matches("4001889250", "contains", "1889")
    assert not _number_matches("4001889250", "contains", "999")
    assert _number_matches("4001889250", "not_contains", "999")
    assert not _number_matches("4001889250", "not_contains", "4001")


def test_rule_matches_callee_contains():
    rule = _rule(
        [{"condition_type": "callee_number", "operator": "contains", "value": "400188"}]
    )
    assert _rule_matches(rule, "15200000000", "4001889250", {})
    assert not _rule_matches(rule, "15200000000", "4001999999", {})


def test_rule_matches_caller_not_contains():
    rule = _rule(
        [{"condition_type": "caller_number", "operator": "not_contains", "value": "152"}]
    )
    assert _rule_matches(rule, "18600000000", "4001889250", {})
    assert not _rule_matches(rule, "15200000000", "4001889250", {})
