"""Add personal export tasks.

Revision ID: b058e701a001
Revises: a066cc22bd0a
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b058e701a001"
down_revision = "a066cc22bd0a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('export_tasks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('idempotency_key', sa.UUID(), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=64), nullable=False),
    sa.Column('name', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('business_type', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('safe_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('row_count', sa.Integer(), nullable=True),
    sa.Column('file_name', sa.String(length=255), nullable=True),
    sa.Column('content_type', sa.String(length=128), nullable=True),
    sa.Column('file_size', sa.BigInteger(), nullable=True),
    sa.Column('file_sha256', sa.String(length=64), nullable=True),
    sa.Column('storage_key', sa.String(length=512), nullable=True),
    sa.Column('manifest', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('scope_reduced', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('viewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'employee_id', 'idempotency_key', name='uq_export_task_submission')
    )
    op.create_index('ix_export_task_owner', 'export_tasks', ['tenant_id', 'employee_id', 'created_at', 'id'], unique=False)
    op.create_index('ix_export_task_queue', 'export_tasks', ['status', 'created_at'], unique=False)
    op.create_index('uq_export_task_running_owner', 'export_tasks', ['tenant_id', 'employee_id'], unique=True, postgresql_where=sa.text("status = 'running'"))


def downgrade() -> None:
    op.drop_table("export_tasks")
