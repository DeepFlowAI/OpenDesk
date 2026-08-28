"""add scheduling shifts and assignments

Revision ID: b5c7d9e1f3a5
Revises: e7f8a9b0c1d2
Create Date: 2026-08-08 12:00:00.000000

Scheduling Center phase 1: shift templates (schedule_shifts) and per-day
assignment records (schedule_assignments). Additive only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5c7d9e1f3a5"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_shifts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=20), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_schedule_shifts_tenant_name"),
    )
    op.create_index("ix_schedule_shifts_tenant_id", "schedule_shifts", ["tenant_id"], unique=False)

    op.create_table(
        "schedule_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("shift_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_id"], ["schedule_shifts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "employee_id", "shift_id", "date",
            name="uq_schedule_assignments_emp_shift_date",
        ),
    )
    op.create_index(
        "ix_schedule_assignments_tenant_date", "schedule_assignments", ["tenant_id", "date"], unique=False
    )
    op.create_index(
        "ix_schedule_assignments_tenant_shift", "schedule_assignments", ["tenant_id", "shift_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_assignments_tenant_shift", table_name="schedule_assignments")
    op.drop_index("ix_schedule_assignments_tenant_date", table_name="schedule_assignments")
    op.drop_table("schedule_assignments")
    op.drop_index("ix_schedule_shifts_tenant_id", table_name="schedule_shifts")
    op.drop_table("schedule_shifts")
