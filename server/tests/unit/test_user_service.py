"""
Unit tests for user organization association behavior.
"""
from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserUpdate
from app.services.user_service import UserService


class _DummyDB:
    """Sentinel async session for repository-patched service tests."""


class TestUserServiceOrganizationAssociation:

    @pytest.mark.asyncio
    async def test_update_user_allows_clearing_organization(self, monkeypatch):
        user = SimpleNamespace(id=1, tenant_id=10, organization_id=5)
        captured: dict[str, object] = {}

        async def fake_get_by_id(_db, user_id: int):
            assert user_id == 1
            return user

        async def fake_update(_db, _user, data: dict):
            captured["data"] = data
            return _user

        async def fake_slot_map(_db, tenant_id: int):
            assert tenant_id == 10
            return {}

        async def fake_validate(_db, tenant_id: int, organization_id: int | None):
            captured["validated"] = (tenant_id, organization_id)

        monkeypatch.setattr(UserRepository, "get_by_id", fake_get_by_id)
        monkeypatch.setattr(UserRepository, "update", fake_update)
        monkeypatch.setattr(UserService, "_get_field_key_slot_map", fake_slot_map)
        monkeypatch.setattr(UserService, "_validate_organization", fake_validate)
        monkeypatch.setattr(UserService, "_enrich_user_response", lambda _user, _slot_map: {"id": 1})

        result = await UserService.update_user(
            _DummyDB(),
            tenant_id=10,
            user_id=1,
            data=UserUpdate(organization_id=None),
        )

        assert result == {"id": 1}
        assert captured["data"] == {
            "organization_id": None,
            "updated_by_actor_type": "system",
            "updated_by_actor_id": None,
            "updated_by_actor_name": "System",
        }
        assert captured["validated"] == (10, None)

    @pytest.mark.asyncio
    async def test_validate_organization_rejects_other_tenant(self, monkeypatch):
        async def fake_get_by_id(_db, organization_id: int):
            assert organization_id == 3
            return SimpleNamespace(id=3, tenant_id=99)

        monkeypatch.setattr(OrganizationRepository, "get_by_id", fake_get_by_id)

        with pytest.raises(NotFoundError):
            await UserService._validate_organization(_DummyDB(), tenant_id=10, organization_id=3)

    @pytest.mark.asyncio
    async def test_validate_organization_accepts_empty_value(self, monkeypatch):
        async def fake_get_by_id(*_args, **_kwargs):
            raise AssertionError("No repository lookup is needed for an empty organization")

        monkeypatch.setattr(OrganizationRepository, "get_by_id", fake_get_by_id)

        await UserService._validate_organization(_DummyDB(), tenant_id=10, organization_id=None)
