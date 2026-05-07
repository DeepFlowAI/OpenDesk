"""
Hardcoded metadata field definitions shared by all tenants / domains.

Metadata fields are ALWAYS visible in list views and detail pages.
They cannot be toggled on/off in field-configuration UI — they are
guaranteed to render for every record.

To add a new metadata field (e.g. a sort_key column), append it here
and add the corresponding DB column in MetadataMixin.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetadataFieldDef:
    key: str
    name_zh: str
    name_en: str
    field_type: str
    type_config: dict = field(default_factory=dict)
    description: str | None = None
    default_sort_order: int = 0


METADATA_FIELDS: tuple[MetadataFieldDef, ...] = (
    MetadataFieldDef(
        key="created_at",
        name_zh="创建时间",
        name_en="Created At",
        field_type="datetime",
        description="Record creation timestamp, auto-generated.",
        default_sort_order=1,
    ),
    MetadataFieldDef(
        key="updated_at",
        name_zh="更新时间",
        name_en="Updated At",
        field_type="datetime",
        description="Last modification timestamp, auto-updated.",
        default_sort_order=2,
    ),
)


def get_metadata_fields() -> tuple[MetadataFieldDef, ...]:
    return METADATA_FIELDS


def get_metadata_field(key: str) -> MetadataFieldDef | None:
    for f in METADATA_FIELDS:
        if f.key == key:
            return f
    return None
