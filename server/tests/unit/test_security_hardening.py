"""Unit tests for login throttling, password-reset hardening, visitor message
type restriction, field-definition tenant isolation and first-run admin seed."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import login_throttle
from app.core.exceptions import InvalidCodeError, NotFoundError, RateLimitedError, UnauthorizedError, ValidationError
from app.core.security import hash_password
from app.db import seed
from app.schemas.auth import LoginRequest
from app.schemas.password_reset import ResetPasswordRequest, SendVerifyCodeRequest
from app.services import auth_service as auth_module
from app.services import password_reset_service as reset_module
from app.services.auth_service import AuthService
from app.services.conversation_service import ConversationService
from app.services.fd_field_definition_service import FdFieldDefinitionService
from app.services.password_reset_service import VERIFY_CODE_MAX_ATTEMPTS, PasswordResetService


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}

    async def get(self, key):
        return self.data.get(key)

    async def incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    async def expire(self, key, seconds):
        return True

    async def delete(self, *keys):
        return sum(1 for key in keys if self.data.pop(key, None) is not None)

    async def setex(self, key, seconds, value):
        self.data[key] = value

    async def exists(self, key):
        return 1 if key in self.data else 0


@pytest.fixture
def fake_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(login_throttle, "_redis", lambda: redis)
    return redis


# ── Employee login throttling ────────────────────────────────────────────


def _patch_login(monkeypatch, *, password="Right1234"):
    tenant = SimpleNamespace(id=1, is_active=True)
    employee = SimpleNamespace(
        id=42, tenant_id=1, username="agent", name="Agent", display_name="Agent",
        avatar=None, roles=["agent"], password_hash=hash_password(password),
        is_active=True, preferences={}, current_session_id=None,
    )
    principal = SimpleNamespace(
        role_ids=[], permissions=[], data_scopes={}, is_super_admin=False, group_ids=[],
    )

    async def fake_update_login_session(_db, emp, session_id):
        emp.current_session_id = session_id
        return emp

    monkeypatch.setattr(auth_module.TenantRepository, "resolve_by_identifier", AsyncMock(return_value=tenant))
    monkeypatch.setattr(auth_module.EmployeeRepository, "get_by_username_or_email", AsyncMock(return_value=employee))
    monkeypatch.setattr(
        auth_module.EmployeeRepository, "update_login_session", AsyncMock(side_effect=fake_update_login_session)
    )
    monkeypatch.setattr(auth_module.EmployeeSessionService, "disconnect_current_socket", AsyncMock())
    monkeypatch.setattr(auth_module.EmployeeSessionService, "generate_session_id", lambda: "sess0001")
    monkeypatch.setattr(auth_module.PermissionService, "get_current_principal", AsyncMock(return_value=principal))
    monkeypatch.setattr(auth_module, "create_access_token", lambda data: "signed-token")


async def _login(password: str, ip: str = "198.51.100.1"):
    return await AuthService.login(
        AsyncMock(),
        LoginRequest(tenant="t", username="Agent", password=password),
        client_ip=ip,
    )


async def test_login_locks_account_after_repeated_failures(monkeypatch, fake_redis):
    _patch_login(monkeypatch)
    for i in range(auth_module.LOGIN_ACCOUNT_FAIL_LIMIT):
        with pytest.raises(UnauthorizedError):
            await _login("wrong", ip=f"198.51.100.{i}")

    with pytest.raises(RateLimitedError):
        await _login("Right1234", ip="203.0.113.99")


async def test_login_success_clears_account_counter(monkeypatch, fake_redis):
    _patch_login(monkeypatch)
    with pytest.raises(UnauthorizedError):
        await _login("wrong")
    assert fake_redis.data["auth:login_fail:acct:1:agent"] == 1

    await _login("Right1234")
    assert "auth:login_fail:acct:1:agent" not in fake_redis.data


async def test_login_ip_limit_blocks_before_lookup(monkeypatch, fake_redis):
    _patch_login(monkeypatch)
    fake_redis.data["auth:login_fail:ip:198.51.100.1"] = auth_module.LOGIN_IP_FAIL_LIMIT

    with pytest.raises(RateLimitedError):
        await _login("Right1234")
    auth_module.TenantRepository.resolve_by_identifier.assert_not_awaited()


async def test_login_fails_open_without_redis(monkeypatch):
    monkeypatch.setattr(login_throttle, "_redis", lambda: None)
    _patch_login(monkeypatch)
    for _ in range(auth_module.LOGIN_ACCOUNT_FAIL_LIMIT + 2):
        with pytest.raises(UnauthorizedError):
            await _login("wrong")
    result = await _login("Right1234")
    assert result.access_token == "signed-token"


# ── Password reset ───────────────────────────────────────────────────────


def _patch_reset(monkeypatch, user):
    tenant = SimpleNamespace(id=1, is_active=True)
    monkeypatch.setattr(reset_module.TenantRepository, "resolve_by_identifier", AsyncMock(return_value=tenant))
    monkeypatch.setattr(reset_module.EmployeeRepository, "get_by_username_or_email", AsyncMock(return_value=user))
    monkeypatch.setattr(reset_module.EmployeeRepository, "update_password", AsyncMock())
    email_client = SimpleNamespace(send=AsyncMock())
    monkeypatch.setattr(reset_module, "create_email_client", lambda: email_client)
    return email_client


def _send_request():
    return SendVerifyCodeRequest(tenant="t", username="agent", locale="zh")


def _reset_request(code: str):
    return ResetPasswordRequest(tenant="t", username="agent", verify_code=code, new_password="NewPass123")


@pytest.mark.parametrize("user", [None, SimpleNamespace(id=42, email=None)])
async def test_send_code_is_silent_for_unknown_or_emailless_accounts(monkeypatch, user):
    redis = FakeRedis()
    email_client = _patch_reset(monkeypatch, user)

    await PasswordResetService.send_verify_code(AsyncMock(), redis, _send_request())

    email_client.send.assert_not_awaited()
    assert redis.data == {}


async def test_send_code_uses_crypto_random(monkeypatch):
    redis = FakeRedis()
    _patch_reset(monkeypatch, SimpleNamespace(id=42, email="a@example.com"))
    monkeypatch.setattr(reset_module.secrets, "randbelow", lambda n: 1234)

    await PasswordResetService.send_verify_code(AsyncMock(), redis, _send_request())

    assert redis.data["verify_code:1:42"] == "001234"


async def test_reset_unknown_account_looks_like_wrong_code(monkeypatch):
    _patch_reset(monkeypatch, None)
    with pytest.raises(InvalidCodeError):
        await PasswordResetService.reset_password(AsyncMock(), FakeRedis(), _reset_request("123456"))


async def test_reset_code_is_burned_after_max_wrong_attempts(monkeypatch):
    redis = FakeRedis()
    _patch_reset(monkeypatch, SimpleNamespace(id=42, email="a@example.com"))
    redis.data["verify_code:1:42"] = "654321"

    for _ in range(VERIFY_CODE_MAX_ATTEMPTS):
        with pytest.raises(InvalidCodeError):
            await PasswordResetService.reset_password(AsyncMock(), redis, _reset_request("000000"))

    assert "verify_code:1:42" not in redis.data
    with pytest.raises(InvalidCodeError):
        await PasswordResetService.reset_password(AsyncMock(), redis, _reset_request("654321"))
    reset_module.EmployeeRepository.update_password.assert_not_awaited()


async def test_reset_with_correct_code_updates_password_and_clears_keys(monkeypatch):
    redis = FakeRedis()
    _patch_reset(monkeypatch, SimpleNamespace(id=42, email="a@example.com"))
    redis.data["verify_code:1:42"] = "654321"
    redis.data["verify_attempts:1:42"] = 2

    await PasswordResetService.reset_password(AsyncMock(), redis, _reset_request("654321"))

    reset_module.EmployeeRepository.update_password.assert_awaited_once()
    assert redis.data == {}


# ── Visitor message types ────────────────────────────────────────────────


@pytest.mark.parametrize("content_type", ["rich_text", "system", "internal_note", "welcome"])
async def test_visitor_cannot_send_privileged_content_types(monkeypatch, content_type):
    lookup = AsyncMock()
    monkeypatch.setattr(ConversationService, "get_conversation_for_visitor_session", lookup)

    with pytest.raises(ValidationError):
        await ConversationService.send_visitor_message_for_session(
            AsyncMock(),
            conversation_public_id="c1",
            visitor_context={"tenant_id": 1, "channel_id": 1, "visitor_external_id": "v"},
            content_type=content_type,
            content="<a href=javascript:alert(1)>x</a>",
        )
    lookup.assert_not_awaited()


# ── Field definition tenant isolation ────────────────────────────────────


async def test_field_definition_of_other_tenant_is_not_found(monkeypatch):
    from app.services import fd_field_definition_service as fd_module

    definition = SimpleNamespace(id=5, tenant_id=2)
    monkeypatch.setattr(fd_module.FdFieldDefinitionRepository, "get_by_id", AsyncMock(return_value=definition))
    options = AsyncMock(return_value=[])
    tree = AsyncMock(return_value=[])
    monkeypatch.setattr(fd_module.FdFieldDefinitionRepository, "get_options", options)
    monkeypatch.setattr(fd_module.FdFieldDefinitionRepository, "get_tree_nodes", tree)

    with pytest.raises(NotFoundError):
        await FdFieldDefinitionService.get_by_id(AsyncMock(), 5, 1)
    with pytest.raises(NotFoundError):
        await FdFieldDefinitionService.get_options(AsyncMock(), 5, 1)
    with pytest.raises(NotFoundError):
        await FdFieldDefinitionService.get_tree_nodes(AsyncMock(), 5, 1)
    options.assert_not_awaited()
    tree.assert_not_awaited()

    assert await FdFieldDefinitionService.get_by_id(AsyncMock(), 5, 2) is definition
    assert await FdFieldDefinitionService.get_options(AsyncMock(), 5, 2) == []


# ── First-run admin seed ─────────────────────────────────────────────────


def _db_with_tenant_count(count: int):
    db = MagicMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: count))
    return db


@pytest.mark.parametrize("password", ["", "Admin123456"])
async def test_seed_refuses_documented_admin_password_in_production(monkeypatch, password):
    monkeypatch.setattr(seed, "is_production_env", lambda: True)
    monkeypatch.setattr(seed.settings, "DEFAULT_ADMIN_PASSWORD", password)
    db = _db_with_tenant_count(0)

    with pytest.raises(RuntimeError, match="DEFAULT_ADMIN_PASSWORD"):
        await seed._ensure_default_tenant(db)
    db.add.assert_not_called()


async def test_seed_is_noop_for_existing_deployments(monkeypatch):
    monkeypatch.setattr(seed, "is_production_env", lambda: True)
    monkeypatch.setattr(seed.settings, "DEFAULT_ADMIN_PASSWORD", "Admin123456")
    db = _db_with_tenant_count(3)

    await seed._ensure_default_tenant(db)
    db.add.assert_not_called()
