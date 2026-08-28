"""
Unit tests for bulk SMS target import: parse, mapping validation,
row-level validation, dedup and execution.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.libs.excel import build_xlsx
from app.models.sms_bulk_task import SmsBulkTask
from app.schemas.permission import EffectivePrincipal
from app.schemas.sms_bulk_task import SmsBulkImportMapping
from app.services.sms_bulk_import_service import SmsBulkImportService, _cache_key

MANAGE = "engagement.sms_task.manage"

VARIABLE_DEFS = [
    {"key": "name", "label": "客户姓名", "required": True, "max_length": 5},
    {"key": "time", "label": "预约时间", "required": False, "max_length": 20},
]

HEADERS = ["手机号", "姓名", "时间", "备注"]
ROWS = [
    ["13800138000", "王先生", "周一", "VIP"],
    ["13900139000", "李女士", "周二", ""],
]


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)


def principal(permissions: list[str] = [MANAGE], user_id: int = 10, tenant_id: int = 1) -> EffectivePrincipal:
    return EffectivePrincipal(user_id=user_id, tenant_id=tenant_id, permissions=permissions, is_super_admin=False)


def task(status: str = "draft", created_by_id: int = 10) -> SmsBulkTask:
    return SmsBulkTask(
        id=1,
        tenant_id=1,
        name="八月套餐到期提醒",
        status=status,
        template_id=10,
        template_name="预约回访提醒",
        template_type="notify",
        sign_name="深流客服",
        provider_sign_name="深流客服",
        body="尊敬的{name}，您预约的回访时间为{time}。",
        variables=VARIABLE_DEFS,
        provider="aliyun",
        provider_template_code="SMS_123456",
        send_type="immediate",
        created_by_id=created_by_id,
        updated_by_id=created_by_id,
    )


def _xlsx(rows: list[list[str]] = ROWS) -> bytes:
    return build_xlsx(HEADERS, rows)


def _patch_repos(existing_phones: set[str] | None = None):
    target_repo = patch("app.services.sms_bulk_import_service.SmsBulkTargetRepository").start()
    target_repo.list_phones_for_task = AsyncMock(return_value=existing_phones or set())
    target_repo.create_many = AsyncMock(side_effect=lambda db, rows: len(rows))
    return SimpleNamespace(target=target_repo)


def _patch_get_task(item: SmsBulkTask):
    return patch(
        "app.services.sms_bulk_import_service.SmsBulkTaskService._get_manageable_task",
        new=AsyncMock(return_value=item),
    ).start()


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _mapping(token: str, phone_column: str = "手机号", variable_columns: dict | None = None) -> SmsBulkImportMapping:
    return SmsBulkImportMapping(
        token=token,
        phone_column=phone_column,
        variable_columns=variable_columns if variable_columns is not None else {"name": "姓名"},
    )


async def _parse_into(redis: FakeRedis, content: bytes | None = None) -> str:
    result = await SmsBulkImportService.parse(
        AsyncMock(), redis, principal(), 1, "targets.xlsx", content if content is not None else _xlsx()
    )
    return result.token


class TestParse:
    @pytest.mark.asyncio
    async def test_parse_returns_token_headers_and_samples(self):
        _patch_get_task(task())
        redis = FakeRedis()

        result = await SmsBulkImportService.parse(AsyncMock(), redis, principal(), 1, "t.xlsx", _xlsx())

        assert result.headers == HEADERS
        assert result.sample_rows == ROWS
        cache = json.loads(redis.store[_cache_key(result.token)])
        assert cache["rows"] == ROWS
        assert cache["tenant_id"] == 1

    @pytest.mark.asyncio
    async def test_parse_rejects_non_mutable_status(self):
        _patch_get_task(task(status="sending"))

        with pytest.raises(ValidationError):
            await SmsBulkImportService.parse(AsyncMock(), FakeRedis(), principal(), 1, "t.xlsx", _xlsx())

    @pytest.mark.asyncio
    async def test_parse_rejects_empty_file(self):
        _patch_get_task(task())

        with pytest.raises(ValidationError):
            await SmsBulkImportService.parse(AsyncMock(), FakeRedis(), principal(), 1, "t.xlsx", build_xlsx([], []))


class TestValidateMapping:
    @pytest.mark.asyncio
    async def test_phone_column_must_exist(self):
        _patch_get_task(task())
        _patch_repos()
        redis = FakeRedis()
        token = await _parse_into(redis)

        with pytest.raises(ValidationError, match="接收号码"):
            await SmsBulkImportService.validate(
                AsyncMock(), redis, principal(), 1, _mapping(token, phone_column="不存在列")
            )

    @pytest.mark.asyncio
    async def test_required_variable_must_be_mapped(self):
        _patch_get_task(task())
        _patch_repos()
        redis = FakeRedis()
        token = await _parse_into(redis)

        with pytest.raises(ValidationError, match="客户姓名"):
            await SmsBulkImportService.validate(
                AsyncMock(), redis, principal(), 1, _mapping(token, variable_columns={})
            )

    @pytest.mark.asyncio
    async def test_expired_token_raises_not_found(self):
        _patch_get_task(task())
        _patch_repos()

        with pytest.raises(NotFoundError):
            await SmsBulkImportService.validate(AsyncMock(), FakeRedis(), principal(), 1, _mapping("missing"))

    @pytest.mark.asyncio
    async def test_cross_tenant_cache_rejected(self):
        _patch_get_task(task())
        _patch_repos()
        redis = FakeRedis()
        token = await _parse_into(redis)
        cache = json.loads(redis.store[_cache_key(token)])
        cache["tenant_id"] = 999
        redis.store[_cache_key(token)] = json.dumps(cache)

        with pytest.raises(ValidationError):
            await SmsBulkImportService.validate(AsyncMock(), redis, principal(), 1, _mapping(token))


class TestValidateRows:
    @pytest.mark.asyncio
    async def test_valid_rows_pass(self):
        _patch_get_task(task())
        _patch_repos()
        redis = FakeRedis()
        token = await _parse_into(redis)

        result = await SmsBulkImportService.validate(AsyncMock(), redis, principal(), 1, _mapping(token))

        assert result.total == 2
        assert result.valid == 2
        assert result.duplicate == 0
        assert result.invalid == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_row_level_errors(self):
        rows = [
            ["", "王先生", "周一", ""],           # empty phone
            ["12345", "李女士", "周二", ""],       # invalid format
            ["13800138000", "", "周一", ""],       # missing required variable
            ["13900139000", "超过五个字的名字", "周二", ""],  # exceeds max_length 5
        ]
        _patch_get_task(task())
        _patch_repos()
        redis = FakeRedis()
        token = await _parse_into(redis, _xlsx(rows))

        result = await SmsBulkImportService.validate(AsyncMock(), redis, principal(), 1, _mapping(token))

        assert result.valid == 0
        assert result.invalid == 4
        assert len(result.errors) == 4
        assert result.errors[0].row_number == 2
        assert "required" in result.errors[0].reason
        assert "Invalid phone" in result.errors[1].reason
        assert "name" in result.errors[2].reason
        assert "max length" in result.errors[3].reason

    @pytest.mark.asyncio
    async def test_duplicates_skipped_and_counted(self):
        rows = [
            ["13800138000", "王先生", "周一", ""],
            ["13800138000", "重复", "周二", ""],   # duplicate within file
            ["13700137000", "已有", "周三", ""],   # duplicate with existing task target
            ["13900139000", "李女士", "周四", ""],
        ]
        _patch_get_task(task())
        _patch_repos(existing_phones={"13700137000"})
        redis = FakeRedis()
        token = await _parse_into(redis, _xlsx(rows))

        result = await SmsBulkImportService.validate(AsyncMock(), redis, principal(), 1, _mapping(token))

        assert result.total == 4
        assert result.valid == 2
        assert result.duplicate == 2
        assert result.invalid == 0

    @pytest.mark.asyncio
    async def test_optional_variable_can_be_unmapped(self):
        _patch_get_task(task())
        _patch_repos()
        redis = FakeRedis()
        token = await _parse_into(redis)

        result = await SmsBulkImportService.validate(AsyncMock(), redis, principal(), 1, _mapping(token))

        assert result.valid == 2


class TestExecute:
    @pytest.mark.asyncio
    async def test_execute_inserts_valid_rows_and_clears_cache(self):
        _patch_get_task(task())
        repos = _patch_repos()
        redis = FakeRedis()
        token = await _parse_into(redis)

        result = await SmsBulkImportService.execute(AsyncMock(), redis, principal(), 1, _mapping(token))

        assert result.success == 2
        assert result.duplicate == 0
        assert result.failed == 0
        payloads = repos.target.create_many.call_args.args[1]
        assert payloads[0] == {
            "tenant_id": 1,
            "task_id": 1,
            "phone": "13800138000",
            "variable_values": {"name": "王先生"},
        }
        assert _cache_key(token) not in redis.store

    @pytest.mark.asyncio
    async def test_execute_reports_duplicates_and_failures(self):
        rows = [
            ["13800138000", "王先生", "周一", ""],
            ["13800138000", "重复", "周二", ""],
            ["bad", "李女士", "周三", ""],
        ]
        _patch_get_task(task())
        _patch_repos()
        redis = FakeRedis()
        token = await _parse_into(redis, _xlsx(rows))

        result = await SmsBulkImportService.execute(AsyncMock(), redis, principal(), 1, _mapping(token))

        assert result.success == 1
        assert result.duplicate == 1
        assert result.failed == 1

    @pytest.mark.asyncio
    async def test_execute_rejects_non_mutable_status(self):
        _patch_get_task(task(status="sending"))
        _patch_repos()

        with pytest.raises(ValidationError):
            await SmsBulkImportService.execute(AsyncMock(), FakeRedis(), principal(), 1, _mapping("any"))


class TestCreateMany:
    @pytest.mark.asyncio
    async def test_inserts_in_chunks_without_orm_instances(self):
        from app.repositories.sms_bulk_task_repository import SmsBulkTargetRepository

        rows = [
            {"tenant_id": 1, "task_id": 1, "phone": f"1380013{i:04d}", "variable_values": {}}
            for i in range(2500)
        ]
        db = AsyncMock()

        inserted = await SmsBulkTargetRepository.create_many(db, rows)

        assert inserted == 2500
        db.add_all.assert_not_called()
        chunk_sizes = [len(call.args[1]) for call in db.execute.await_args_list]
        assert chunk_sizes == [1000, 1000, 500]
        db.commit.assert_awaited_once()
