"""Unit tests for session routing rule condition validation."""

import pytest
from pydantic import ValidationError

from app.schemas.session_routing_rule import SessionRoutingCondition


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
