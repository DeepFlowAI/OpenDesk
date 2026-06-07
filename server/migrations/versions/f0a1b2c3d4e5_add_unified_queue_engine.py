"""add unified queue engine

Revision ID: f0a1b2c3d4e5
Revises: e8f9a0b1c2d3
Create Date: 2026-05-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "queue_tasks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("task_type", sa.String(32), nullable=False),
        sa.Column("task_ref_id", sa.String(128), nullable=False),
        sa.Column("task_ref_public_id", sa.String(128), nullable=True),
        sa.Column("queue_type", sa.String(32), nullable=False),
        sa.Column("queue_id", sa.Integer, nullable=False),
        sa.Column("priority", sa.SmallInteger, nullable=False, server_default="5"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("source_type", sa.String(64), nullable=False, server_default="manual_api"),
        sa.Column("source_context", JSONB, nullable=False, server_default="{}"),
        sa.Column("policy_snapshot", JSONB, nullable=False, server_default="{}"),
        sa.Column("assignment_strategy", sa.String(64), nullable=True),
        sa.Column("assigned_agent_id", sa.Integer, nullable=True),
        sa.Column("assigned_by", sa.String(32), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("assigning_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_agent_id"], ["employees.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_queue_tasks_dispatch",
        "queue_tasks",
        ["tenant_id", "channel", "queue_type", "queue_id", "status", "priority", "enqueued_at", "id"],
    )
    op.create_index("ix_queue_tasks_ref", "queue_tasks", ["tenant_id", "task_type", "task_ref_id"])
    op.create_index("ix_queue_tasks_deadline", "queue_tasks", ["tenant_id", "status", "deadline_at"])
    op.create_index(
        "uq_queue_tasks_active_ref",
        "queue_tasks",
        ["tenant_id", "channel", "task_type", "task_ref_id"],
        unique=True,
        postgresql_where=sa.text("status in ('queued', 'assigning')"),
    )

    op.create_table(
        "queue_policies",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.Integer, nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("assignment_strategy", sa.String(64), nullable=True),
        sa.Column("max_waiting_count", sa.Integer, nullable=True),
        sa.Column("max_wait_seconds", sa.Integer, nullable=True),
        sa.Column("config", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_queue_policies_lookup",
        "queue_policies",
        ["tenant_id", "channel", "scope_type", "scope_id"],
    )
    op.create_index(
        "uq_queue_policies_scope",
        "queue_policies",
        ["tenant_id", "channel", "scope_type", sa.text("coalesce(scope_id, 0)")],
        unique=True,
    )

    op.create_table(
        "queue_round_robin_states",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("queue_type", sa.String(32), nullable=False),
        sa.Column("queue_id", sa.Integer, nullable=False),
        sa.Column("last_agent_id", sa.Integer, nullable=True),
        sa.Column("cursor_payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_agent_id"], ["employees.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "channel", "queue_type", "queue_id", name="uq_queue_rr_scope"),
    )

    op.create_table(
        "queue_assignment_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("task_id", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("queue_type", sa.String(32), nullable=False),
        sa.Column("queue_id", sa.Integer, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.Integer, nullable=True),
        sa.Column("strategy", sa.String(64), nullable=True),
        sa.Column("policy_source", sa.String(64), nullable=True),
        sa.Column("priority", sa.SmallInteger, nullable=False),
        sa.Column("before_load", JSONB, nullable=True),
        sa.Column("after_load", JSONB, nullable=True),
        sa.Column("operator_id", sa.Integer, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["queue_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["employees.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_queue_assignment_events_task", "queue_assignment_events", ["task_id"])
    op.create_index(
        "ix_queue_assignment_events_tenant_created",
        "queue_assignment_events",
        ["tenant_id", "created_at"],
    )

    op.create_table(
        "queue_outbox_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_queue_outbox_pending", "queue_outbox_events", ["status", "next_retry_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_queue_outbox_pending", table_name="queue_outbox_events")
    op.drop_table("queue_outbox_events")

    op.drop_index("ix_queue_assignment_events_tenant_created", table_name="queue_assignment_events")
    op.drop_index("ix_queue_assignment_events_task", table_name="queue_assignment_events")
    op.drop_table("queue_assignment_events")

    op.drop_table("queue_round_robin_states")

    op.drop_index("uq_queue_policies_scope", table_name="queue_policies")
    op.drop_index("ix_queue_policies_lookup", table_name="queue_policies")
    op.drop_table("queue_policies")

    op.drop_index("uq_queue_tasks_active_ref", table_name="queue_tasks")
    op.drop_index("ix_queue_tasks_deadline", table_name="queue_tasks")
    op.drop_index("ix_queue_tasks_ref", table_name="queue_tasks")
    op.drop_index("ix_queue_tasks_dispatch", table_name="queue_tasks")
    op.drop_table("queue_tasks")
