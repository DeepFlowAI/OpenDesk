"""
Unit tests for the VOD client factory and providers (mock behavior + event parsing).
"""
import pytest

from app.libs.vod import base as vod_base
from app.libs.vod.factory import get_vod_client, reset_vod_client
from app.libs.vod.providers.mock import MockVodClient


@pytest.fixture(autouse=True)
def _reset_factory():
    reset_vod_client()
    yield
    reset_vod_client()


class TestVodFactory:
    def test_mock_provider_returns_mock_client(self, monkeypatch):
        monkeypatch.setattr("app.libs.vod.factory.settings.VOD_PROVIDER", "mock")
        client = get_vod_client()
        assert isinstance(client, MockVodClient)

    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.setattr("app.libs.vod.factory.settings.VOD_PROVIDER", "unknown")
        with pytest.raises(ValueError):
            get_vod_client()

    def test_factory_caches_instance(self, monkeypatch):
        monkeypatch.setattr("app.libs.vod.factory.settings.VOD_PROVIDER", "mock")
        assert get_vod_client() is get_vod_client()


class TestMockVodClient:
    @pytest.mark.asyncio
    async def test_upload_credential_returns_mock_video_id(self):
        client = MockVodClient()
        credential = await client.create_upload_credential(title="t", filename="a.mp4")
        assert credential.video_id.startswith("MOCK-")
        assert credential.upload_address

    @pytest.mark.asyncio
    async def test_play_info_is_ready(self):
        client = MockVodClient()
        info = await client.get_play_info(video_id="MOCK-1")
        assert info.status == "ok"
        assert info.play_url

    def test_parse_event_requires_video_id(self):
        client = MockVodClient()
        assert client.parse_transcode_event({}) is None
        event = client.parse_transcode_event({"video_id": "v1", "success": False})
        assert event is not None
        assert event.video_id == "v1"
        assert event.success is False


class TestAliyunEventParsing:
    """Pure-payload parsing does not need the Aliyun SDK installed."""

    def test_transcode_complete_success(self):
        from app.libs.vod.providers.aliyun import AliyunVodClient

        client = AliyunVodClient(access_key_id="", access_key_secret="", endpoint="")
        event = client.parse_transcode_event(
            {
                "EventType": "FileTranscodeComplete",
                "EventData": {"VideoId": "abc", "Status": "success", "Duration": "95.5"},
            }
        )
        assert event is not None
        assert event.video_id == "abc"
        assert event.success is True
        assert event.duration_seconds == 95

    def test_stream_transcode_complete_success(self):
        # StreamTranscodeComplete is the current name of FileTranscodeComplete.
        from app.libs.vod.providers.aliyun import AliyunVodClient

        client = AliyunVodClient(access_key_id="", access_key_secret="", endpoint="")
        event = client.parse_transcode_event(
            {
                "EventType": "StreamTranscodeComplete",
                "EventData": {"VideoId": "abc", "Status": "success", "Duration": "95.5"},
            }
        )
        assert event is not None
        assert event.video_id == "abc"
        assert event.success is True
        assert event.duration_seconds == 95

    def test_irrelevant_event_returns_none(self):
        from app.libs.vod.providers.aliyun import AliyunVodClient

        client = AliyunVodClient(access_key_id="", access_key_secret="", endpoint="")
        assert client.parse_transcode_event({"EventType": "SnapshotComplete"}) is None

    def test_event_data_as_json_string(self):
        from app.libs.vod.providers.aliyun import AliyunVodClient

        client = AliyunVodClient(access_key_id="", access_key_secret="", endpoint="")
        event = client.parse_transcode_event(
            {
                "EventType": "FileTranscodeComplete",
                "EventData": '{"VideoId": "xyz", "Status": "fail"}',
            }
        )
        assert event is not None
        assert event.video_id == "xyz"
        assert event.success is False


class TestAliyunVodClientRequests:
    """Request-building tests stub out the Aliyun SDK (not installed locally)."""

    @pytest.fixture
    def _fake_sdk(self, monkeypatch):
        import sys
        import types

        class _Request:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class _Body:
            video_id = "vid-1"
            upload_address = "addr"
            upload_auth = "auth"

        class _Response:
            body = _Body()

        class _FakeSdkClient:
            def __init__(self):
                self.calls = []

            def create_upload_video(self, request):
                self.calls.append(("create_upload_video", request))
                return _Response()

            def submit_transcode_jobs(self, request):
                self.calls.append(("submit_transcode_jobs", request))
                return _Response()

        fake_models = types.ModuleType("alibabacloud_vod20170321.models")
        fake_models.CreateUploadVideoRequest = _Request
        fake_models.SubmitTranscodeJobsRequest = _Request
        fake_sdk = types.ModuleType("alibabacloud_vod20170321")
        fake_sdk.models = fake_models
        monkeypatch.setitem(sys.modules, "alibabacloud_vod20170321", fake_sdk)
        monkeypatch.setitem(sys.modules, "alibabacloud_vod20170321.models", fake_models)

        from app.libs.vod.providers.aliyun import AliyunVodClient

        sdk_client = _FakeSdkClient()
        client = AliyunVodClient(
            access_key_id="",
            access_key_secret="",
            endpoint="",
            template_group_id="tg-1",
        )
        monkeypatch.setattr(client, "_build_client", lambda: sdk_client)
        return client, sdk_client

    @pytest.mark.asyncio
    async def test_upload_credential_sets_template_group(self, _fake_sdk):
        client, sdk_client = _fake_sdk
        credential = await client.create_upload_credential(title="t", filename="a.mp4")
        assert credential.video_id == "vid-1"
        _, request = sdk_client.calls[0]
        assert request.template_group_id == "tg-1"

    @pytest.mark.asyncio
    async def test_submit_transcode_uses_jobs_api(self, _fake_sdk):
        client, sdk_client = _fake_sdk
        assert await client.submit_transcode(video_id="vid-1") is True
        name, request = sdk_client.calls[0]
        assert name == "submit_transcode_jobs"
        assert request.video_id == "vid-1"
        assert request.template_group_id == "tg-1"
