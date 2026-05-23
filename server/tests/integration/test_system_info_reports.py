"""Integration tests for /api/v1/system/info ``reports_enabled`` field.

Verifies SR0's contract: the field is true iff the reports extension is in
``app.state.loaded_extensions``. Other system_info fields are not asserted
here — only the SR0-specific addition.
"""
import pytest
from httpx import AsyncClient

from app.main import _fastapi_app


class TestSystemInfoReportsEnabled:

    @pytest.mark.asyncio
    async def test_reports_enabled_present_in_response(self, client: AsyncClient):
        resp = await client.get("/api/v1/system/info")
        assert resp.status_code == 200
        data = resp.json()
        assert "reports_enabled" in data
        assert isinstance(data["reports_enabled"], bool)

    @pytest.mark.asyncio
    async def test_reports_enabled_reflects_loaded_state(self, client: AsyncClient):
        original = list(getattr(_fastapi_app.state, "loaded_extensions", []))
        try:
            _fastapi_app.state.loaded_extensions = ["reports"]
            resp = await client.get("/api/v1/system/info")
            assert resp.json()["reports_enabled"] is True

            _fastapi_app.state.loaded_extensions = []
            resp = await client.get("/api/v1/system/info")
            assert resp.json()["reports_enabled"] is False
        finally:
            _fastapi_app.state.loaded_extensions = original
