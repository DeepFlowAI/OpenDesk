"""Ticket adapter for the shared export task lifecycle."""
import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Awaitable, Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.db.session import AsyncSessionLocal
from app.libs.export_types import ExportFile, FrozenExport
from app.libs.ticket_export_xlsx import MAX_BYTES, MAX_ROWS, TicketWorkbook, entity_id, values, fail
from app.core.exceptions import BusinessError
from app.repositories.ticket_repository import TicketRepository, SYSTEM_FIELD_MAP, _resolve_column, _build_condition_clause
from app.repositories.ticket_export_repository import TicketExportRepository as Repo
from app.schemas.fd_field_definition import UnifiedFieldResponse
from app.schemas.permission import EffectivePrincipal
from app.schemas.ticket_export import TicketExportPrepare, TicketExportSubmit
from app.services.data_scope_service import DataScopeService
from app.services.fd_field_definition_service import FdFieldDefinitionService
from app.services.export_task_service import ExportTaskService, export_error

ENTITY_TYPES = {"employee_select", "group_select", "user_select", "organization_select"}


def field_uid(field: dict) -> str:
    return f"id:{field['id']}" if field.get("id") is not None else f"key:{field['key']}"


def signature(prepared: str) -> str:
    content = prepared.encode()
    return hmac.new(settings.SECRET_KEY.encode(), b"ticket-export-v1:" + content, hashlib.sha256).hexdigest()


