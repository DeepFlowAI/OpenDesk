"""Unit tests for auto-outbound terminal-state mapping."""
from __future__ import annotations

import pytest

from app.services.auto_outbound.outcome_mapping import (
    AutoOutboundTerminalState,
    map_outcome,
)


@pytest.mark.parametrize(
    ("reason", "sip_status", "answered", "expected"),
    [
        (None, None, True, AutoOutboundTerminalState.ANSWERED),
        ("busy", 200, True, AutoOutboundTerminalState.ANSWERED),
        (None, 486, False, AutoOutboundTerminalState.BUSY),
        (None, 600, False, AutoOutboundTerminalState.BUSY),
        (None, 603, False, AutoOutboundTerminalState.BUSY),
        (None, 408, False, AutoOutboundTerminalState.NO_ANSWER),
        (None, 487, False, AutoOutboundTerminalState.NO_ANSWER),
        (None, 504, False, AutoOutboundTerminalState.NO_ANSWER),
        (None, 404, False, AutoOutboundTerminalState.INVALID_NUMBER),
        (None, 410, False, AutoOutboundTerminalState.INVALID_NUMBER),
        (None, 484, False, AutoOutboundTerminalState.INVALID_NUMBER),
        (None, 604, False, AutoOutboundTerminalState.INVALID_NUMBER),
        (None, 480, False, AutoOutboundTerminalState.POWER_OFF),
        (None, 403, False, AutoOutboundTerminalState.POWER_OFF),
        ("power_off", None, False, AutoOutboundTerminalState.POWER_OFF),
        ("关机", None, False, AutoOutboundTerminalState.POWER_OFF),
        ("停机", 480, False, AutoOutboundTerminalState.POWER_OFF),
        ("offline", None, False, AutoOutboundTerminalState.POWER_OFF),
        ("user_busy", None, False, AutoOutboundTerminalState.BUSY),
        ("no_answer", None, False, AutoOutboundTerminalState.NO_ANSWER),
        ("ring_timeout", None, False, AutoOutboundTerminalState.NO_ANSWER),
        ("空号", None, False, AutoOutboundTerminalState.INVALID_NUMBER),
        ("originate_failed", None, False, AutoOutboundTerminalState.FAILED),
        ("trunk error", None, False, AutoOutboundTerminalState.FAILED),
        (None, 478, False, AutoOutboundTerminalState.INVALID_NUMBER),
        (None, 488, False, AutoOutboundTerminalState.FAILED),
        (None, 503, False, AutoOutboundTerminalState.FAILED),
        (None, 499, False, AutoOutboundTerminalState.NO_ANSWER),  # unknown SIP → no_answer
        ("weird", None, False, AutoOutboundTerminalState.FAILED),  # text-only unknown → failed
        (None, None, False, AutoOutboundTerminalState.NO_ANSWER),
    ],
)
def test_map_outcome_matrix(reason, sip_status, answered, expected):
    assert map_outcome(reason, sip_status, answered=answered) == expected
