"""Export contracts and managed session regression tests."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import BusinessError
from app.libs import export_types
from app.libs.export_types import ExportFile, FrozenExport
from app.schemas.export_task import ExportTaskCreate
from app.schemas.permission import EffectivePrincipal
from app.services import export_task_service as module
from app.services.export_task_service import ExportTaskService as Service

NOW = datetime.now(timezone.utc)
PRINCIPAL = EffectivePrincipal(user_id=7, tenant_id=3, permissions=["test.export"])


class SampleExport:
    kind = "test"
    name = {"zh": "测试导出", "en": "Test export"}
    business_type = {"zh": "测试", "en": "Test"}
    permissions = ("test.export",)
    max_file_bytes = 1024

    async def freeze(self, principal, config):
        return FrozenExport(config, {"zh": "客户甲"}, {"zh": "1 个条件"})

    async def generate(self, snapshot, principal, checkpoint):
        await checkpoint()
        return ExportFile(b"id\n1\n", "test.csv", "text/csv", 1, {"ids": [1]})

    async def can_download(self, principal, snapshot, manifest):
        return True


def task(**values):
    defaults = dict(id=uuid4(), employee_id=7, tenant_id=3, kind="test", name=SampleExport.name,
        business_type=SampleExport.business_type, summary={"zh": "客户甲"}, safe_summary={"zh": "1 个条件"},
        status="completed", expires_at=NOW + timedelta(days=7), created_at=NOW,
        completed_at=NOW, started_at=NOW, error_code=None, row_count=1, file_name="test.csv",
        file_size=5, content_type="text/csv", file_sha256=None, storage_key="exports/3/7/test", manifest={"ids": [1]},
        snapshot={"principal": PRINCIPAL.model_dump(), "config": {}}, scope_reduced=False, viewed_at=None,
        request_hash="abc")
    defaults.update(values)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    monkeypatch.setattr(export_types, "_export_types", {"test": SampleExport()})


@pytest.fixture
def sessions(monkeypatch):
    state = SimpleNamespace(active=0, commit=AsyncMock(), flush=AsyncMock())

    @asynccontextmanager
    async def session():
        state.active += 1
        try:
            yield state
        finally:
            state.active -= 1

    monkeypatch.setattr(module, "AsyncSessionLocal", session)
    return state, session


def test_expiry_boundary_and_redaction():
    expired = Service.response(task(expires_at=NOW), PRINCIPAL, NOW)
    assert expired.status == "expired"
    assert not expired.can_download
    denied = Service.response(task(), PRINCIPAL.model_copy(update={"permissions": []}), NOW)
    assert denied.summary == {"zh": "1 个条件"}
    assert denied.error_code == "access_changed"
    assert not denied.can_download
    assert "storage_key" not in denied.model_dump()
    assert "snapshot" not in denied.model_dump()


def test_idempotency_and_retention():
    original = task()
    assert Service.existing_submission(original, "abc", PRINCIPAL, NOW).id == original.id
    with pytest.raises(BusinessError) as error:
        Service.existing_submission(original, "different", PRINCIPAL, NOW)
    assert error.value.status_code == 409
    with pytest.raises(BusinessError) as error:
        Service.existing_submission(task(created_at=NOW-timedelta(days=90)), "abc", PRINCIPAL, NOW)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_limit_and_freeze_without_session(monkeypatch, sessions):
    state, _ = sessions
    monkeypatch.setattr(Service, "current", AsyncMock(return_value=PRINCIPAL))
    monkeypatch.setattr(module.PermissionService, "get_current_principal", AsyncMock(return_value=PRINCIPAL))
    monkeypatch.setattr(module.Repo, "by_key", AsyncMock(return_value=None))
    monkeypatch.setattr(module.Repo, "lock_owner", AsyncMock(return_value=True))
    monkeypatch.setattr(module.Repo, "pending_count", AsyncMock(return_value=5))
    async def freeze(principal, config):
        assert state.active == 0
        return FrozenExport(config, {}, {})
    monkeypatch.setattr(export_types._export_types["test"], "freeze", freeze)
    with pytest.raises(BusinessError) as error:
        await Service.create(PRINCIPAL, ExportTaskCreate(idempotency_key=uuid4(), kind="test"))
    assert error.value.code == "EXPORT_PENDING_LIMIT"


@pytest.mark.asyncio
async def test_cancel_ownership_and_completion_race(monkeypatch, sessions):
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(module.Repo, "get_owned", lookup)
    task_id = uuid4()
    with pytest.raises(BusinessError) as error:
        await Service.cancel(PRINCIPAL, task_id)
    assert error.value.status_code == 404
    assert lookup.call_args.args[1:4] == (3, 7, task_id)
    lookup.return_value = task()
    monkeypatch.setattr(module.Repo, "transition", AsyncMock(return_value=False))
    with pytest.raises(BusinessError) as error:
        await Service.cancel(PRINCIPAL, task_id)
    assert error.value.code == "EXPORT_ALREADY_COMPLETED"


@pytest.mark.asyncio
async def test_empty_registry_does_not_grant_entry(monkeypatch, sessions):
    monkeypatch.setattr(export_types, "_export_types", {})
    monkeypatch.setattr(module.Repo, "counts", AsyncMock(return_value=(0, 0)))
    assert not (await Service.status(PRINCIPAL))["visible"]
    monkeypatch.setattr(module.Repo, "counts", AsyncMock(return_value=(1, 0)))
    assert (await Service.status(PRINCIPAL))["visible"]

@pytest.mark.asyncio
async def test_generate_upload_has_no_session_and_cancel_cannot_resurrect(monkeypatch, sessions):
    from app.services import export_task_worker as worker
    state, session = sessions
    monkeypatch.setattr(worker, "AsyncSessionLocal", session)
    original = task(status="running")
    monkeypatch.setattr(worker.Repo, "get", AsyncMock(return_value=original))
    monkeypatch.setattr(Service, "current", AsyncMock(return_value=PRINCIPAL))
    async def generate(snapshot, principal, checkpoint):
        assert state.active == 0
        assert snapshot["principal"]["user_id"] == 7
        await checkpoint()
        return ExportFile(b"id\n1\n", "test.csv", "text/csv", 1, {"ids": [1]})
    monkeypatch.setattr(export_types._export_types["test"], "generate", generate)
    async def upload(*args):
        assert state.active == 0
        original.status = "cancelled"
    storage = SimpleNamespace(upload_private=upload)
    monkeypatch.setattr(worker, "create_storage_client", lambda: storage)
    async def transition(db, task_id, states, values):
        assert states == ("running",)
        if original.status in states:
            original.status = values["status"]
            return True
        return False
    monkeypatch.setattr(worker.Repo, "transition", transition)
    with pytest.raises(worker.ExportStopped):
        await worker.ExportTaskWorker.generate(original.id)
    assert original.status == "cancelled"
    assert state.active == 0


@pytest.mark.asyncio
async def test_download_signs_without_reading_file_or_holding_session(monkeypatch, sessions):
    from app.services import export_task_worker as worker
    state, session = sessions
    monkeypatch.setattr(worker, "AsyncSessionLocal", session)
    original = task()
    monkeypatch.setattr(worker.Repo, "get_owned", AsyncMock(return_value=original))
    monkeypatch.setattr(Service, "current", AsyncMock(return_value=PRINCIPAL))
    validate = AsyncMock()
    monkeypatch.setattr(worker.EmployeeSessionService, "validate_payload", validate)
    monkeypatch.setattr(worker.Repo, "transition", AsyncMock(return_value=True))
    auth = AsyncMock(return_value=True)
    monkeypatch.setattr(export_types._export_types["test"], "can_download", auth)
    async def sign(*args, **kwargs):
        assert state.active == 0
        return "https://storage.example/export?signature=test"
    storage = SimpleNamespace(get_temporary_url=AsyncMock(side_effect=sign), read_private=AsyncMock())
    monkeypatch.setattr(worker, "create_storage_client", lambda: storage)
    assert await worker.ExportTaskWorker.download(PRINCIPAL, original.id, {}) == "https://storage.example/export?signature=test"
    storage.get_temporary_url.assert_awaited_once_with(
        original.storage_key, expires_seconds=120, download_name=original.file_name,
    )
    storage.read_private.assert_not_awaited()
    auth.assert_awaited_once()
    validate.assert_awaited_once()

    storage.get_temporary_url.reset_mock()
    original.expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    await worker.ExportTaskWorker.download(PRINCIPAL, original.id, {})
    assert 0 < storage.get_temporary_url.call_args.kwargs["expires_seconds"] <= 30

    storage.get_temporary_url.reset_mock()
    auth.return_value = False
    with pytest.raises(BusinessError) as error:
        await worker.ExportTaskWorker.download(PRINCIPAL, original.id, {})
    assert error.value.code == "EXPORT_ACCESS_CHANGED"
    storage.get_temporary_url.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["expired", "session", "storage"])
async def test_download_does_not_issue_link_on_validation_or_signing_failure(monkeypatch, sessions, reason):
    from app.services import export_task_worker as worker
    _, session = sessions
    monkeypatch.setattr(worker, "AsyncSessionLocal", session)
    original = task()
    monkeypatch.setattr(worker.ExportTaskWorker, "authorized_file", AsyncMock(return_value=original))
    async def validate(*args):
        if reason == "expired":
            original.expires_at = datetime.now(timezone.utc)
        elif reason == "session":
            raise BusinessError("Session revoked", status_code=401)
    monkeypatch.setattr(worker.EmployeeSessionService, "validate_payload", validate)
    storage = SimpleNamespace(get_temporary_url=AsyncMock(side_effect=RuntimeError("Unavailable")))
    monkeypatch.setattr(worker, "create_storage_client", lambda: storage)
    with pytest.raises(BusinessError) as error:
        await worker.ExportTaskWorker.download(PRINCIPAL, original.id, {})
    if reason == "storage":
        assert error.value.code == "EXPORT_DOWNLOAD_FAILED"
    else:
        storage.get_temporary_url.assert_not_awaited()
        if reason == "expired":
            assert error.value.code == "EXPORT_EXPIRED"


@pytest.mark.asyncio
async def test_expired_file_never_reads_storage(monkeypatch, sessions):
    from app.services import export_task_worker as worker
    _, session = sessions
    monkeypatch.setattr(worker, "AsyncSessionLocal", session)
    monkeypatch.setattr(worker.Repo, "get_owned", AsyncMock(return_value=task(expires_at=NOW)))
    monkeypatch.setattr(Service, "current", AsyncMock(return_value=PRINCIPAL))
    with pytest.raises(BusinessError) as error:
        await worker.ExportTaskWorker.download(PRINCIPAL, uuid4(), {})
    assert error.value.code == "EXPORT_EXPIRED"


@pytest.mark.asyncio
async def test_signed_download_encodes_unicode_filename(monkeypatch):
    from unittest.mock import Mock
    from urllib.parse import quote
    from app.libs.storage.providers import aliyun_oss

    bucket = SimpleNamespace(sign_url=Mock(return_value="https://storage.example/signed"))
    monkeypatch.setattr(aliyun_oss, "_get_bucket", lambda: bucket)
    filename = '工单导出 "客户".xlsx'
    url = await aliyun_oss.AliyunOSSClient().get_temporary_url(
        "exports/test", expires_seconds=120, download_name=filename,
    )
    assert url == "https://storage.example/signed"
    bucket.sign_url.assert_called_once_with("GET", "exports/test", 120, params={
        "response-content-disposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
    })


@pytest.mark.asyncio
async def test_generation_permission_loss_fails_without_file(monkeypatch, sessions):
    from app.services import export_task_worker as worker
    _, session = sessions
    monkeypatch.setattr(worker, "AsyncSessionLocal", session)
    original = task(status="running")
    monkeypatch.setattr(worker.Repo, "get", AsyncMock(return_value=original))
    monkeypatch.setattr(Service, "current", AsyncMock(return_value=PRINCIPAL.model_copy(update={"permissions": []})))
    fail = AsyncMock()
    monkeypatch.setattr(worker.ExportTaskWorker, "fail", fail)
    await worker.ExportTaskWorker.execute(original.id)
    fail.assert_awaited_once_with(original.id, "permission_lost")

@pytest.mark.asyncio
async def test_http_pagination_validation_and_private_headers(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.db.deps import get_current_principal_short_session, get_current_user
    from app.routers.v1.exports import router
    from app.services.export_task_worker import ExportTaskWorker
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_principal_short_session] = lambda: PRINCIPAL
    app.dependency_overrides[get_current_user] = lambda: {"user_id": 7, "tenant_id": 3}
    list_tasks = AsyncMock(return_value=dict(items=[], total=0, page=1, per_page=50, pages=1))
    monkeypatch.setattr(Service, "list_tasks", list_tasks)
    monkeypatch.setattr(ExportTaskWorker, "download", AsyncMock(return_value="https://storage.example/export?signature=test"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get('/exports?per_page=50')
        assert response.status_code == 200, response.text
        assert list_tasks.call_args.args[2] == 50
        assert (await client.get('/exports?per_page=10')).status_code == 422
        response = await client.get(f'/exports/{uuid4()}/download')
        assert response.json() == {"url": "https://storage.example/export?signature=test"}
        assert response.headers['cache-control'] == 'no-store, private'
        assert response.headers["x-content-type-options"] == "nosniff"

@pytest.mark.asyncio
@pytest.mark.parametrize('row_count', [0, 1])
async def test_sample_type_full_lifecycle(monkeypatch, sessions, row_count):
    from app.services import export_task_worker as worker
    state, session = sessions
    monkeypatch.setattr(worker, "AsyncSessionLocal", session)
    monkeypatch.setattr(Service, "current", AsyncMock(return_value=PRINCIPAL))
    monkeypatch.setattr(module.PermissionService, "get_current_principal", AsyncMock(return_value=PRINCIPAL))
    monkeypatch.setattr(module.Repo, "lock_owner", AsyncMock(return_value=True))
    monkeypatch.setattr(module.Repo, "pending_count", AsyncMock(return_value=0))
    current = None
    async def by_key(*args):
        return current
    async def add(db, values):
        nonlocal current
        current = task(**values)
        return current
    async def get(*args):
        return current
    async def transition(db, task_id, states, values):
        if current.status not in states:
            return False
        for key, value in values.items():
            setattr(current, key, value)
        return True
    monkeypatch.setattr(module.Repo, "by_key", by_key)
    monkeypatch.setattr(module.Repo, "add", add)
    monkeypatch.setattr(module.Repo, "get", get)
    monkeypatch.setattr(module.Repo, "get_owned", get)
    monkeypatch.setattr(module.Repo, "transition", transition)
    objects = {}
    async def upload(key, data, content_type):
        assert state.active == 0
        objects[key] = data
    async def sign(key, expires_seconds, download_name):
        assert state.active == 0
        assert key in objects
        assert expires_seconds == 120
        assert download_name == 'sample.csv'
        return 'https://storage.example/export?signature=test'
    monkeypatch.setattr(worker, "create_storage_client", lambda: SimpleNamespace(upload_private=upload, get_temporary_url=sign))
    monkeypatch.setattr(worker.EmployeeSessionService, "validate_payload", AsyncMock())
    async def generate(snapshot, principal, checkpoint):
        assert state.active == 0
        assert snapshot['language'] == 'en'
        assert snapshot['timezone'] == 'Asia/Shanghai'
        await checkpoint()
        return ExportFile(b'id\n' if row_count == 0 else b'id\n1\n', 'sample.csv', 'text/csv', row_count, {'ids': [] if row_count == 0 else [1]})
    monkeypatch.setattr(export_types._export_types['test'], 'generate', generate)
    body = ExportTaskCreate(idempotency_key=uuid4(), kind='test', language='en', timezone='Asia/Shanghai')
    created = await Service.create(PRINCIPAL, body)
    assert created.status == 'pending'
    assert (await Service.create(PRINCIPAL, body)).id == created.id
    current.status = 'running'
    current.started_at = datetime.now(timezone.utc)
    await worker.ExportTaskWorker.execute(created.id)
    assert current.status == 'completed'
    assert current.row_count == row_count
    assert current.expires_at - current.completed_at == timedelta(days=7)
    url = await worker.ExportTaskWorker.download(PRINCIPAL, created.id, {})
    assert url == 'https://storage.example/export?signature=test'
    assert state.active == 0


@pytest.mark.asyncio
async def test_access_revoked_during_upload_prevents_publication(monkeypatch, sessions):
    from app.services import export_task_worker as worker
    state, session = sessions
    monkeypatch.setattr(worker, "AsyncSessionLocal", session)
    original = task(status="running")
    monkeypatch.setattr(worker.Repo, "get", AsyncMock(return_value=original))
    monkeypatch.setattr(Service, "current", AsyncMock(return_value=PRINCIPAL))
    authorization = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(export_types._export_types["test"], "can_download", authorization)
    async def upload(*args):
        assert state.active == 0
    monkeypatch.setattr(worker, "create_storage_client", lambda: SimpleNamespace(upload_private=upload))
    transition = AsyncMock()
    monkeypatch.setattr(worker.Repo, "transition", transition)
    with pytest.raises(BusinessError) as error:
        await worker.ExportTaskWorker.generate(original.id)
    assert error.value.code == "EXPORT_ACCESS_CHANGED"
    assert authorization.await_count == 2
    transition.assert_not_awaited()
