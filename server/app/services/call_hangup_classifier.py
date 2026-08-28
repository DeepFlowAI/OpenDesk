"""Provider-neutral classification for call hangup signals."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

CLASSIFICATION_VERSION = 1


@dataclass(frozen=True)
class HangupSignal:
    reason: str | None
    sip_status: int | None
    sip_reason: str | None = None
    sip_warning: str | None = None
    sip_reason_hdr: str | None = None


@dataclass(frozen=True)
class HangupClassification:
    code: str
    party: str
    strategy: str
    score: float
    margin: float = 0.0
    matched_text: str | None = None
    version: int = CLASSIFICATION_VERSION


_INTERNAL_REASONS: dict[str, tuple[str, str]] = {
    "customer_hangup": ("customer_hangup", "customer"),
    "agent_hangup": ("agent_hangup", "agent"),
    "agent_cancel": ("canceled", "agent"),
    "local_cancel": ("canceled", "agent"),
    "remote_bye": ("customer_hangup", "customer"),
    "media_timeout": ("customer_hangup", "customer"),
    "busy": ("customer_busy", "carrier"),
    "customer_busy": ("customer_busy", "carrier"),
    "customer_power_off": ("customer_power_off", "carrier"),
    "customer_unreachable": ("customer_unreachable", "carrier"),
    "no_answer": ("customer_no_answer", "carrier"),
    "supervisor_force_hangup": ("supervisor_force_hangup", "supervisor"),
    "bot_completed": ("bot_completed", "bot"),
    "bridge_peer_gone": ("customer_hangup", "customer"),
    "no_agent_online": ("no_agent_online", "system"),
    "queue_timeout": ("queue_timeout", "system"),
    "queue_limit_reached": ("queue_limit_reached", "system"),
    "no_available_queue": ("no_available_queue", "system"),
    "agent_rejected": ("agent_rejected", "agent"),
    "drain_timeout": ("drain_timeout", "system"),
    "bridge_failed": ("bridge_failed", "system"),
    "media_failed": ("media_failed", "system"),
    "reconnect_failed": ("reconnect_failed", "system"),
    "invalid_number": ("invalid_number", "carrier"),
    "no_route": ("no_route", "system"),
    "no_flow_version": ("no_flow_version", "system"),
    "offer_expired": ("agent_no_answer", "system"),
    "originate_failed": ("originate_failed", "system"),
    "originate_rejected": ("originate_failed", "system"),
    "timeout": ("customer_no_answer", "carrier"),
    "canceled": ("canceled", "agent"),
}

_SIP_STATUS: dict[int, tuple[str, str]] = {
    400: ("provider_rejected", "carrier"),
    401: ("provider_auth_failed", "carrier"),
    402: ("provider_balance_insufficient", "carrier"),
    403: ("provider_rejected", "carrier"),
    404: ("provider_not_found", "carrier"),
    405: ("provider_unsupported", "carrier"),
    406: ("provider_rejected", "carrier"),
    407: ("provider_auth_failed", "carrier"),
    408: ("customer_no_answer", "carrier"),
    410: ("invalid_number", "carrier"),
    415: ("media_failed", "system"),
    429: ("provider_rate_limited", "carrier"),
    433: ("provider_rejected", "carrier"),
    478: ("provider_unresolvable_destination", "carrier"),
    479: ("provider_unresolvable_destination", "carrier"),
    480: ("customer_no_answer", "carrier"),
    481: ("provider_rejected", "carrier"),
    482: ("no_route", "system"),
    483: ("no_route", "system"),
    484: ("invalid_number", "carrier"),
    485: ("invalid_number", "carrier"),
    486: ("customer_busy", "carrier"),
    487: ("canceled", "agent"),
    488: ("media_failed", "system"),
    491: ("customer_busy", "carrier"),
    493: ("media_failed", "system"),
    500: ("provider_unavailable", "carrier"),
    501: ("provider_unsupported", "carrier"),
    502: ("provider_unavailable", "carrier"),
    503: ("provider_unavailable", "carrier"),
    504: ("provider_timeout", "carrier"),
    505: ("provider_unsupported", "carrier"),
    513: ("provider_rejected", "carrier"),
    580: ("media_failed", "system"),
    600: ("customer_busy", "carrier"),
    603: ("provider_rejected", "carrier"),
    604: ("invalid_number", "carrier"),
    606: ("provider_rejected", "carrier"),
    607: ("provider_rejected", "carrier"),
    608: ("provider_rejected", "carrier"),
}

_PHRASE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("provider_balance_insufficient", ("insufficient balance", "insufficient credit", "余额不足", "欠费")),
    ("provider_auth_failed", ("authentication failed", "unauthorized", "forbidden", "鉴权失败")),
    ("provider_rate_limited", ("rate limit", "too many requests", "频率限制")),
    ("provider_unresolvable_destination", ("unresolvable destination", "cannot resolve destination", "无法解析被叫")),
    ("invalid_number", ("invalid number", "number does not exist", "空号", "号码无效")),
    ("customer_power_off", ("powered off", "subscriber switched off", "关机")),
    ("customer_unreachable", ("subscriber unreachable", "network out of order", "无法接通")),
    ("provider_rejected", ("call rejected", "decline", "拒绝呼叫")),
)


def classify_hangup(signal: HangupSignal) -> HangupClassification:
    normalized_reason = (signal.reason or "").strip().lower()
    known = _INTERNAL_REASONS.get(normalized_reason)
    if known is not None:
        return HangupClassification(*known, strategy="internal_reason", score=1.0)

    text = _combined_text(signal)
    folded = text.casefold()
    for code, phrases in _PHRASE_RULES:
        if any(phrase.casefold() in folded for phrase in phrases):
            return HangupClassification(
                code, "carrier", "known_phrase", 1.0, matched_text=text
            )

    # Only final SIP responses classify a call. Provisional 1xx statuses often
    # remain attached to a later local timeout or cancellation.
    if signal.sip_status is not None and signal.sip_status >= 300:
        known = _SIP_STATUS.get(signal.sip_status)
        if known is not None:
            return HangupClassification(*known, strategy="sip_status", score=1.0)
        family = _sip_family(signal.sip_status)
        if family is not None:
            return HangupClassification(*family, strategy="sip_family", score=0.6)

    best = _bm25_classify(text)
    if best is not None:
        code, score, margin = best
        return HangupClassification(
            code, "carrier", "bm25", score, margin=margin, matched_text=text
        )

    if not normalized_reason and not text:
        return HangupClassification("normal_completed", "unknown", "empty", 1.0)
    return HangupClassification("unknown", "carrier", "unmapped", 0.0, matched_text=text or None)


def _sip_family(status: int) -> tuple[str, str] | None:
    if status >= 600:
        return ("provider_rejected", "carrier")
    if status >= 500:
        return ("provider_unavailable", "carrier")
    if status >= 400:
        return ("provider_rejected", "carrier")
    if status >= 300:
        return ("provider_rejected", "carrier")
    return None


def _combined_text(signal: HangupSignal) -> str:
    return " ".join(
        value.strip()
        for value in (signal.sip_reason, signal.sip_warning, signal.sip_reason_hdr)
        if value and value.strip()
    )


def _tokens(text: str) -> list[str]:
    folded = text.casefold()
    raw_words = re.findall(r"[a-z0-9]+", folded)
    words = [f"w:{word}" for word in raw_words]
    english_grams = [
        f"e3:{word[i : i + 3]}"
        for word in raw_words
        if len(word) >= 5
        for i in range(len(word) - 2)
    ]
    chunks = re.findall(r"[\u4e00-\u9fff]+", folded)
    chinese_grams = [
        f"zh2:{chunk[i : i + 2]}"
        for chunk in chunks
        for i in range(len(chunk) - 1)
    ]
    return words + english_grams + chinese_grams


def _bm25_classify(text: str) -> tuple[str, float, float] | None:
    query = _tokens(text)
    if not query:
        return None
    documents: list[tuple[str, list[str]]] = [
        (code, _tokens(phrase))
        for code, phrases in _PHRASE_RULES
        for phrase in phrases
    ]
    scores: dict[str, float] = {}
    avg_len = sum(len(tokens) for _, tokens in documents) / len(documents)
    for code, tokens in documents:
        score = _bm25_score(query, tokens, (doc for _, doc in documents), avg_len)
        scores[code] = max(scores.get(code, 0.0), score)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_code, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - second_score
    if best_score < 1.2 or margin < 0.35:
        return None
    return best_code, round(best_score, 4), round(margin, 4)


def _bm25_score(
    query: list[str], document: list[str], corpus: Iterable[list[str]], avg_len: float
) -> float:
    corpus_list = list(corpus)
    score = 0.0
    k1, b = 1.5, 0.75
    for term in set(query):
        frequency = document.count(term)
        if frequency == 0:
            continue
        docs_with_term = sum(term in item for item in corpus_list)
        idf = math.log(1 + (len(corpus_list) - docs_with_term + 0.5) / (docs_with_term + 0.5))
        denominator = frequency + k1 * (1 - b + b * len(document) / avg_len)
        score += idf * frequency * (k1 + 1) / denominator
    return score
