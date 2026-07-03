"""Tests for global exception handlers."""
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.exceptions import NotFoundError, register_exception_handlers


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise NameError("name 'display_mode' is not defined")

    @app.get("/missing")
    async def missing():
        raise NotFoundError("Conversation not found")

    return app


def test_unhandled_exception_returns_500_and_logs_traceback(caplog):
    client = TestClient(_build_app(), raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR, logger="app.core.exceptions"):
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Internal server error",
        "status": 500,
    }

    records = [r for r in caplog.records if r.name == "app.core.exceptions"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert "path=/boom" in record.getMessage()
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1], NameError)


def test_business_error_still_returns_structured_4xx(caplog):
    client = TestClient(_build_app(), raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR, logger="app.core.exceptions"):
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "Conversation not found",
        "status": 404,
    }
    assert not [r for r in caplog.records if r.name == "app.core.exceptions"]
