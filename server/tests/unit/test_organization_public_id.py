"""
Unit tests for organization public IDs.
"""
from types import SimpleNamespace

import pytest

from app.core.exceptions import NotFoundError
from app.repositories.organization_repository import (
    OrganizationRepository,
    ORGANIZATION_PUBLIC_ID_PREFIX,
    ORGANIZATION_PUBLIC_ID_RANDOM_LENGTH,
    is_valid_organization_public_id,
)
from app.services.organization_service import OrganizationService


class _DummyDB:
    """Sentinel async session for repository-patched service tests."""


class TestOrganizationPublicId:

    def test_generate_public_id_uses_org_prefix(self):
        public_id = OrganizationRepository.generate_public_id()

        assert public_id.startswith(ORGANIZATION_PUBLIC_ID_PREFIX)
        assert len(public_id) == len(ORGANIZATION_PUBLIC_ID_PREFIX) + ORGANIZATION_PUBLIC_ID_RANDOM_LENGTH
        assert is_valid_organization_public_id(public_id)

    def test_public_id_validation_rejects_wrong_shape(self):
        assert is_valid_organization_public_id(
            f"{ORGANIZATION_PUBLIC_ID_PREFIX}{'A' * ORGANIZATION_PUBLIC_ID_RANDOM_LENGTH}"
        )
        assert not is_valid_organization_public_id(f"{ORGANIZATION_PUBLIC_ID_PREFIX}{'A' * 32}")
        assert not is_valid_organization_public_id(f"usr_{'A' * ORGANIZATION_PUBLIC_ID_RANDOM_LENGTH}")

    @pytest.mark.asyncio
    async def test_get_by_ref_accepts_public_id(self, monkeypatch):
        org = SimpleNamespace(id=42, tenant_id=10, public_id="org_test", name="Acme")

        async def fake_get_by_public_id(_db, public_id: str):
            assert public_id == "org_test"
            return org

        async def fake_slot_map(_db, tenant_id: int):
            assert tenant_id == 10
            return {}

        async def fake_count_users(_db, tenant_id: int, org_id: int):
            assert (tenant_id, org_id) == (10, 42)
            return 3

        monkeypatch.setattr(OrganizationRepository, "get_by_public_id", fake_get_by_public_id)
        monkeypatch.setattr(OrganizationRepository, "count_users", fake_count_users)
        monkeypatch.setattr(OrganizationService, "_get_field_key_slot_map", fake_slot_map)
        monkeypatch.setattr(
            OrganizationService,
            "_enrich_response",
            lambda item, _slots, user_count=0: {"id": item.id, "user_count": user_count},
        )

        result = await OrganizationService.get_by_ref(_DummyDB(), 10, "org_test")

        assert result == {"id": 42, "user_count": 3}

    @pytest.mark.asyncio
    async def test_get_by_ref_rejects_cross_tenant_public_id(self, monkeypatch):
        org = SimpleNamespace(id=42, tenant_id=99, public_id="org_test", name="Acme")

        async def fake_get_by_public_id(_db, _public_id: str):
            return org

        monkeypatch.setattr(OrganizationRepository, "get_by_public_id", fake_get_by_public_id)

        with pytest.raises(NotFoundError):
            await OrganizationService.get_by_ref(_DummyDB(), 10, "org_test")

    @pytest.mark.asyncio
    async def test_get_by_ref_keeps_numeric_id_compatibility(self, monkeypatch):
        org = SimpleNamespace(id=42, tenant_id=10, public_id="org_test", name="Acme")

        async def fake_get_by_id(_db, org_id: int):
            assert org_id == 42
            return org

        async def fake_slot_map(_db, tenant_id: int):
            assert tenant_id == 10
            return {}

        async def fake_count_users(_db, tenant_id: int, org_id: int):
            assert (tenant_id, org_id) == (10, 42)
            return 0

        monkeypatch.setattr(OrganizationRepository, "get_by_id", fake_get_by_id)
        monkeypatch.setattr(OrganizationRepository, "count_users", fake_count_users)
        monkeypatch.setattr(OrganizationService, "_get_field_key_slot_map", fake_slot_map)
        monkeypatch.setattr(
            OrganizationService,
            "_enrich_response",
            lambda item, _slots, user_count=0: {"public_id": item.public_id},
        )

        result = await OrganizationService.get_by_ref(_DummyDB(), 10, "42")

        assert result == {"public_id": "org_test"}
