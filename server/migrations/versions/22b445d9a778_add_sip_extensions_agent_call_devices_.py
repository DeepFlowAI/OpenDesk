"""add sip_extensions, agent_call_devices, call_record device attribution

Revision ID: 22b445d9a778
Revises: cc33dd44ee55
Create Date: 2026-07-13 20:02:47.550293

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '22b445d9a778'
down_revision: Union[str, None] = 'cc33dd44ee55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_call_devices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('device_type', sa.String(length=24), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'employee_id', name='uq_agent_call_device_tenant_employee'),
    )
    op.create_table(
        'sip_extensions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('extension_number', sa.String(length=10), nullable=False),
        sa.Column('sip_user_id', sa.String(length=80), nullable=False),
        sa.Column('auth_account', sa.String(length=80), nullable=False),
        sa.Column('auth_password_hash', sa.String(length=64), nullable=False),
        sa.Column('auth_password_masked', sa.String(length=40), nullable=False),
        sa.Column('registration_status', sa.String(length=16), server_default='unregistered', nullable=False),
        sa.Column('last_registered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('bound_employee_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by_actor_type', sa.String(length=32), nullable=True),
        sa.Column('created_by_actor_id', sa.Integer(), nullable=True),
        sa.Column('created_by_actor_name', sa.String(length=128), nullable=True),
        sa.Column('updated_by_actor_type', sa.String(length=32), nullable=True),
        sa.Column('updated_by_actor_id', sa.Integer(), nullable=True),
        sa.Column('updated_by_actor_name', sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(['bound_employee_id'], ['employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bound_employee_id', name='uq_sip_ext_bound_employee'),
        sa.UniqueConstraint('sip_user_id', name='uq_sip_ext_sip_user_id'),
        sa.UniqueConstraint('tenant_id', 'extension_number', name='uq_sip_ext_tenant_number'),
    )
    op.create_index('ix_sip_ext_tenant_active', 'sip_extensions', ['tenant_id', 'is_active'], unique=False)
    op.create_index('ix_sip_ext_tenant_id', 'sip_extensions', ['tenant_id'], unique=False)
    op.create_index('ix_sip_ext_tenant_reg_status', 'sip_extensions', ['tenant_id', 'registration_status'], unique=False)
    op.add_column('call_records', sa.Column('device_type', sa.String(length=24), nullable=True))
    op.add_column('call_records', sa.Column('device_identifier', sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column('call_records', 'device_identifier')
    op.drop_column('call_records', 'device_type')
    op.drop_index('ix_sip_ext_tenant_reg_status', table_name='sip_extensions')
    op.drop_index('ix_sip_ext_tenant_id', table_name='sip_extensions')
    op.drop_index('ix_sip_ext_tenant_active', table_name='sip_extensions')
    op.drop_table('sip_extensions')
    op.drop_table('agent_call_devices')
