"""
Call user association service.

Matches a call record's customer-side phone number to end users, creates a
user when there is no match, and stores the durable link on call_records.user_id.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.call_record import CallRecord
from app.models.user import User
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.user_repository import UserRepository
from app.schemas.call_trajectory import CallEventCreate
from app.schemas.permission import EffectivePrincipal
from app.schemas.user import UserCreate
from app.services.data_scope_service import DataScopeService
from app.services.call_trajectory_service import CallTrajectoryService
from app.services.user_service import UserService


def normalize_phone_digits(value: str | None) -> str:
    if not value:
        return ""
    digits = re.sub(r"\D+", "", value)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def phone_match_keys(value: str | None) -> set[str]:
    digits = normalize_phone_digits(value)
    if not digits:
        return set()
    keys = {digits}
    if digits.startswith("86") and len(digits) == 13:
        keys.add(digits[2:])
    if digits.startswith("1") and len(digits) == 11:
        keys.add(digits[1:])
    return keys


def customer_number_for_call(
    direction: str | None,
    from_number: str | None,
    to_number: str | None,
) -> str | None:
    if direction == "outbound":
        return to_number
    return from_number


class CallUserAssociationService:
    @staticmethod
    async def identify_for_public_id(
        db: AsyncSession,
        public_id: UUID,
        principal: EffectivePrincipal,
        *,
        actor_id: int | None = None,
    ) -> dict:
        row = await CallRecordRepository.get_by_public_id(
            db,
            public_id,
            principal.tenant_id,
        )
        if not row:
            raise NotFoundError("Call record not found")
        await DataScopeService.assert_call_record_in_scope(db, principal, row)
        return await CallUserAssociationService.identify_for_record(
            db, principal.tenant_id, row, actor_id=actor_id
        )

    @staticmethod
    async def identify_for_record(
        db: AsyncSession,
        tenant_id: int,
        row: CallRecord,
        *,
        actor_id: int | None = None,
    ) -> dict:
        if row.user_id:
            user = await UserRepository.get_by_id(db, row.user_id)
            if user and user.tenant_id == tenant_id:
                return CallUserAssociationService.to_response(row, user=user)

        number = row.customer_number
        keys = phone_match_keys(number)
        if not keys:
            return CallUserAssociationService.to_response(row)

        matches = await CallUserAssociationService._find_matching_users(db, tenant_id, keys)
        if len(matches) == 1:
            user = matches[0]
            await CallUserAssociationService._link_user(
                db,
                row,
                user.id,
                status="linked",
                method="auto",
                number=number,
                normalized_number=sorted(keys)[0],
                candidate_user_ids=[],
            )
            return CallUserAssociationService.to_response(row, user=user)

        if len(matches) > 1:
            return CallUserAssociationService.to_response(
                row,
                candidates=matches,
                status="multiple",
            )

        created_user = await CallUserAssociationService._create_user_from_number(
            db, tenant_id, number or sorted(keys)[0], actor_id
        )
        await CallUserAssociationService._link_user(
            db,
            row,
            created_user.id,
            status="created",
            method="auto_create",
            number=number,
            normalized_number=sorted(keys)[0],
            candidate_user_ids=[],
        )
        return CallUserAssociationService.to_response(
            row,
            user=created_user,
            status="created",
        )

    @staticmethod
    async def link_user(
        db: AsyncSession,
        public_id: UUID,
        principal: EffectivePrincipal,
        user_id: int,
    ) -> dict:
        row = await CallRecordRepository.get_by_public_id(
            db,
            public_id,
            principal.tenant_id,
        )
        if not row:
            raise NotFoundError("Call record not found")
        await DataScopeService.assert_call_record_in_scope(db, principal, row)
        user = await UserRepository.get_by_id(db, user_id)
        if not user or user.tenant_id != principal.tenant_id:
            raise NotFoundError("User not found")
        number = row.customer_number
        await CallUserAssociationService._link_user(
            db,
            row,
            user.id,
            status="linked",
            method="manual",
            number=number,
            normalized_number=normalize_phone_digits(number),
            candidate_user_ids=[],
        )
        return CallUserAssociationService.to_response(row, user=user)

    @staticmethod
    async def unlink_user(
        db: AsyncSession,
        public_id: UUID,
        principal: EffectivePrincipal,
    ) -> dict:
        row = await CallRecordRepository.get_by_public_id(
            db,
            public_id,
            principal.tenant_id,
        )
        if not row:
            raise NotFoundError("Call record not found")
        await DataScopeService.assert_call_record_in_scope(db, principal, row)
        event_id = f"opendesk:user-disassociated:{row.id}:{uuid4().hex}"
        await CallTrajectoryService.append_event(
            db,
            call_record_id=row.id,
            payload=CallEventCreate(
                event_id=event_id,
                event_type="user_disassociated",
                event_category="lifecycle",
                actor_type="agent",
                actor_id=str(principal.user_id),
                source="opendesk",
                source_event_id=event_id,
                occurred_at=datetime.now(timezone.utc),
                details={"method": "manual"},
            ),
        )
        row.user_id = None
        return CallUserAssociationService.to_response(row)

    @staticmethod
    async def candidate_users(db: AsyncSession, tenant_id: int, row: CallRecord) -> list[User]:
        if row.user_id is not None:
            return []
        keys = phone_match_keys(row.customer_number)
        if not keys:
            return []
        matches = await CallUserAssociationService._find_matching_users(
            db, tenant_id, keys
        )
        return matches if len(matches) > 1 else []

    @staticmethod
    def status_for_record(row: CallRecord) -> str:
        if row.user_id:
            return "linked"
        return "unlinked" if normalize_phone_digits(row.customer_number) else "unknown"

    @staticmethod
    def brief_user(user: User | None) -> dict | None:
        if not user:
            return None
        return {
            "id": user.id,
            "public_id": user.public_id,
            "name": user.name,
            "phone": user.phone,
            "email": user.email,
        }

    @staticmethod
    def to_response(
        row: CallRecord,
        *,
        user: User | None = None,
        candidates: list[User] | None = None,
        status: str | None = None,
    ) -> dict:
        number = row.customer_number
        return {
            "record_public_id": row.public_id,
            "call_id": row.call_id,
            "identified_number": number,
            "normalized_number": normalize_phone_digits(number),
            "status": status or CallUserAssociationService.status_for_record(row),
            "user": CallUserAssociationService.brief_user(user),
            "candidates": [
                brief
                for candidate in (candidates or [])
                if (brief := CallUserAssociationService.brief_user(candidate)) is not None
            ],
        }

    @staticmethod
    async def _find_matching_users(
        db: AsyncSession,
        tenant_id: int,
        target_keys: set[str],
    ) -> list[User]:
        return await UserRepository.list_by_phone_match_keys(db, tenant_id, target_keys)

    @staticmethod
    async def _create_user_from_number(
        db: AsyncSession,
        tenant_id: int,
        number: str,
        actor_id: int | None,
    ) -> User:
        phone = (number or "").strip()[:32]
        name = phone[:64] or "未知号码"
        created = await UserService.create_user(
            db,
            tenant_id,
            UserCreate(name=name, phone=phone),
            actor_id=actor_id,
        )
        user = await UserRepository.get_by_id(db, int(created["id"]))
        if not user:
            raise NotFoundError("User not found")
        return user

    @staticmethod
    async def _link_user(
        db: AsyncSession,
        row: CallRecord,
        user_id: int,
        *,
        status: str,
        method: str,
        number: str | None,
        normalized_number: str,
        candidate_user_ids: list[int],
    ) -> None:
        del status, number, normalized_number, candidate_user_ids
        event_id = f"opendesk:user-associated:{row.id}:{uuid4().hex}"
        await CallRecordRepository.update(
            db, row, {"user_id": user_id}, commit=False
        )
        await CallTrajectoryService.append_event(
            db,
            call_record_id=row.id,
            payload=CallEventCreate(
                event_id=event_id,
                event_type="user_associated",
                event_category="lifecycle",
                actor_type="system" if method.startswith("auto") else "agent",
                target_type="user",
                target_id=str(user_id),
                source="opendesk",
                source_event_id=event_id,
                occurred_at=datetime.now(timezone.utc),
                details={"method": method},
            ),
            commit=False,
        )
        await db.commit()
