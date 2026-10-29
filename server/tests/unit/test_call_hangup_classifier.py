"""Behavior tests for provider-neutral call hangup classification."""

from app.services.call_hangup_classifier import HangupSignal, classify_hangup


def test_known_sip_404_maps_to_provider_not_found() -> None:
    result = classify_hangup(
        HangupSignal(
            reason="rejected",
            sip_status=404,
            sip_reason="Not Found",
        )
    )

    assert result.code == "provider_not_found"
    assert result.party == "carrier"
    assert result.strategy == "sip_status"
    assert result.score == 1.0


def test_explicit_local_cancel_wins_over_provisional_sip_status() -> None:
    result = classify_hangup(
        HangupSignal(reason="local_cancel", sip_status=183, sip_reason="Session Progress")
    )

    assert result.code == "canceled"
    assert result.party == "agent"
    assert result.strategy == "internal_reason"


def test_unresolvable_destination_statuses_are_grouped() -> None:
    for status, phrase in (
        (478, "Unresolvable destination (478/TM)"),
        (479, "Regretfully, we were not able to process the URI (479/SL)"),
    ):
        result = classify_hangup(
            HangupSignal(reason="rejected", sip_status=status, sip_reason=phrase)
        )
        assert result.code == "provider_unresolvable_destination"
        assert result.party == "carrier"


def test_satisfaction_survey_endings_count_as_agent_hangup() -> None:
    for status in ("completed", "partial", "unanswered", "failed"):
        result = classify_hangup(
            HangupSignal(reason=f"satisfaction_{status}", sip_status=None)
        )
        assert result.code == "agent_hangup"
        assert result.party == "agent"
        assert result.strategy == "internal_reason"


def test_standard_busy_and_no_answer_are_preserved() -> None:
    busy = classify_hangup(HangupSignal(reason="busy", sip_status=486))
    no_answer = classify_hangup(HangupSignal(reason="no_answer", sip_status=180))
    no_signal = classify_hangup(HangupSignal(reason="no_answer", sip_status=None))

    assert busy.code == "customer_busy"
    assert no_answer.code == "customer_no_answer"
    assert no_signal.code == "customer_no_answer"


def test_ring_timeout_after_early_media_is_not_a_customer_no_answer() -> None:
    result = classify_hangup(
        HangupSignal(reason="no_answer", sip_status=183, sip_reason="Session Progress")
    )

    assert result.code == "provider_answer_unconfirmed"
    assert result.party == "carrier"
    assert result.strategy == "internal_reason_sip_status"


def test_carrier_480_is_reported_as_temporarily_unavailable() -> None:
    unanswered = classify_hangup(
        HangupSignal(reason="no_answer", sip_status=480, sip_reason="Temporarily Unavailable")
    )
    rejected = classify_hangup(HangupSignal(reason="rejected", sip_status=480))

    assert unanswered.code == "provider_temporarily_unavailable"
    assert rejected.code == "provider_temporarily_unavailable"
    assert unanswered.party == rejected.party == "carrier"


def test_callee_decline_is_reported_as_customer_busy() -> None:
    result = classify_hangup(
        HangupSignal(reason="rejected", sip_status=603, sip_reason="Decline")
    )

    assert result.code == "customer_busy"
    assert result.strategy == "sip_status"


def test_carrier_block_wording_on_603_stays_provider_rejected() -> None:
    result = classify_hangup(
        HangupSignal(
            reason="rejected",
            sip_status=603,
            sip_reason="Decline",
            sip_reason_hdr='Q.850;cause=21;text="Call rejected"',
        )
    )

    assert result.code == "provider_rejected"
    assert result.strategy == "known_phrase"


def test_bm25_matches_supplier_balance_message_without_exact_wording() -> None:
    result = classify_hangup(
        HangupSignal(
            reason="rejected",
            sip_status=None,
            sip_warning="Account has insufficent credit to complete this call",
        )
    )

    assert result.code == "provider_balance_insufficient"
    assert result.strategy == "bm25"
    assert result.score > 0


def test_unrelated_supplier_text_stays_unknown() -> None:
    result = classify_hangup(
        HangupSignal(reason="rejected", sip_status=None, sip_reason="XQZ-9381")
    )

    assert result.code == "unknown"
    assert result.strategy == "unmapped"


def test_common_unmapped_sip_codes_are_classified() -> None:
    cases = (
        (402, "provider_balance_insufficient"),
        (487, "canceled"),
        (488, "media_failed"),
        (491, "customer_busy"),
        (600, "customer_busy"),
        (604, "invalid_number"),
        (608, "provider_rejected"),
    )
    for status, code in cases:
        result = classify_hangup(HangupSignal(reason="rejected", sip_status=status))
        assert result.code == code
        assert result.strategy == "sip_status"


def test_unlisted_final_sip_uses_family_fallback() -> None:
    result = classify_hangup(HangupSignal(reason="rejected", sip_status=418))

    assert result.code == "provider_rejected"
    assert result.strategy == "sip_family"


def test_media_timeout_maps_to_customer_hangup() -> None:
    result = classify_hangup(HangupSignal(reason="media_timeout", sip_status=None))

    assert result.code == "customer_hangup"
    assert result.party == "customer"
    assert result.strategy == "internal_reason"


def test_remote_bye_and_media_timeout_share_customer_path() -> None:
    bye = classify_hangup(HangupSignal(reason="remote_bye", sip_status=None))
    timeout = classify_hangup(HangupSignal(reason="media_timeout", sip_status=None))

    assert (bye.code, bye.party) == (timeout.code, timeout.party)