"""Add an index for tenant-scoped normalized phone lookup.

Revision ID: a6c8e0f2b4d6
Revises: 85c1e2150f10
"""
from alembic import op
import sqlalchemy as sa

revision = "a6c8e0f2b4d6"
down_revision = "85c1e2150f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_users_tenant_normalized_phone",
            "users",
            ["tenant_id", sa.text(r"regexp_replace(regexp_replace(phone, '\D', '', 'g'), '^00', '')")],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_users_tenant_normalized_phone",
            table_name="users",
            postgresql_concurrently=True,
            if_exists=True,
        )
