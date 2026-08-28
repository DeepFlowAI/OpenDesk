"""
Scheduling rule set service: CRUD, copy, and tenant-default management.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.enums import ScheduleShiftType
from app.models.scheduling_rule import ScheduleRuleSet
from app.repositories.scheduling_repository import ScheduleShiftRepository
from app.repositories.scheduling_rule_repository import ScheduleRuleSetRepository
from app.schemas.scheduling_rule import RuleSetCreate, RuleSetUpdate


def _filter_shift_refs(data: dict, valid_shift_ids: set[int]) -> dict:
    """Drop targets / rotation template entries that reference unknown shifts."""
    targets = data.get("targets")
    if targets:
        data["targets"] = {
            key: days for key, days in targets.items() if int(key) in valid_shift_ids
        }
    templates = data.get("rotation_templates")
    if templates:
        cleaned = []
        for template in templates:
            days = [
                day for day in template["days"] if day["kind"] == "off" or day["shift_id"] in valid_shift_ids
            ]
            if len(days) >= 2:
                cleaned.append({**template, "days": days})
        data["rotation_templates"] = cleaned
    return data


class SchedulingRuleService:

    @staticmethod
    async def list_rule_sets(db: AsyncSession, tenant_id: int) -> list[ScheduleRuleSet]:
        return await ScheduleRuleSetRepository.list_by_tenant(db, tenant_id)

    @staticmethod
    async def get_rule_set(db: AsyncSession, tenant_id: int, rule_set_id: int) -> ScheduleRuleSet:
        rule_set = await ScheduleRuleSetRepository.get_by_id(db, tenant_id, rule_set_id)
        if rule_set is None:
            raise NotFoundError("Rule set not found")
        return rule_set

    @staticmethod
    async def _prepare_data(db: AsyncSession, tenant_id: int, data: dict) -> dict:
        shifts = await ScheduleShiftRepository.list_by_tenant(db, tenant_id)
        valid_shift_ids = {
            shift.id
            for shift in shifts
            if shift.is_enabled
            and (shift.shift_type or ScheduleShiftType.WORK.value)
            == ScheduleShiftType.WORK.value
        }
        return _filter_shift_refs(data, valid_shift_ids)

    @staticmethod
    async def create_rule_set(db: AsyncSession, tenant_id: int, data: RuleSetCreate) -> ScheduleRuleSet:
        existing = await ScheduleRuleSetRepository.get_by_name(db, tenant_id, data.name)
        if existing is not None:
            raise ValidationError("Rule set name already exists")
        payload = await SchedulingRuleService._prepare_data(db, tenant_id, data.model_dump())
        payload["tenant_id"] = tenant_id
        # The tenant's first rule set becomes the default automatically.
        if await ScheduleRuleSetRepository.count_by_tenant(db, tenant_id) == 0:
            payload["is_default"] = True
        if payload["is_default"]:
            await ScheduleRuleSetRepository.clear_default(db, tenant_id)
        return await ScheduleRuleSetRepository.create(db, payload)

    @staticmethod
    async def update_rule_set(
        db: AsyncSession, tenant_id: int, rule_set_id: int, data: RuleSetUpdate
    ) -> ScheduleRuleSet:
        rule_set = await SchedulingRuleService.get_rule_set(db, tenant_id, rule_set_id)
        existing = await ScheduleRuleSetRepository.get_by_name(
            db, tenant_id, data.name, exclude_id=rule_set_id
        )
        if existing is not None:
            raise ValidationError("Rule set name already exists")
        payload = await SchedulingRuleService._prepare_data(db, tenant_id, data.model_dump())
        return await ScheduleRuleSetRepository.update(db, rule_set, payload)

    @staticmethod
    async def delete_rule_set(db: AsyncSession, tenant_id: int, rule_set_id: int) -> None:
        rule_set = await SchedulingRuleService.get_rule_set(db, tenant_id, rule_set_id)
        if rule_set.is_default and await ScheduleRuleSetRepository.count_by_tenant(db, tenant_id) > 1:
            raise ValidationError("Set another rule set as default before deleting this one")
        await ScheduleRuleSetRepository.delete(db, rule_set)

    @staticmethod
    async def copy_rule_set(db: AsyncSession, tenant_id: int, rule_set_id: int) -> ScheduleRuleSet:
        rule_set = await SchedulingRuleService.get_rule_set(db, tenant_id, rule_set_id)
        base_name = f"{rule_set.name} 副本"
        name = base_name
        suffix = 2
        while await ScheduleRuleSetRepository.get_by_name(db, tenant_id, name) is not None:
            name = f"{base_name}{suffix}"
            suffix += 1
        payload = {
            "tenant_id": tenant_id,
            "name": name,
            "description": rule_set.description,
            "is_default": False,
            "default_group_ids": list(rule_set.default_group_ids),
            "targets_enabled": bool(getattr(rule_set, "targets_enabled", True)),
            "targets": dict(rule_set.targets),
            "constraints": dict(rule_set.constraints),
            "rotation_templates": list(rule_set.rotation_templates),
        }
        payload = await SchedulingRuleService._prepare_data(db, tenant_id, payload)
        return await ScheduleRuleSetRepository.create(db, payload)

    @staticmethod
    async def set_default(db: AsyncSession, tenant_id: int, rule_set_id: int) -> ScheduleRuleSet:
        rule_set = await SchedulingRuleService.get_rule_set(db, tenant_id, rule_set_id)
        await ScheduleRuleSetRepository.clear_default(db, tenant_id, exclude_id=rule_set_id)
        if not rule_set.is_default:
            rule_set = await ScheduleRuleSetRepository.update(db, rule_set, {"is_default": True})
        else:
            await db.commit()
        return rule_set
