"""
Unit tests for end-user public IDs.
"""
from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError
from app.repositories.user_repository import (
    UserRepository,
    USER_PUBLIC_ID_PREFIX,
    USER_PUBLIC_ID_RANDOM_LENGTH,
    is_valid_user_public_id,
)
from app.services.user_service import UserService


class _DummyDB:
    """Sentinel async session for repository-patched service tests."""


class TestUserPublicId:

    def test_generate_public_id_uses_usr_prefix(self):
        public_id = UserRepository.generate_public_id()

        assert public_id.startswith(USER_PUBLIC_ID_PREFIX)
        assert len(public_id) == len(USER_PUBLIC_ID_PREFIX) + USER_PUBLIC_ID_RANDOM_LENGTH
        assert is_valid_user_public_id(public_id)

    def test_public_id_validation_rejects_overlong_ids(self):
        assert is_valid_user_public_id(f"{USER_PUBLIC_ID_PREFIX}{'A' * USER_PUBLIC_ID_RANDOM_LENGTH}")
        assert not is_valid_user_public_id(f"{USER_PUBLIC_ID_PREFIX}{'A' * 32}")
        assert not is_valid_user_public_id(f"v_{'A' * USER_PUBLIC_ID_RANDOM_LENGTH}")

    @pytest.mark.asyncio
    async def test_get_by_ref_accepts_public_id(self, monkeypatch):
        user = SimpleNamespace(id=42, tenant_id=10, public_id="usr_test", name="A")

        async def fake_get_by_public_id(_db, public_id: str):
            assert public_id == "usr_test"
            return user

        async def fake_slot_map(_db, tenant_id: int):
            assert tenant_id == 10
            return {}

        monkeypatch.setattr(UserRepository, "get_by_public_id", fake_get_by_public_id)
        monkeypatch.setattr(UserService, "_get_field_key_slot_map", fake_slot_map)
        monkeypatch.setattr(UserService, "_enrich_user_response", lambda item, _slots: {"id": item.id})

        result = await UserService.get_by_ref(_DummyDB(), 10, "usr_test")

        assert result == {"id": 42}

    @pytest.mark.asyncio
    async def test_get_by_ref_rejects_cross_tenant_public_id(self, monkeypatch):
        user = SimpleNamespace(id=42, tenant_id=99, public_id="usr_test", name="A")

        async def fake_get_by_public_id(_db, _public_id: str):
            return user

        monkeypatch.setattr(UserRepository, "get_by_public_id", fake_get_by_public_id)

        with pytest.raises(NotFoundError):
            await UserService.get_by_ref(_DummyDB(), 10, "usr_test")

    @pytest.mark.asyncio
    async def test_get_by_ref_keeps_numeric_id_compatibility(self, monkeypatch):
        user = SimpleNamespace(id=42, tenant_id=10, public_id="usr_test", name="A")

        async def fake_get_by_id(_db, user_id: int):
            assert user_id == 42
            return user

        async def fake_slot_map(_db, tenant_id: int):
            assert tenant_id == 10
            return {}

        monkeypatch.setattr(UserRepository, "get_by_id", fake_get_by_id)
        monkeypatch.setattr(UserService, "_get_field_key_slot_map", fake_slot_map)
        monkeypatch.setattr(UserService, "_enrich_user_response", lambda item, _slots: {"public_id": item.public_id})

        result = await UserService.get_by_ref(_DummyDB(), 10, "42")

        assert result == {"public_id": "usr_test"}
