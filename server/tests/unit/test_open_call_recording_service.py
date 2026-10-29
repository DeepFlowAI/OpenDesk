"""Unit tests for the Open API recording service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, NotFoundError, RateLimitedError
from app.schemas.open_api import OpenApiContext
from app.services import open_call_recording_service as service_module
from app.services.open_call_recording_service import OpenCallRecordingService


NOW = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc)


class SessionTracker:
    def __init__(self) -> None:
        self.active = 0
        self.added: list = []
        self.commits = 0

    def __call__(self):
        tracker = self

        class _Session:
            async def __aenter__(self):
                tracker.active += 1
                return self

            async def __aexit__(self, *exc):
                tracker.active -= 1
                return False

            def add_all(self, rows):
                tracker.added.extend(rows)

            async def commit(self):
                tracker.commits += 1

        return _Session()


class FakeRedis:
    def __init__(self, used: int = 0, fail: bool = False) -> None:
        self.used = used
        self.fail = fail

    async def incrby(self, key, count):
        if self.fail:
            raise ConnectionError("down")
        self.used += count
        return self.used

    async def expire(self, key, seconds):
        return True


def _context(tenant_id: int = 7) -> OpenApiContext:
    return OpenApiContext(
        tenant_id=tenant_id,
        api_key_id=3,
        api_key_name="CRM",
        api_key_version=1,
        is_active=True,
    )


def _recording(**overrides):
    values = {
        "id": 1,
        "public_id": uuid4(),
        "phase": "bridged",
        "status": "completed",
        "storage_key": "tenant/7/recordings/a.wav",
        "started_at": NOW,
        "ended_at": NOW + timedelta(seconds=30),
        "duration_ms": 30_000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def wiring(monkeypatch):
    tracker = SessionTracker()
    redis = FakeRedis()
    signed: list[tuple[str, int, int]] = []

    class Storage:
        async def get_temporary_url(self, key, expires_seconds):
            signed.append((key, expires_seconds, tracker.active))
            return f"https://signed/{key}"

    state = SimpleNamespace(
        tracker=tracker,
        redis=redis,
        signed=signed,
        call=SimpleNamespace(id=5, public_id=uuid4()),
        recordings=[],
        recording=None,
    )

    async def get_call(db, *, tenant_id, call_public_id):
        state.call_lookup = (tenant_id, call_public_id)
        return state.call

    async def list_for_call(db, call_record_id):
        return state.recordings

    async def get_recording(db, *, tenant_id, recording_public_id):
        state.recording_lookup = (tenant_id, recording_public_id)
        return state.recording

    repo = service_module.OpenCallRecordingRepository
    monkeypatch.setattr(service_module, "AsyncSessionLocal", tracker)
    monkeypatch.setattr(repo, "get_call", get_call)
    monkeypatch.setattr(repo, "list_for_call", list_for_call)
    monkeypatch.setattr(repo, "get_recording", get_recording)
    monkeypatch.setattr(
        service_module, "redis_client", SimpleNamespace(client=redis)
    )
    monkeypatch.setattr(service_module, "create_storage_client", Storage)
    return state


@pytest.mark.asyncio
async def test_list_signs_playable_recordings_and_audits_each(wiring):
    playable = _recording(phase="llm", status="partial")
    failed = _recording(status="failed", storage_key=None)
    wiring.recordings = [playable, failed]
    call_public_id = wiring.call.public_id

    result = await OpenCallRecordingService.list_for_call_managed(
        _context(), str(call_public_id)
    )

    assert wiring.call_lookup == (7, call_public_id)
    first, second = result.items
    assert first.phase == "bot"
    assert first.download_url == "https://signed/tenant/7/recordings/a.wav"
    assert first.download_url_expires_at is not None
    assert second.download_url is None
    assert second.failure_reason == "recording_failed"
    assert wiring.redis.used == 1
    assert [row.recording_public_id for row in wiring.tracker.added] == [playable.public_id]
    audit = wiring.tracker.added[0]
    assert (audit.tenant_id, audit.api_key_id, audit.api_key_name) == (7, 3, "CRM")
    assert audit.call_public_id == call_public_id
    assert not hasattr(audit, "download_url")
    assert wiring.tracker.commits == 1


@pytest.mark.asyncio
async def test_signing_happens_without_an_open_session(wiring):
    wiring.recordings = [_recording(), _recording()]

    await OpenCallRecordingService.list_for_call_managed(
        _context(), str(wiring.call.public_id)
    )

    assert [entry[1] for entry in wiring.signed] == [3600, 3600]
    assert all(active == 0 for *_, active in wiring.signed)
    assert wiring.tracker.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("public_id", ["not-a-uuid", str(uuid4())])
async def test_unknown_or_cross_tenant_call_is_not_found(wiring, public_id):
    wiring.call = None

    with pytest.raises(NotFoundError):
        await OpenCallRecordingService.list_for_call_managed(_context(), public_id)
    assert wiring.tracker.added == []


@pytest.mark.asyncio
async def test_single_link_is_signed_and_audited(wiring):
    recording = _recording()
    call_public_id = uuid4()
    wiring.recording = (recording, call_public_id)

    result = await OpenCallRecordingService.get_download_url_managed(
        _context(), str(recording.public_id)
    )

    assert wiring.recording_lookup == (7, recording.public_id)
    assert result.call_public_id == call_public_id
    assert result.download_url.startswith("https://signed/")
    assert result.download_url_expires_at > datetime.now(timezone.utc) + timedelta(minutes=59)
    assert len(wiring.tracker.added) == 1


@pytest.mark.asyncio
async def test_single_link_for_failed_recording_conflicts(wiring):
    recording = _recording(status="failed", storage_key=None)
    wiring.recording = (recording, uuid4())

    with pytest.raises(ConflictError):
        await OpenCallRecordingService.get_download_url_managed(
            _context(), str(recording.public_id)
        )
    assert wiring.signed == []
    assert wiring.redis.used == 0


@pytest.mark.asyncio
async def test_single_link_unknown_recording_is_not_found(wiring):
    with pytest.raises(NotFoundError):
        await OpenCallRecordingService.get_download_url_managed(_context(), str(uuid4()))


@pytest.mark.asyncio
async def test_rate_limit_rejects_after_sixty_links(wiring):
    wiring.redis.used = 60
    recording = _recording()
    wiring.recording = (recording, uuid4())

    with pytest.raises(RateLimitedError):
        await OpenCallRecordingService.get_download_url_managed(
            _context(), str(recording.public_id)
        )
    assert wiring.signed == []
    assert wiring.tracker.added == []


@pytest.mark.asyncio
async def test_rate_limit_fails_open_when_redis_unavailable(wiring):
    wiring.redis.fail = True
    recording = _recording()
    wiring.recording = (recording, uuid4())

    result = await OpenCallRecordingService.get_download_url_managed(
        _context(), str(recording.public_id)
    )

    assert result.download_url
