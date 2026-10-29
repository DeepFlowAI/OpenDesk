"""Module contract for frozen, authorized exports.

Register production types at application import time. Implementations must use
short database sessions and release them before external I/O. Tests can register
an in-memory type without exposing a sample exporter to users.
"""
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from app.schemas.permission import EffectivePrincipal


@dataclass(frozen=True)
class FrozenExport:
    config: dict
    summary: dict[str, str]
    safe_summary: dict[str, str]


@dataclass(frozen=True)
class ExportFile:
    data: bytes
    filename: str
    content_type: str
    row_count: int
    manifest: dict
    scope_reduced: bool = False


class ExportType(Protocol):
    kind: str
    name: dict[str, str]
    business_type: dict[str, str]
    permissions: tuple[str, ...]
    max_file_bytes: int

    async def freeze(self, principal: EffectivePrincipal, config: dict) -> FrozenExport:
        """Validate effective input, resolve relative dates and freeze selected fields.

        safe_summary contains only condition labels/counts, never search text or
        business entity names. Reject unsupported or stale configuration.
        """
        ...

    async def generate(
        self, snapshot: dict, principal: EffectivePrincipal,
        checkpoint: Callable[[], Awaitable[None]],
    ) -> ExportFile:
        """Read the intersection of snapshot.principal and current record access.

        Page without duplicates, enforce module limits without truncation, and
        call checkpoint between batches. Include every output record in manifest
        (or equivalent evidence) for full-file authorization. Empty output still
        needs authorization and contains headers.
        """
        ...

    async def can_download(self, principal: EffectivePrincipal, snapshot: dict, manifest: dict) -> bool:
        """Recheck all output records including current ownership/group membership.

        Return False if full-file authorization cannot be established.
        """
        ...


_export_types: dict[str, ExportType] = {}


def register_export_type(export_type: ExportType) -> None:
    if export_type.kind in _export_types:
        raise ValueError("Export type already registered")
    if not export_type.permissions or export_type.max_file_bytes <= 0:
        raise ValueError("Export type requires permissions and a file limit")
    _export_types[export_type.kind] = export_type


def get_export_type(kind: str) -> ExportType | None:
    return _export_types.get(kind)


def available_export_types(principal: EffectivePrincipal) -> list[ExportType]:
    return [item for item in _export_types.values() if principal.has_all_permissions(list(item.permissions))]
