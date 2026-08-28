"""Unit tests for role seeding."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.permission_catalog import SYSTEM_ROLE_PRESETS
from app.services.role_service import RoleService, normalize_data_scopes, normalize_permissions


def _synced_system_role(key: str) -> SimpleNamespace:
    preset = SYSTEM_ROLE_PRESETS[key]
    return SimpleNamespace(
        name=preset["name"],
        description=preset["description"],
        is_system=True,
        is_active=True,
        permissions=normalize_permissions(preset["permissions"]),
        data_scopes=normalize_data_scopes(preset["data_scopes"]),
    )


@pytest.mark.asyncio
async def test_ensure_system_roles_commits_when_creating_missing_roles():
    db = AsyncMock()
    db.add = MagicMock()

    with patch(
        "app.services.role_service.RoleRepository.get_by_key",
        AsyncMock(return_value=None),
    ):
        await RoleService.ensure_system_roles(db, tenant_id=99)

    assert db.add.call_count == 2
    db.flush.assert_awaited()
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_ensure_system_roles_does_not_commit_when_already_in_sync():
    roles = {"admin": _synced_system_role("admin"), "agent": _synced_system_role("agent")}
    db = AsyncMock()
    db.add = MagicMock()

    async def _get_by_key(_db, _tenant_id, key: str):
        return roles[key]

    with patch(
        "app.services.role_service.RoleRepository.get_by_key",
        side_effect=_get_by_key,
    ):
        await RoleService.ensure_system_roles(db, tenant_id=99)

    db.add.assert_not_called()
    db.flush.assert_not_awaited()
    db.commit.assert_not_awaited()
