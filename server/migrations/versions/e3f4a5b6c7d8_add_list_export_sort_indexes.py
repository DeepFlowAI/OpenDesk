"""Add list/export default-sort and org-user indexes.

Revision ID: e3f4a5b6c7d8
Revises: b058e701a001
Create Date: 2026-09-14

Additive btree indexes for the default list/export ORDER BY shapes:
- tickets (tenant_id, updated_at DESC, id DESC)
- users (tenant_id, created_at DESC, id DESC)
- organizations (tenant_id, updated_at DESC, id DESC)
- users (tenant_id, organization_id) for batched org user-count GROUP BY

Hot custom-field slot indexes are NOT created here. There is no in-repo
signal for which fd_field_definitions.slot_column values are high-frequency
filters. After a slow SQL names a real slot, create a partial btree with:

    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_<table>_tenant_<slot>
    ON <table> (tenant_id, <slot>);

Use tools/create_hot_slot_indexes.py to list allocated slots or to create
an explicitly named (tenant_id, slot) index. Do not pre-build every slot.

If CREATE INDEX CONCURRENTLY fails, DROP INDEX the leftover INVALID index
before rerunning.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "b058e701a001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_index(name: str, table: str, columns: list) -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            name,
            table,
            columns,
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def _drop_index(name: str, table: str) -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            name,
            table_name=table,
            postgresql_concurrently=True,
            if_exists=True,
        )


def upgrade() -> None:
    _create_index(
        "ix_tickets_tenant_updated_id",
        "tickets",
        ["tenant_id", sa.literal_column("updated_at DESC"), sa.literal_column("id DESC")],
    )
    _create_index(
        "ix_users_tenant_created_id",
        "users",
        ["tenant_id", sa.literal_column("created_at DESC"), sa.literal_column("id DESC")],
    )
    _create_index(
        "ix_organizations_tenant_updated_id",
        "organizations",
        ["tenant_id", sa.literal_column("updated_at DESC"), sa.literal_column("id DESC")],
    )
    _create_index(
        "ix_users_tenant_organization_id",
        "users",
        ["tenant_id", "organization_id"],
    )


def downgrade() -> None:
    _drop_index("ix_users_tenant_organization_id", "users")
    _drop_index("ix_organizations_tenant_updated_id", "organizations")
    _drop_index("ix_users_tenant_created_id", "users")
    _drop_index("ix_tickets_tenant_updated_id", "tickets")
