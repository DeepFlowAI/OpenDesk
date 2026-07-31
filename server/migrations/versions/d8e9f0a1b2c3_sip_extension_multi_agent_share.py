"""sip extension multi-agent share bindings and occupant

Revision ID: d8e9f0a1b2c3
Revises: 44d667f1c990
Create Date: 2026-07-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, None] = "44d667f1c990"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sip_extension_bindings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("extension_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["extension_id"], ["sip_extensions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", name="uq_sip_ext_binding_employee"),
        sa.UniqueConstraint(
            "extension_id", "employee_id", name="uq_sip_ext_binding_ext_employee"
        ),
    )
    op.create_index(
        "ix_sip_ext_binding_extension_id",
        "sip_extension_bindings",
        ["extension_id"],
        unique=False,
    )
    op.create_index(
        "ix_sip_ext_binding_tenant_id",
        "sip_extension_bindings",
        ["tenant_id"],
        unique=False,
    )

    op.add_column(
        "sip_extensions",
        sa.Column("current_occupant_employee_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_sip_ext_current_occupant",
        "sip_extensions",
        "employees",
        ["current_occupant_employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_sip_ext_current_occupant",
        "sip_extensions",
        ["current_occupant_employee_id"],
        unique=False,
    )

    # Migrate existing 1:1 bindings into the new table.
    op.execute(
        """
        INSERT INTO sip_extension_bindings (
            tenant_id, extension_id, employee_id, created_at, updated_at
        )
        SELECT
            tenant_id, id, bound_employee_id, NOW(), NOW()
        FROM sip_extensions
        WHERE bound_employee_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    # Agents already using sip_phone keep occupancy so live shifts are not disrupted.
    op.execute(
        """
        UPDATE sip_extensions AS e
        SET current_occupant_employee_id = e.bound_employee_id
        FROM agent_call_devices AS d
        WHERE e.bound_employee_id IS NOT NULL
          AND d.tenant_id = e.tenant_id
          AND d.employee_id = e.bound_employee_id
          AND d.device_type = 'sip_phone'
        """
    )

    op.drop_constraint("uq_sip_ext_bound_employee", "sip_extensions", type_="unique")
    op.drop_constraint(
        "sip_extensions_bound_employee_id_fkey", "sip_extensions", type_="foreignkey"
    )
    op.drop_column("sip_extensions", "bound_employee_id")


def downgrade() -> None:
    op.add_column(
        "sip_extensions",
        sa.Column("bound_employee_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "sip_extensions_bound_employee_id_fkey",
        "sip_extensions",
        "employees",
        ["bound_employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_sip_ext_bound_employee", "sip_extensions", ["bound_employee_id"]
    )

    # Best-effort restore: pick one binding per extension (lowest employee_id).
    op.execute(
        """
        UPDATE sip_extensions AS e
        SET bound_employee_id = b.employee_id
        FROM (
            SELECT DISTINCT ON (extension_id) extension_id, employee_id
            FROM sip_extension_bindings
            ORDER BY extension_id, employee_id
        ) AS b
        WHERE e.id = b.extension_id
        """
    )

    op.drop_index("ix_sip_ext_current_occupant", table_name="sip_extensions")
    op.drop_constraint("fk_sip_ext_current_occupant", "sip_extensions", type_="foreignkey")
    op.drop_column("sip_extensions", "current_occupant_employee_id")

    op.drop_index("ix_sip_ext_binding_tenant_id", table_name="sip_extension_bindings")
    op.drop_index("ix_sip_ext_binding_extension_id", table_name="sip_extension_bindings")
    op.drop_table("sip_extension_bindings")
