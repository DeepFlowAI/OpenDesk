"""Unit tests for session routing rule condition validation."""

import pytest
from pydantic import ValidationError

from app.schemas.session_routing_rule import (
    SessionRoutingCondition,
    SessionRoutingQueueSource,
    SessionRoutingRuleCreate,
)


def test_channel_condition_accepts_websdk_value():
    condition = SessionRoutingCondition(
        condition_type="channel",
        operator="eq",
        value="websdk",
    )

    assert condition.value == "websdk"


@pytest.mark.parametrize("legacy_value", ["web", "sdk"])
def test_channel_condition_normalizes_legacy_values(legacy_value):
    condition = SessionRoutingCondition(
        condition_type="channel",
        operator="eq",
        value=legacy_value,
    )

    assert condition.value == "websdk"


def test_channel_condition_rejects_display_label():
    with pytest.raises(ValidationError):
        SessionRoutingCondition(
            condition_type="channel",
            operator="eq",
            value="Web SDK",
        )


def test_queue_source_deduplicates_target_ids():
    source = SessionRoutingQueueSource(
        source_type="employee",
        target_ids=[3, 3, 4],
    )

    assert source.target_ids == [3, 4]


def test_user_field_source_requires_single_field():
    with pytest.raises(ValidationError):
        SessionRoutingQueueSource(
            source_type="user_field",
            target_ids=[1, 2],
        )


def test_rule_create_accepts_legacy_target_group_id():
    payload = SessionRoutingRuleCreate(
        name="Legacy",
        target_group_id=8,
        conditions=[],
    )

    assert payload.target_group_id == 8
    assert payload.target_queue_sources == []


def test_rule_create_requires_queue_target():
    with pytest.raises(ValidationError):
        SessionRoutingRuleCreate(name="No target", conditions=[])
