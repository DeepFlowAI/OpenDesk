"""
Unit tests for embedded page service.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ForbiddenError, NotFoundError
from app.routers.v1.conversation_settings import (
    require_embedded_page_admin,
    require_embedded_page_workspace,
)
from app.schemas.embedded_page import EmbeddedPageCreate, EmbeddedPageUpdate
from app.schemas.permission import EffectivePrincipal
from app.services.embedded_page_service import EmbeddedPageService


VALID_REACT_CODE = "export default function EmbeddedApp({ context }) { return null }"
BLOCKED_REACT_CODE = "export default function EmbeddedApp() { return window.location.href }"


def _page(
    *,
    page_id: int = 1,
    location: str = "chat_auxiliary",
    page_type: str = "iframe",
    enabled: bool = True,
    default_focus: bool = False,
    sort_order: int = 0,
):
    return SimpleNamespace(
        id=page_id,
        location=location,
        name=f"Page {page_id}",
        page_type=page_type,
        url="https://example.com/member" if page_type == "iframe" else None,
        react_code=VALID_REACT_CODE if page_type == "react_code" else None,
        config={},
        enabled=enabled,
        default_focus=default_focus,
        sort_order=sort_order,
        created_at=None,
        updated_at=None,
    )


def _create_payload(**overrides) -> EmbeddedPageCreate:
    data = {
        "name": "Member profile",
        "page_type": "iframe",
        "url": "https://example.com/member?visitor_id={visitor_id}",
    }
    data.update(overrides)
    return EmbeddedPageCreate(**data)


def test_schema_rejects_empty_and_long_name():
    with pytest.raises(PydanticValidationError):
        _create_payload(name="   ")
    with pytest.raises(PydanticValidationError):
        _create_payload(name="x" * 41)


def test_schema_rejects_invalid_url():
    with pytest.raises(PydanticValidationError):
        _create_payload(url="ftp://example.com/x")
    with pytest.raises(PydanticValidationError):
        _create_payload(url="https://example.com/" + "x" * 2000)


def test_schema_requires_url_for_iframe_type():
    with pytest.raises(PydanticValidationError):
        _create_payload(url=None)


def test_schema_requires_react_code_for_react_type():
    with pytest.raises(PydanticValidationError):
        _create_payload(page_type="react_code", url=None, react_code=None)
    with pytest.raises(PydanticValidationError):
        _create_payload(page_type="react_code", url=None, react_code="   ")


def test_schema_rejects_react_code_without_default_export():
    with pytest.raises(PydanticValidationError):
        _create_payload(page_type="react_code", url=None, react_code="function App() { return null }")


def test_schema_rejects_react_code_with_blocked_capabilities():
    for code in (
        BLOCKED_REACT_CODE,
        "export default function A() { fetch('/x'); return null }",
        "export default function A() { return document.title }",
        "export default function A() { eval('1'); return null }",
        "import x from 'y'; export default function A() { return null }",
    ):
        with pytest.raises(PydanticValidationError):
            _create_payload(page_type="react_code", url=None, react_code=code)


def test_schema_accepts_valid_react_code_page():
    payload = _create_payload(
        page_type="react_code",
        url=None,
        react_code=VALID_REACT_CODE,
        config={"title": "Reminder"},
    )
    assert payload.page_type == "react_code"
    assert payload.config == {"title": "Reminder"}


@pytest.mark.asyncio
async def test_create_with_default_focus_clears_siblings(monkeypatch):
    created = _page(page_id=3, default_focus=True)
    create_mock = AsyncMock(return_value=created)
    clear_mock = AsyncMock(return_value=2)
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmbeddedPageRepository.create", create_mock
    )
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmbeddedPageRepository.clear_default_focus_others", clear_mock
    )
    db = AsyncMock()

    result = await EmbeddedPageService.create(db, 1, _create_payload(default_focus=True))

    clear_mock.assert_awaited_once_with(db, 1, "chat_auxiliary", 3)
    db.commit.assert_awaited_once()
    assert result["default_focus"] is True
    assert result["default_focus_overridden"] is True


@pytest.mark.asyncio
async def test_create_without_default_focus_skips_clear(monkeypatch):
    created = _page(page_id=3, default_focus=False)
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmbeddedPageRepository.create", AsyncMock(return_value=created)
    )
    clear_mock = AsyncMock(return_value=0)
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmbeddedPageRepository.clear_default_focus_others", clear_mock
    )
    db = AsyncMock()

    result = await EmbeddedPageService.create(db, 1, _create_payload())

    clear_mock.assert_not_awaited()
    assert result["default_focus_overridden"] is False


@pytest.mark.asyncio
async def test_update_not_found_raises(monkeypatch):
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmbeddedPageRepository.get_by_id", AsyncMock(return_value=None)
    )
    with pytest.raises(NotFoundError):
        await EmbeddedPageService.update(AsyncMock(), 999, 1, EmbeddedPageUpdate(**_create_payload().model_dump()))


@pytest.mark.asyncio
async def test_update_keeps_location_and_clears_focus(monkeypatch):
    existing = _page(page_id=5, location="chat_auxiliary", default_focus=False)
    updated = _page(page_id=5, default_focus=True)
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmbeddedPageRepository.get_by_id", AsyncMock(return_value=existing)
    )
    update_mock = AsyncMock(return_value=updated)
    monkeypatch.setattr("app.services.embedded_page_service.EmbeddedPageRepository.update", update_mock)
    clear_mock = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmbeddedPageRepository.clear_default_focus_others", clear_mock
    )
    db = AsyncMock()

    payload = _create_payload(location="call_screen_pop", default_focus=True)
    result = await EmbeddedPageService.update(db, 5, 1, EmbeddedPageUpdate(**payload.model_dump()))

    # Location is fixed by the management entry and must not be overwritten.
    assert "location" not in update_mock.await_args.args[2]
    clear_mock.assert_awaited_once_with(db, 1, "chat_auxiliary", 5)
    assert result["default_focus_overridden"] is True


@pytest.mark.asyncio
async def test_get_by_id_not_found_raises(monkeypatch):
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmbeddedPageRepository.get_by_id", AsyncMock(return_value=None)
    )
    with pytest.raises(NotFoundError):
        await EmbeddedPageService.get_by_id(AsyncMock(), 999, 1)


@pytest.mark.asyncio
async def test_workspace_pages_include_agent_summary(monkeypatch):
    rows = [_page(page_id=1), _page(page_id=2, page_type="react_code")]
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmbeddedPageRepository.list_enabled_by_location",
        AsyncMock(return_value=rows),
    )
    employee = SimpleNamespace(id=7, name="Alice", display_name="Alice A.", email="alice@example.com")
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmployeeRepository.get_by_id", AsyncMock(return_value=employee)
    )

    result = await EmbeddedPageService.list_workspace_pages(AsyncMock(), 1, 7, "chat_auxiliary")

    assert len(result["items"]) == 2
    assert result["items"][0]["name"] == "Page 1"
    assert result["agent"] == {"id": 7, "name": "Alice A.", "email": "alice@example.com"}


@pytest.mark.asyncio
async def test_workspace_pages_handle_missing_employee(monkeypatch):
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmbeddedPageRepository.list_enabled_by_location",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.services.embedded_page_service.EmployeeRepository.get_by_id", AsyncMock(return_value=None)
    )

    result = await EmbeddedPageService.list_workspace_pages(AsyncMock(), 1, 7, "chat_auxiliary")

    assert result["items"] == []
    assert result["agent"] == {"id": 7, "name": "", "email": ""}


def _principal(permissions: list[str], *, is_super_admin: bool = False) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=1,
        tenant_id=1,
        is_super_admin=is_super_admin,
        permissions=permissions,
    )


class TestEmbeddedPageLocationPermissions:
    def test_chat_admin_allowed_for_chat_auxiliary(self):
        principal = _principal(["admin.access", "chat.admin.settings.manage"])
        require_embedded_page_admin(principal, "chat_auxiliary")

    def test_call_admin_allowed_for_call_screen_pop(self):
        principal = _principal(["admin.access", "call.admin.settings.manage"])
        require_embedded_page_admin(principal, "call_screen_pop")

    def test_chat_admin_denied_for_call_screen_pop(self):
        principal = _principal(["admin.access", "chat.admin.settings.manage"])
        with pytest.raises(ForbiddenError):
            require_embedded_page_admin(principal, "call_screen_pop")

    def test_call_admin_denied_for_chat_auxiliary(self):
        principal = _principal(["admin.access", "call.admin.settings.manage"])
        with pytest.raises(ForbiddenError):
            require_embedded_page_admin(principal, "chat_auxiliary")

    def test_admin_access_required(self):
        principal = _principal(["call.admin.settings.manage"])
        with pytest.raises(ForbiddenError):
            require_embedded_page_admin(principal, "call_screen_pop")

    def test_super_admin_allowed_for_any_location(self):
        principal = _principal([], is_super_admin=True)
        require_embedded_page_admin(principal, "chat_auxiliary")
        require_embedded_page_admin(principal, "call_screen_pop")

    def test_unknown_location_denied(self):
        principal = _principal(
            ["admin.access", "chat.admin.settings.manage", "call.admin.settings.manage"]
        )
        with pytest.raises(ForbiddenError):
            require_embedded_page_admin(principal, "unknown_location")

    def test_workspace_permission_switches_by_location(self):
        chat_agent = _principal(["chat.workspace.use"])
        call_agent = _principal(["call.workspace.use"])

        require_embedded_page_workspace(chat_agent, "chat_auxiliary")
        require_embedded_page_workspace(call_agent, "call_screen_pop")

        with pytest.raises(ForbiddenError):
            require_embedded_page_workspace(chat_agent, "call_screen_pop")
        with pytest.raises(ForbiddenError):
            require_embedded_page_workspace(call_agent, "chat_auxiliary")
