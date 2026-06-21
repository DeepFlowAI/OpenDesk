"""
EmployeeGroup and EmployeeGroupMember models
"""
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin


class EmployeeGroup(Base, TimestampMixin):
    __tablename__ = "employee_groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_employee_groups_tenant_name"),
        Index("ix_employee_groups_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    members: Mapped[list["EmployeeGroupMember"]] = relationship(
        "EmployeeGroupMember", back_populates="group", cascade="all, delete-orphan", lazy="selectin"
    )


class EmployeeGroupMember(Base):
    __tablename__ = "employee_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "employee_id", name="uq_group_members_group_employee"),
        Index("ix_group_members_group_id", "group_id"),
        Index("ix_group_members_employee_id", "employee_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("employee_groups.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    group: Mapped["EmployeeGroup"] = relationship("EmployeeGroup", back_populates="members")
    employee: Mapped["Employee"] = relationship("Employee", lazy="selectin")
