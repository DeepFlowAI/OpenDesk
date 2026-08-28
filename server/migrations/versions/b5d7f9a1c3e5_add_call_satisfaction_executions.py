"""add call satisfaction executions

Revision ID: b5d7f9a1c3e5
Revises: a4c6e8f0b2d4
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5d7f9a1c3e5"
down_revision: Union[str, None] = "a4c6e8f0b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_satisfaction_executions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("call_record_id", sa.BigInteger(), nullable=False),
        sa.Column("satisfaction_flow_id", sa.Integer(), nullable=False),
        sa.Column("satisfaction_flow_version_id", sa.Integer(), nullable=False),
        sa.Column("trigger_source", sa.String(length=24), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default="preparing",
            nullable=False,
        ),
        sa.Column("flow_name_snapshot", sa.String(length=50), nullable=False),
        sa.Column("flow_version_no", sa.Integer(), nullable=False),
        sa.Column("agent_id_snapshot", sa.Integer(), nullable=True),
        sa.Column("agent_name_snapshot", sa.String(length=128), nullable=True),
        sa.Column("queue_type_snapshot", sa.String(length=24), nullable=True),
        sa.Column("queue_id_snapshot", sa.Integer(), nullable=True),
        sa.Column("queue_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("termination_reason", sa.String(length=64), nullable=True),
        sa.Column("answer_count", sa.Integer(), server_default="0", nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["call_record_id"], ["call_records.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["satisfaction_flow_id"], ["satisfaction_flows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["satisfaction_flow_version_id"],
            ["satisfaction_flow_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_record_id", name="uq_cse_call_record"),
    )
    op.create_index(
        "ix_cse_tenant_status_started",
        "call_satisfaction_executions",
        ["tenant_id", "status", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_cse_tenant_flow_version",
        "call_satisfaction_executions",
        ["tenant_id", "satisfaction_flow_version_id"],
        unique=False,
    )

    op.create_table(
        "call_satisfaction_answers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.BigInteger(), nullable=False),
        sa.Column("question_node_id", sa.String(length=64), nullable=False),
        sa.Column("question_name_snapshot", sa.String(length=50), nullable=False),
        sa.Column("question_order", sa.Integer(), nullable=False),
        sa.Column("option_id", sa.String(length=64), nullable=False),
        sa.Column("option_label_snapshot", sa.String(length=30), nullable=False),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["call_satisfaction_executions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_id", "question_node_id", name="uq_csa_execution_question"
        ),
    )
    op.create_index(
        "ix_csa_tenant_execution_order",
        "call_satisfaction_answers",
        ["tenant_id", "execution_id", "question_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_csa_tenant_execution_order", table_name="call_satisfaction_answers"
    )
    op.drop_table("call_satisfaction_answers")
    op.drop_index(
        "ix_cse_tenant_flow_version", table_name="call_satisfaction_executions"
    )
    op.drop_index(
        "ix_cse_tenant_status_started", table_name="call_satisfaction_executions"
    )
    op.drop_table("call_satisfaction_executions")
