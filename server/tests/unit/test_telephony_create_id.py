"""Unit tests for optional catalog IDs on phone-number / SIP-trunk create."""

from app.extensions.telephony.schemas import PhoneNumberCreate, SipTrunkCreate


def test_phone_number_create_accepts_explicit_id():
    payload = PhoneNumberCreate(
        id="pn_abc123def456",
        phone_number="07550001111",
        call_types=["inbound"],
    )
    assert payload.id == "pn_abc123def456"


def test_phone_number_create_blank_id_becomes_none():
    payload = PhoneNumberCreate(
        id="   ",
        phone_number="07550001111",
        call_types=["outbound"],
    )
    assert payload.id is None


def test_sip_trunk_create_accepts_explicit_id():
    payload = SipTrunkCreate(
        id="trunk_abc123def4",
        supplier_name="Lanrui",
        trunk_name="lanrui-shared",
        trunk_types=["inbound", "outbound"],
        peer_endpoints=[{"ip": "203.0.113.10", "port": 5060}],
    )
    assert payload.id == "trunk_abc123def4"
