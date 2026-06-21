"""standardize datetime columns with timezone

Revision ID: 9a0b1c2d3e4f
Revises: 8e9f0a1b2c3d
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a0b1c2d3e4f"
down_revision: Union[str, Sequence[str], None] = "8e9f0a1b2c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_TIMEZONE = "Asia/Shanghai"

DATETIME_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("agent_status", ("status_changed_at", "created_at", "updated_at")),
    ("agent_webrtc_sessions", ("started_at", "ended_at")),
    ("api_keys", ("disabled_at", "last_used_at", "created_at", "updated_at")),
    ("audio_assets", ("deleted_at", "created_at", "updated_at")),
    ("call_records", ("started_at", "answered_at", "ended_at", "created_at", "updated_at")),
    ("call_summary_config_fields", ("created_at", "updated_at")),
    ("call_summary_configs", ("created_at", "updated_at")),
    ("call_summary_field_values", ("created_at", "updated_at")),
    ("call_summary_interaction_rules", ("created_at", "updated_at")),
    ("channels", ("key_rotated_at", "created_at", "updated_at")),
    ("conversations", ("started_at", "ended_at", "last_message_at", "created_at", "updated_at")),
    ("cs_summary_config_fields", ("created_at", "updated_at")),
    ("cs_summary_configs", ("created_at", "updated_at")),
    ("cs_summary_field_values", ("created_at", "updated_at")),
    ("cs_summary_interaction_rules", ("created_at", "updated_at")),
    ("emoji_settings", ("created_at", "updated_at")),
    ("employee_group_members", ("created_at",)),
    ("employee_groups", ("created_at", "updated_at")),
    ("employee_roles", ("created_at",)),
    ("employees", ("last_login_at", "created_at", "updated_at")),
    ("entity_changes", ("created_at", "updated_at")),
    ("fd_field_definitions", ("created_at", "updated_at")),
    ("fd_field_options", ("created_at", "updated_at")),
    ("fd_form_layout_fields", ("created_at", "updated_at")),
    ("fd_form_layout_sections", ("created_at", "updated_at")),
    ("fd_form_layout_tabs", ("created_at", "updated_at")),
    ("fd_form_layouts", ("created_at", "updated_at")),
    ("fd_interaction_rules", ("created_at", "updated_at")),
    ("fd_system_field_overrides", ("created_at", "updated_at")),
    ("fd_tree_nodes", ("created_at", "updated_at")),
    ("inbound_routing_rules", ("created_at", "updated_at")),
    ("knowledge_directories", ("created_at", "updated_at")),
    ("knowledge_documents", ("valid_from", "valid_to", "created_at", "updated_at")),
    ("messages", ("created_at",)),
    ("offline_message_entries", ("created_at",)),
    (
        "offline_messages",
        ("handled_at", "last_message_at", "customer_unread_at", "customer_read_at", "created_at", "updated_at"),
    ),
    ("open_agent_settings", ("created_at", "updated_at")),
    ("organization_views", ("created_at", "updated_at")),
    ("organizations", ("created_at", "updated_at", "datetime_1", "datetime_2", "datetime_3", "datetime_4", "datetime_5")),
    ("phone_number_tenant_meta", ("created_at", "updated_at")),
    ("phone_numbers", ("created_at", "updated_at")),
    ("queue_assignment_events", ("created_at",)),
    ("queue_outbox_events", ("next_retry_at", "created_at", "sent_at")),
    ("queue_policies", ("created_at", "updated_at")),
    ("queue_round_robin_states", ("created_at", "updated_at")),
    (
        "queue_tasks",
        (
            "enqueued_at",
            "assigning_at",
            "assigned_at",
            "canceled_at",
            "timeout_at",
            "deadline_at",
            "created_at",
            "updated_at",
        ),
    ),
    ("roles", ("created_at", "updated_at")),
    ("satisfaction_survey_config_versions", ("published_at", "created_at", "updated_at")),
    ("satisfaction_survey_configs", ("created_at", "updated_at")),
    ("satisfaction_survey_records", ("invited_at", "submitted_at", "created_at", "updated_at")),
    ("service_hours", ("created_at", "updated_at")),
    ("session_routing_rules", ("created_at", "updated_at")),
    ("sip_trunks", ("created_at", "updated_at")),
    ("system_settings", ("created_at", "updated_at")),
    ("tenants", ("created_at", "updated_at")),
    ("ticket_changes", ("created_at", "updated_at")),
    ("ticket_comments", ("created_at", "updated_at")),
    ("ticket_views", ("created_at", "updated_at")),
    ("ticket_workflow_versions", ("created_at", "updated_at")),
    ("ticket_workflows", ("deleted_at", "created_at", "updated_at")),
    ("tickets", ("created_at", "updated_at", "datetime_1", "datetime_2", "datetime_3", "datetime_4", "datetime_5")),
    ("user_views", ("created_at", "updated_at")),
    ("users", ("created_at", "updated_at", "datetime_1", "datetime_2", "datetime_3", "datetime_4", "datetime_5")),
    ("voice_flow_versions", ("created_at", "updated_at")),
    ("voice_flows", ("deleted_at", "created_at", "updated_at")),
    ("welcome_message_rules", ("created_at", "updated_at")),
)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _column_data_type(table_name: str, column_name: str) -> str | None:
    bind = op.get_bind()
    return bind.execute(
        sa.text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar_one_or_none()


def _alter_if_type(table_name: str, column_name: str, *, source_type: str, target_sql: str, using_sql: str) -> None:
    if _column_data_type(table_name, column_name) != source_type:
        return
    table = _quote(table_name)
    column = _quote(column_name)
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {target_sql} USING {using_sql.format(column=column)}"
        )
    )


def upgrade() -> None:
    for table_name, columns in DATETIME_COLUMNS:
        for column_name in columns:
            _alter_if_type(
                table_name,
                column_name,
                source_type="timestamp without time zone",
                target_sql="TIMESTAMP WITH TIME ZONE",
                using_sql="{column} AT TIME ZONE '" + LEGACY_TIMEZONE + "'",
            )


def downgrade() -> None:
    for table_name, columns in DATETIME_COLUMNS:
        for column_name in columns:
            _alter_if_type(
                table_name,
                column_name,
                source_type="timestamp with time zone",
                target_sql="TIMESTAMP WITHOUT TIME ZONE",
                using_sql="{column} AT TIME ZONE '" + LEGACY_TIMEZONE + "'",
            )
