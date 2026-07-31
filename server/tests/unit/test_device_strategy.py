from app.services.call_center.device_strategy import (
    DeviceStrategy,
    strategy_for_device_type,
)


def test_sip_phone_does_not_own_browser_media():
    s = strategy_for_device_type("sip_phone")
    assert s.is_sip_phone
    assert not s.browser_owns_media()
    assert not s.should_request_browser_media_reconnect()
    assert not s.browser_accepts_offers()


def test_webrtc_owns_browser_media():
    s = strategy_for_device_type("webrtc")
    assert s.is_webrtc
    assert s.browser_owns_media()
    assert s.should_request_browser_media_reconnect()
    assert s.browser_accepts_offers()


def test_unknown_defaults_to_webrtc_capabilities():
    s = strategy_for_device_type(None)
    assert isinstance(s, DeviceStrategy)
    assert s.browser_owns_media()
