"""
Map telephony hangup signals to auto-outbound terminal states.

Data-driven tables keep SIP / reason adjustments in one place.
When an unanswered outcome is ambiguous, prefer no_answer (retryable)
over failed (terminal) unless the signal clearly indicates a hard failure.
"""
from __future__ import annotations

from enum import StrEnum


class AutoOutboundTerminalState(StrEnum):
    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    POWER_OFF = "power_off"
    INVALID_NUMBER = "invalid_number"
    FAILED = "failed"


# SIP response → terminal state (unanswered path only).
SIP_STATUS_MAP: dict[int, AutoOutboundTerminalState] = {
    # Busy / reject-as-busy family
    486: AutoOutboundTerminalState.BUSY,
    491: AutoOutboundTerminalState.BUSY,
    600: AutoOutboundTerminalState.BUSY,
    603: AutoOutboundTerminalState.BUSY,
    606: AutoOutboundTerminalState.BUSY,
    607: AutoOutboundTerminalState.BUSY,
    608: AutoOutboundTerminalState.BUSY,
    # Timeout / cancelled / gateway timeout → treat as no answer
    408: AutoOutboundTerminalState.NO_ANSWER,
    487: AutoOutboundTerminalState.NO_ANSWER,
    504: AutoOutboundTerminalState.NO_ANSWER,
    # Number does not exist / gone / address incomplete / does not exist anywhere
    404: AutoOutboundTerminalState.INVALID_NUMBER,
    410: AutoOutboundTerminalState.INVALID_NUMBER,
    478: AutoOutboundTerminalState.INVALID_NUMBER,
    479: AutoOutboundTerminalState.INVALID_NUMBER,
    484: AutoOutboundTerminalState.INVALID_NUMBER,
    485: AutoOutboundTerminalState.INVALID_NUMBER,
    604: AutoOutboundTerminalState.INVALID_NUMBER,
    # Temporarily unavailable — often power-off / out of coverage; refined by reason keywords
    480: AutoOutboundTerminalState.POWER_OFF,
    # Forbidden — sometimes carrier "service barred / suspended"
    403: AutoOutboundTerminalState.POWER_OFF,
    # Auth / balance / media / upstream — hard fail, do not keep retrying the same target
    401: AutoOutboundTerminalState.FAILED,
    402: AutoOutboundTerminalState.FAILED,
    405: AutoOutboundTerminalState.FAILED,
    407: AutoOutboundTerminalState.FAILED,
    415: AutoOutboundTerminalState.FAILED,
    429: AutoOutboundTerminalState.FAILED,
    481: AutoOutboundTerminalState.FAILED,
    482: AutoOutboundTerminalState.FAILED,
    483: AutoOutboundTerminalState.FAILED,
    488: AutoOutboundTerminalState.FAILED,
    500: AutoOutboundTerminalState.FAILED,
    501: AutoOutboundTerminalState.FAILED,
    502: AutoOutboundTerminalState.FAILED,
    503: AutoOutboundTerminalState.FAILED,
    505: AutoOutboundTerminalState.FAILED,
    580: AutoOutboundTerminalState.FAILED,
}

# Substrings in hangup reason (lowercased) → terminal state.
# Checked after SIP map so reason can refine 480/403/410 and cover text-only fails.
REASON_KEYWORD_MAP: list[tuple[tuple[str, ...], AutoOutboundTerminalState]] = [
    (
        ("poweroff", "power_off", "power-off", "offline", "关机", "停机", "out of service"),
        AutoOutboundTerminalState.POWER_OFF,
    ),
    (
        ("busy", "user_busy", "here_now", "线忙"),
        AutoOutboundTerminalState.BUSY,
    ),
    (
        ("no_answer", "noanswer", "no-answer", "timeout", "ring_timeout", "无人接听"),
        AutoOutboundTerminalState.NO_ANSWER,
    ),
    (
        ("invalid", "not_found", "unallocated", "空号", "does_not_exist"),
        AutoOutboundTerminalState.INVALID_NUMBER,
    ),
    (
        ("originate", "invite", "trunk", "network", "forbidden", "rejected", "failed"),
        AutoOutboundTerminalState.FAILED,
    ),
]

# Reasons that imply the call never left our stack successfully.
ORIGINATE_FAILURE_REASONS: frozenset[str] = frozenset(
    {
        "originate_failed",
        "originate_error",
        "invite_failed",
        "trunk_error",
        "telephony_error",
        "connection_failed",
    }
)


def map_outcome(
    reason: str | None,
    sip_status: int | None,
    *,
    answered: bool = False,
) -> AutoOutboundTerminalState:
    """
    Resolve a terminal state from hangup / answer signals.

    Priority:
      1. answered flag → answered
      2. reason keywords (power_off / busy / …) when present
      3. SIP status table
      4. known originate-failure reason tokens → failed
      5. conservative fallback: no_answer when a SIP status exists but is
         unmapped; otherwise failed (likely never rang).
    """
    if answered:
        return AutoOutboundTerminalState.ANSWERED

    reason_l = (reason or "").strip().lower()

    if reason_l:
        for keywords, state in REASON_KEYWORD_MAP:
            if any(token in reason_l for token in keywords):
                return state
        if reason_l in ORIGINATE_FAILURE_REASONS:
            return AutoOutboundTerminalState.FAILED

    if sip_status is not None:
        mapped = SIP_STATUS_MAP.get(int(sip_status))
        if mapped is not None:
            # 410 appears in both invalid_number (SIP map) and power_off keywords.
            # Keywords already ran; keep SIP mapping.
            return mapped
        # Unknown SIP on an unanswered call: safer to retry as no_answer
        # than to permanently fail the target.
        return AutoOutboundTerminalState.NO_ANSWER

    if reason_l:
        # Text reason with no SIP — treat as system/line failure.
        return AutoOutboundTerminalState.FAILED

    # No signal at all: conservative no_answer so retry policy can apply.
    return AutoOutboundTerminalState.NO_ANSWER
