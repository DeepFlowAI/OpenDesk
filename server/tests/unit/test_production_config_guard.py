"""Unit tests for the production startup config guard."""
import logging
from types import SimpleNamespace

import pytest

from app.configs import settings as settings_mod


def _fake_settings(secret_key: str, cors_origins: list[str]) -> SimpleNamespace:
    return SimpleNamespace(SECRET_KEY=secret_key, cors_origins=cors_origins)


def test_non_production_env_is_noop(monkeypatch, caplog):
    monkeypatch.setattr(settings_mod, "ENV", "dev")
    monkeypatch.setattr(
        settings_mod, "settings", _fake_settings("change-me", ["*"])
    )
    with caplog.at_level(logging.WARNING):
        settings_mod.assert_safe_production_config()
    assert caplog.records == []


def test_production_default_secret_key_raises(monkeypatch):
    monkeypatch.setattr(settings_mod, "ENV", "production")
    monkeypatch.setattr(
        settings_mod, "settings", _fake_settings("change-me", ["*"])
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings_mod.assert_safe_production_config()


def test_production_wildcard_cors_warns(monkeypatch, caplog):
    monkeypatch.setattr(settings_mod, "ENV", "production")
    monkeypatch.setattr(
        settings_mod, "settings", _fake_settings("strong-key", ["*"])
    )
    with caplog.at_level(logging.WARNING):
        settings_mod.assert_safe_production_config()
    assert any("CORS_ALLOW_ORIGINS" in r.message for r in caplog.records)


def test_production_explicit_cors_no_warning(monkeypatch, caplog):
    monkeypatch.setattr(settings_mod, "ENV", "production")
    monkeypatch.setattr(
        settings_mod,
        "settings",
        _fake_settings("strong-key", ["https://app.example.com"]),
    )
    with caplog.at_level(logging.WARNING):
        settings_mod.assert_safe_production_config()
    assert caplog.records == []
