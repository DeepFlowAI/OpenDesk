"""
Helpers for writing extensible creator/updater actor references.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.repositories.employee_repository import EmployeeRepository


class AuditActorService:
    @staticmethod
    def _employee_display_name(employee: Employee | None) -> str | None:
        if not employee:
            return None
        for attr in (employee.display_name, employee.nickname, employee.name):
            if attr and str(attr).strip():
                return str(attr).strip()
        return str(employee.username) if employee.username else None

    @staticmethod
    async def resolve_current_employee(
        db: AsyncSession,
        tenant_id: int,
        employee_id: int | None,
    ) -> dict:
        if employee_id is None:
            return {
                "actor_type": "system",
                "actor_id": None,
                "actor_name": "System",
            }

        employee = await EmployeeRepository.get_by_id(db, employee_id)
        display_name = None
        if employee and employee.tenant_id == tenant_id:
            display_name = AuditActorService._employee_display_name(employee)

        return {
            "actor_type": "employee",
            "actor_id": employee_id,
            "actor_name": display_name or f"Employee #{employee_id}",
        }

    @staticmethod
    def to_columns(prefix: str, actor: dict) -> dict:
        return {
            f"{prefix}_by_actor_type": actor["actor_type"],
            f"{prefix}_by_actor_id": actor["actor_id"],
            f"{prefix}_by_actor_name": actor["actor_name"],
        }
