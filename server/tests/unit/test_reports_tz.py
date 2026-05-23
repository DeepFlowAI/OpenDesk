"""Unit tests for tenant timezone resolver."""
from zoneinfo import ZoneInfo

import importlib

import app.extensions  # triggers private overlay

tz_mod = importlib.import_module("app.extensions.reports.lib.tz")


class TestGetTenantTimezone:

    def test_returns_asia_shanghai_by_default(self):
        result = tz_mod.get_tenant_timezone(tenant_id=1)
        assert isinstance(result, ZoneInfo)
        assert str(result) == "Asia/Shanghai"

    def test_unknown_tenant_id_falls_back(self):
        result = tz_mod.get_tenant_timezone(tenant_id=999999)
        assert str(result) == "Asia/Shanghai"
