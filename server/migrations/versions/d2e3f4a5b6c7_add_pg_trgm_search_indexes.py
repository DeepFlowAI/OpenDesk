"""Add pg_trgm GIN indexes for list search boxes.

Revision ID: d2e3f4a5b6c7
Revises: e3f4a5b6c7d8
Create Date: 2026-09-14

Keeps the existing ILIKE '%kw%' predicates. pg_trgm GIN lets PostgreSQL
use an index for those leading-wildcard patterns.

Search columns (short text only):
- tickets: title, ticket_number
- users: public_id, name, external_id
- organizations: public_id, name

tickets.description and organizations.description are deferred: they are
long-text columns on hot tables. A GIN trgm index is expensive to build
CONCURRENTLY and costly on writes; evaluate those separately later.

If CREATE INDEX CONCURRENTLY fails, DROP INDEX the leftover INVALID index
before rerunning.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRGM_INDEXES = (
    ("ix_tickets_title_trgm", "tickets", "title"),
    ("ix_tickets_ticket_number_trgm", "tickets", "ticket_number"),
    ("ix_users_public_id_trgm", "users", "public_id"),
    ("ix_users_name_trgm", "users", "name"),
    ("ix_users_external_id_trgm", "users", "external_id"),
    ("ix_organizations_public_id_trgm", "organizations", "public_id"),
    ("ix_organizations_name_trgm", "organizations", "name"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, table, column in _TRGM_INDEXES:
        with op.get_context().autocommit_block():
            op.create_index(
                name,
                table,
                [column],
                unique=False,
                postgresql_using="gin",
                postgresql_ops={column: "gin_trgm_ops"},
                postgresql_concurrently=True,
                if_not_exists=True,
            )


def downgrade() -> None:
    for name, table, _column in reversed(_TRGM_INDEXES):
        with op.get_context().autocommit_block():
            op.drop_index(
                name,
                table_name=table,
                postgresql_concurrently=True,
                if_exists=True,
            )
