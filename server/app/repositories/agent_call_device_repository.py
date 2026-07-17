"""
Agent call-device repository — persisted current-device selection per agent.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_call_device import AgentCallDevice


class AgentCallDeviceRepository:
    @staticmethod
    async def get_for_employee(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> AgentCallDevice | None:
        result = await db.execute(
            select(AgentCallDevice).where(
                AgentCallDevice.tenant_id == tenant_id,
                AgentCallDevice.employee_id == employee_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert(
        db: AsyncSession, tenant_id: int, employee_id: int, device_type: str
    ) -> AgentCallDevice:
        row = await AgentCallDeviceRepository.get_for_employee(
            db, tenant_id, employee_id
        )
        if row is None:
            row = AgentCallDevice(
                tenant_id=tenant_id,
                employee_id=employee_id,
                device_type=device_type,
            )
            db.add(row)
        else:
            row.device_type = device_type
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def clear_for_employee(
        db: AsyncSession, tenant_id: int, employee_id: int
    ) -> None:
        row = await AgentCallDeviceRepository.get_for_employee(
            db, tenant_id, employee_id
        )
        if row is not None:
            await db.delete(row)
            await db.commit()