class TicketExportService:
    kind = "ticket"
    name = {"zh": "工单导出", "en": "Ticket export"}
    business_type = {"zh": "工单", "en": "Tickets"}
    permissions = ("ticket.workspace.view", "ticket.workspace.export")
    max_file_bytes = MAX_BYTES

    @staticmethod
    def authorize(principal: EffectivePrincipal) -> None:
        if not principal.has_all_permissions(list(TicketExportService.permissions)):
            raise export_error("permission_lost", 403)

    @staticmethod
    async def catalog(db: AsyncSession, tenant_id: int, language: str) -> list[dict]:
        result = await FdFieldDefinitionService.get_unified_list(
            db, tenant_id, "ticket", locale=language, include_metadata=True,
        )
        fields = [UnifiedFieldResponse.model_validate(item).model_dump(mode="json")
                  for item in result["items"] if item.get("status") == "active"]
        fields.sort(key=lambda field: (field["source"] == "custom", field["sort_order"], field_uid(field)))
        used: set[str] = set()
        for field in fields:
            name, suffix = field["name"], 2
            while field["name"] in used:
                field["name"] = f"{name}（{suffix}）"
                suffix += 1
            used.add(field["name"])
        return fields

    @staticmethod
    async def scope(db: AsyncSession, principal: EffectivePrincipal, frozen: dict | None = None) -> object:
        peers = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        predicates = [DataScopeService.build_ticket_predicate(principal, peers)]
        if frozen:
            old = EffectivePrincipal.model_validate(frozen["access"])
            if old.tenant_id != principal.tenant_id or old.user_id != principal.user_id:
                raise export_error("access_changed", 403)
            predicates.append(DataScopeService.build_ticket_predicate(old, frozen["peer_ids"]))
        predicates = [predicate for predicate in predicates if predicate is not None]
        return and_(*predicates) if predicates else None

    @staticmethod
    def validate_fields(frozen: list[dict], current: list[dict]) -> None:
        lookup = {field_uid(field): field for field in current}
        for field in frozen:
            candidate = lookup.get(field_uid(field))
            if not candidate or any(candidate[key] != field[key] for key in ("field_type", "slot_column", "source")):
                fail("configuration_invalid")

    @staticmethod
    def validate_query(query: dict, fields: list[dict]) -> list[dict]:
        lookup = {field_uid(field): field for field in fields}
        by_key = {field["key"]: field for field in fields if field.get("key")}
        dependencies = {}
        for group in ("view_conditions", "temp_conditions"):
            logic = query.get(group.replace("conditions", "condition_logic"), "and")
            if logic not in ("and", "or"):
                fail("configuration_invalid")
            for condition in query.get(group, []):
                field = lookup.get(f"id:{condition['field_id']}") if condition.get("field_id") else by_key.get(condition.get("field_key"))
                if not field:
                    fail("configuration_invalid")
                if field["id"] is not None:
                    condition["field_id"], condition["field_key"] = field["id"], None
                col = _resolve_column(condition.get("field_key"), field["slot_column"])
                if col is None or _build_condition_clause(col, condition["operator"], condition.get("value")) is None:
                    fail("configuration_invalid")
                dependencies[field_uid(field)] = field
        if query.get("group_field_col"):
            grouped = next((field for field in fields if field["slot_column"] == query["group_field_col"]), None)
            if not grouped:
                fail("configuration_invalid")
            dependencies[field_uid(grouped)] = grouped
        return list(dependencies.values())

    @staticmethod
    async def prepare(principal: EffectivePrincipal, body: TicketExportPrepare) -> dict:
        TicketExportService.authorize(principal)
        async with AsyncSessionLocal() as db:
            fields = await TicketExportService.catalog(db, principal.tenant_id, body.language)
            slots = {field["id"]: field["slot_column"] for field in fields if field["id"] is not None}
            req = body.query
            query = dict(search=req.search, temp_conditions=[item.model_dump() for item in req.temp_conditions],
                         temp_condition_logic=req.temp_condition_logic, view_conditions=[], view_condition_logic="and",
                         group_field_col=None, group_value=req.group_value, sort_by="updated_at", sort_order="desc")
            if req.sort_by not in (None, "updated_at") or req.sort_order != "desc":
                fail("configuration_invalid")
            title = {"zh": "全部工单", "en": "All tickets"}
            if req.view_id:
                view = await Repo.view(db, principal.tenant_id, req.view_id)
                if not view:
                    fail("configuration_invalid")
                query.update(view_conditions=view.conditions or [], view_condition_logic=view.condition_logic,
                             group_field_col=slots.get(view.group_field_id))
                title = {"zh": view.name, "en": view.name}
            if query["group_value"] is not None and not query["group_field_col"]:
                fail("configuration_invalid")
            dependencies = TicketExportService.validate_query(query, fields)
            # Keep one COUNT here: the UI shows an exact estimated export row count.
            _, count = await TicketRepository.query_paginated(db, principal.tenant_id, **query,
                slot_map=slots, per_page=1, ids_only=True,
                scope_predicate=await TicketExportService.scope(db, principal))
        prepared = json.dumps(dict(tenant_id=principal.tenant_id, employee_id=principal.user_id, query=query,
                        fields=fields, dependencies=dependencies, language=body.language, summary=title),
                        sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return dict(prepared=prepared, signature=signature(prepared), count=count)

    async def freeze(self, principal: EffectivePrincipal, config: dict) -> FrozenExport:
        self.authorize(principal)
        try:
            body = TicketExportSubmit.model_validate(config)
        except ValidationError:
            fail("configuration_invalid")
        if not hmac.compare_digest(signature(body.prepared), body.signature):
            fail("configuration_invalid")
        prepared = json.loads(body.prepared)
        if prepared["tenant_id"] != principal.tenant_id or prepared["employee_id"] != principal.user_id:
            raise export_error("access_changed", 403)
        if len(body.fields) != len(set(body.fields)) or body.fields[0] != "key:ticket_number":
            fail("configuration_invalid")
        lookup = {field_uid(field): field for field in prepared["fields"]}
        if any(uid not in lookup for uid in body.fields):
            fail("configuration_invalid")
        selected = [lookup[uid] for uid in body.fields]
        async with AsyncSessionLocal() as db:
            current = await self.catalog(db, principal.tenant_id, prepared["language"])
            self.validate_fields(selected + prepared["dependencies"], current)
            slots = {field["id"]: field["slot_column"] for field in current if field["id"] is not None}
            ids, _ = await TicketRepository.query_paginated(
                db, principal.tenant_id, **prepared["query"],
                slot_map=slots, per_page=MAX_ROWS + 1, ids_only=True, include_count=False,
                scope_predicate=await self.scope(db, principal),
            )
            if len(ids) > MAX_ROWS:
                fail("row_limit")
            peers = await DataScopeService.get_group_peer_employee_ids(db, principal.group_ids)
        frozen = dict(query=prepared["query"], fields=selected, dependencies=prepared["dependencies"],
                      access=principal.model_dump(mode="json"), peer_ids=peers, language=prepared["language"],
                      submitted_at=datetime.now(timezone.utc).isoformat(), suffix=uuid4().hex[:8])
        return FrozenExport(frozen, prepared["summary"], {"zh": "工单查询", "en": "Ticket query"})

    @staticmethod
    async def row_values(db: AsyncSession, tenant_id: int, rows: list, fields: list[dict], language: str) -> list[list]:
        raw = [[getattr(row, field["slot_column"] if field["id"] is not None else SYSTEM_FIELD_MAP[field["key"]], None)
                for field in fields] for row in rows]
        missing = "已失效" if language == "zh" else "Unavailable"
        for index, field in enumerate(fields):
            kind = field["field_type"]
            if kind in ENTITY_TYPES:
                ids = {entity_id(item) for row in raw for item in values(row[index])}
                names = await Repo.names(db, tenant_id, kind, ids - {None})
                for row in raw:
                    if row[index] is not None:
                        row[index] = "\n".join(names.get(entity_id(item)) or
                            (item.get("name") if isinstance(item, dict) else None) or missing for item in values(row[index]))
            elif field["key"] == "conversation_id" and field["id"] is None:
                conversations = await Repo.names(db, tenant_id, "conversation", {row.conversation_id for row in rows if row.conversation_id})
                calls = await Repo.names(db, tenant_id, "call", {row.call_record_id for row in rows if row.call_record_id})
                for row, ticket in zip(raw, rows, strict=True):
                    labels = []
                    if ticket.conversation_id:
                        labels.append(("会话 " if language == "zh" else "Session ") + (conversations.get(ticket.conversation_id) or missing))
                    if ticket.call_record_id:
                        labels.append(("通话 " if language == "zh" else "Call ") + (calls.get(ticket.call_record_id) or missing))
                    row[index] = "\n".join(labels) or None
        return raw

    async def generate(self, snapshot: dict, principal: EffectivePrincipal,
                       checkpoint: Callable[[], Awaitable[None]]) -> ExportFile:
        config = snapshot["config"]
        self.authorize(principal)
        async with AsyncSessionLocal() as db:
            current = await self.catalog(db, principal.tenant_id, config["language"])
            self.validate_fields(config["fields"] + config["dependencies"], current)
            slots = {field["id"]: field["slot_column"] for field in current if field["id"] is not None}
            ids, _ = await TicketRepository.query_paginated(
                db, principal.tenant_id, **config["query"],
                slot_map=slots, per_page=MAX_ROWS + 1, ids_only=True, include_count=False,
                scope_predicate=await self.scope(db, principal, config),
            )
            if len(ids) > MAX_ROWS:
                fail("row_limit")
        workbook = TicketWorkbook(config["fields"], snapshot["language"], snapshot["timezone"])
        try:
            output_ids = []
            for start in range(0, len(ids), 250):
                await checkpoint()
                principal = await ExportTaskService.current(principal)
                self.authorize(principal)
                async with AsyncSessionLocal() as db:
                    current = await self.catalog(db, principal.tenant_id, config["language"])
                    self.validate_fields(config["fields"], current)
                    rows = await Repo.rows(db, principal.tenant_id, ids[start:start + 250], await self.scope(db, principal, config))
                    rows.sort(key=lambda row: ids[start:start + 250].index(row.id))
                    data = await self.row_values(db, principal.tenant_id, rows, config["fields"], snapshot["language"])
                    batch_ids = [row.id for row in rows]
                for row in data:
                    workbook.append(row)
                output_ids.extend(batch_ids)
                await asyncio.sleep(0)
            await checkpoint()
            data = workbook.finish()
            stamp = datetime.fromisoformat(config["submitted_at"]).astimezone(ZoneInfo(snapshot["timezone"])).strftime("%Y%m%d_%H%M%S")
            prefix = "工单导出" if snapshot["language"] == "zh" else "Tickets"
            return ExportFile(data, f"{prefix}_{stamp}_{config['suffix']}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", len(output_ids),
                {"ticket_ids": output_ids}, scope_reduced=len(output_ids) < len(ids))
        finally:
            workbook.close()

    async def can_download(self, principal: EffectivePrincipal, snapshot: dict, manifest: dict) -> bool:
        if not principal.has_all_permissions(list(self.permissions)) or "ticket_ids" not in manifest:
            return False
        config = snapshot["config"]
        async with AsyncSessionLocal() as db:
            fields = await self.catalog(db, principal.tenant_id, config["language"])
            try:
                self.validate_fields(config["fields"], fields)
            except BusinessError:
                return False
            predicate = await self.scope(db, principal, config)
            ids = manifest["ticket_ids"]
            for start in range(0, len(ids), 500):
                batch = ids[start:start + 500]
                if set(await Repo.rows(db, principal.tenant_id, batch, predicate, ids_only=True)) != set(batch):
                    return False
        return True
