"""add learning center tables

Revision ID: d1e2f3a4b5c6
Revises: b7c8d9e0f1a2
Create Date: 2026-08-07 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_courses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("cover_url", sa.String(length=500), nullable=True),
        sa.Column("intro", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("visibility", sa.String(length=16), server_default="assigned", nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_courses_tenant_status", "learning_courses", ["tenant_id", "status"], unique=False)
    op.create_index("ix_learning_courses_tenant_updated", "learning_courses", ["tenant_id", "updated_at"], unique=False)

    op.create_table(
        "learning_sections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["learning_courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_sections_course_sort", "learning_sections", ["course_id", "sort_order"], unique=False)
    op.create_index("ix_learning_sections_tenant", "learning_sections", ["tenant_id"], unique=False)

    op.create_table(
        "learning_materials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("file_key", sa.String(length=500), nullable=True),
        sa.Column("vod_video_id", sa.String(length=128), nullable=True),
        sa.Column("transcode_status", sa.String(length=16), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["learning_courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["learning_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_materials_section_sort", "learning_materials", ["section_id", "sort_order"], unique=False)
    op.create_index("ix_learning_materials_course", "learning_materials", ["course_id"], unique=False)
    op.create_index("ix_learning_materials_tenant", "learning_materials", ["tenant_id"], unique=False)
    op.create_index("ix_learning_materials_vod_video_id", "learning_materials", ["vod_video_id"], unique=False)

    op.create_table(
        "learning_course_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["learning_courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "target_type", "target_id", name="uq_learning_assignments_course_target"),
    )
    op.create_index("ix_learning_assignments_tenant", "learning_course_assignments", ["tenant_id"], unique=False)
    op.create_index("ix_learning_assignments_target", "learning_course_assignments", ["target_type", "target_id"], unique=False)

    op.create_table(
        "learning_material_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="in_progress", nullable=False),
        sa.Column("play_position_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_learn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["learning_courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["learning_materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id", "employee_id", name="uq_learning_records_material_employee"),
    )
    op.create_index("ix_learning_records_course_employee", "learning_material_records", ["course_id", "employee_id"], unique=False)
    op.create_index("ix_learning_records_tenant_employee", "learning_material_records", ["tenant_id", "employee_id"], unique=False)
    op.create_index("ix_learning_records_employee_learned", "learning_material_records", ["employee_id", "last_learn_at"], unique=False)


def downgrade() -> None:
    op.drop_table("learning_material_records")
    op.drop_table("learning_course_assignments")
    op.drop_table("learning_materials")
    op.drop_table("learning_sections")
    op.drop_table("learning_courses")
