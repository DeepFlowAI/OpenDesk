"""
Call user association service.

Matches a call record's customer-side phone number to end users, creates a
user when there is no match, and stores the durable link on call_records.user_id.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.call_record import CallRecord
from app.models.user import User
from app.repositories.call_record_repository import CallRecordRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.user_service import UserService


ASSOCIATION_META_KEY = "user_association"


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
    async def identify_for_record_id(
        db: AsyncSession,
        tenant_id: int,
        record_id: int,
        *,
        actor_id: int | None = None,
    ) -> dict:
        row = await CallRecordRepository.get_by_id(db, record_id, tenant_id)
        if not row:
            raise NotFoundError("Call record not found")
        return await CallUserAssociationService.identify_for_record(
            db, tenant_id, row, actor_id=actor_id
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

        number = customer_number_for_call(row.direction, row.from_number, row.to_number)
        keys = phone_match_keys(number)
        if not keys:
            await CallUserAssociationService._set_association_metadata(
                db,
                row,
                status="unknown",
                number=number,
                normalized_number="",
                candidate_user_ids=[],
            )
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
            await CallUserAssociationService._set_association_metadata(
                db,
                row,
                status="multiple",
                number=number,
                normalized_number=sorted(keys)[0],
                candidate_user_ids=[user.id for user in matches],
            )
            return CallUserAssociationService.to_response(row, candidates=matches)

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
        return CallUserAssociationService.to_response(row, user=created_user)

    @staticmethod
    async def link_user(
        db: AsyncSession,
        tenant_id: int,
        record_id: int,
        user_id: int,
    ) -> dict:
        row = await CallRecordRepository.get_by_id(db, record_id, tenant_id)
        if not row:
            raise NotFoundError("Call record not found")
        user = await UserRepository.get_by_id(db, user_id)
        if not user or user.tenant_id != tenant_id:
            raise NotFoundError("User not found")
        number = customer_number_for_call(row.direction, row.from_number, row.to_number)
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
    async def candidate_users(db: AsyncSession, tenant_id: int, row: CallRecord) -> list[User]:
        meta = CallUserAssociationService._association_meta(row)
        candidate_ids = meta.get("candidate_user_ids") if isinstance(meta, dict) else []
        if not isinstance(candidate_ids, list):
            return []
        parsed_ids: list[int] = []
        for user_id in candidate_ids:
            try:
                parsed_ids.append(int(user_id))
            except (TypeError, ValueError):
                continue
        return await UserRepository.list_by_ids(
            db,
            tenant_id,
            parsed_ids,
        )

    @staticmethod
    def status_for_record(row: CallRecord) -> str:
        meta = CallUserAssociationService._association_meta(row)
        status = meta.get("status") if isinstance(meta, dict) else None
        if isinstance(status, str) and status:
            return status
        if row.user_id:
            return "linked"
        number = customer_number_for_call(row.direction, row.from_number, row.to_number)
        return "unlinked" if normalize_phone_digits(number) else "unknown"

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
    ) -> dict:
        meta = CallUserAssociationService._association_meta(row)
        number = meta.get("number") if isinstance(meta, dict) else None
        normalized_number = meta.get("normalized_number") if isinstance(meta, dict) else None
        if not isinstance(number, str):
            number = customer_number_for_call(row.direction, row.from_number, row.to_number)
        if not isinstance(normalized_number, str):
            normalized_number = normalize_phone_digits(number)
        return {
            "record_id": row.id,
            "call_id": row.call_id,
            "identified_number": number,
            "normalized_number": normalized_number,
            "status": CallUserAssociationService.status_for_record(row),
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
        users = await UserRepository.list_with_phone(db, tenant_id)
        return [
            user
            for user in users
            if phone_match_keys(user.phone) & target_keys
        ]

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
        await CallUserAssociationService._update_row_association(
            db,
            row,
            user_id=user_id,
            metadata={
                "status": status,
                "method": method,
                "number": number,
                "normalized_number": normalized_number,
                "candidate_user_ids": candidate_user_ids,
            },
        )

    @staticmethod
    async def _set_association_metadata(
        db: AsyncSession,
        row: CallRecord,
        *,
        status: str,
        number: str | None,
        normalized_number: str,
        candidate_user_ids: list[int],
    ) -> None:
        await CallUserAssociationService._update_row_association(
            db,
            row,
            user_id=None,
            metadata={
                "status": status,
                "number": number,
                "normalized_number": normalized_number,
                "candidate_user_ids": candidate_user_ids,
            },
        )

    @staticmethod
    async def _update_row_association(
        db: AsyncSession,
        row: CallRecord,
        *,
        user_id: int | None,
        metadata: dict[str, Any],
    ) -> None:
        extra = dict(row.extra_metadata or {})
        extra[ASSOCIATION_META_KEY] = metadata
        await CallRecordRepository.update(
            db,
            row,
            {"user_id": user_id, "extra_metadata": extra},
        )

    @staticmethod
    def _association_meta(row: CallRecord) -> dict[str, Any]:
        extra = row.extra_metadata or {}
        meta = extra.get(ASSOCIATION_META_KEY) if isinstance(extra, dict) else None
        return meta if isinstance(meta, dict) else {}
