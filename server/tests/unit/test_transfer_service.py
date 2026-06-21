"""
Unit tests for ``TransferService``.

Repositories and the realtime transport are mocked so the suite exercises the
business logic in isolation, without touching the database, Redis, or
Socket.IO. The fake DB session captures objects added to it and emulates a
``flush`` that hands back primary keys so the ``new_message`` payload can be
asserted on.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import BusinessError, ForbiddenError, NotFoundError
from app.enums import AgentOnlineStatus, ConversationStatus
from app.models.message import Message
from app.schemas.permission import EffectivePrincipal
from app.services import transfer_service as ts
from app.services.transfer_service import TransferService


def _make_employee(
    *,
    id: int,
    tenant_id: int = 7,
    name: str = "Worker",
    display_name: str | None = None,
    nickname: str | None = None,
    roles: list[str] | None = None,
    is_active: bool = True,
):
    return SimpleNamespace(
        id=id,
        tenant_id=tenant_id,
        username=f"user{id}",
        name=name,
        display_name=display_name,
        nickname=nickname,
        job_number=f"J{id}",
        avatar=None,
        max_concurrent=10,
        roles=roles if roles is not None else ["agent"],
        is_active=is_active,
    )


def _principal(user_id: int, *, tenant_id: int = 7, group_ids: list[int] | None = None):
    """Build an EffectivePrincipal for transfer authorization paths."""
    return EffectivePrincipal(
        user_id=user_id,
        tenant_id=tenant_id,
        permissions=["chat.conversation.transfer"],
        data_scopes={"session_record": "all"},
        group_ids=group_ids or [],
    )


def _peer_principal(
    user_id: int,
    *,
    tenant_id: int = 7,
    data_scope: str = "all",
    group_ids: list[int] | None = None,
) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=user_id,
        tenant_id=tenant_id,
        permissions=["chat.conversation.peer.view"],
        data_scopes={"chat.conversation.peer.view": data_scope},
        group_ids=group_ids or [],
    )


def _make_conversation(
    *,
    id: int = 100,
    tenant_id: int = 7,
    agent_id: int | None = 11,
    status: str = ConversationStatus.ACTIVE.value,
    group_id: int | None = None,
):
    visitor = SimpleNamespace(
        id=900,
        public_id="usr_test_900",
        external_id="ext-900",
        name="访客 900",
        avatar_color="#abc",
    )
    channel = SimpleNamespace(id=5, name="Web", channel_type="web")
    return SimpleNamespace(
        id=id,
        public_id=f"cv_test_{id}",
        share_code=f"CV-T{id:06d}",
        tenant_id=tenant_id,
        agent_id=agent_id,
        status=status,
        visitor=visitor,
        visitor_id=visitor.id,
        channel=channel,
        group=None,
        group_id=group_id,
        agent=None,
        started_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ended_at=None,
        ended_by=None,
        last_message_at=None,
        last_message_preview=None,
        unread_count=0,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


class _FakeDB:
    """Async session double tailored to TransferService's usage pattern.

    - ``add`` records the object so we can assert on it later
    - ``flush`` assigns ids/created_at to any added Message rows so the
      service can build its broadcast payload
    - ``execute`` returns a mock with a controllable ``rowcount`` (defaults
      to 1 — the conditional UPDATE wins). Tests can set
      ``fake_db.update_rowcount = 0`` to simulate a concurrent transfer
      losing the optimistic-lock race.
    - ``commit/rollback/refresh`` are awaitable spies
    """

    def __init__(self) -> None:
        self.added: list = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.refresh = AsyncMock()
        self.update_rowcount = 1
        self._next_msg_id = 1000
        self.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, *_args, **_kwargs):
        result = MagicMock()
        result.rowcount = self.update_rowcount
        return result

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        for obj in self.added:
            if isinstance(obj, Message) and obj.id is None:
                obj.id = self._next_msg_id
                obj.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
                self._next_msg_id += 1


@pytest.fixture
def fake_db() -> _FakeDB:
    return _FakeDB()


@pytest.fixture
def fake_redis():
    return AsyncMock()


# ---------------------------------------------------------------------------
# list_targets
# ---------------------------------------------------------------------------


class TestListTargets:

    @pytest.mark.asyncio
    async def test_orders_online_first_then_busy_then_offline(self, fake_db, fake_redis):
        emp_online = _make_employee(id=1, name="Charlie")
        emp_busy = _make_employee(id=2, name="Alice")
        emp_offline = _make_employee(id=3, name="Bob")

        async def fake_get_status(_r, _t, user_id, _max):
            mapping = {
                1: AgentOnlineStatus.ONLINE.value,
                2: AgentOnlineStatus.BUSY.value,
                3: AgentOnlineStatus.OFFLINE.value,
            }
            return {
                "user_id": user_id,
                "status": mapping[user_id],
                "current_count": 0,
                "max_concurrent": 10,
            }

        with patch.object(
            ts.EmployeeRepository,
            "get_transfer_candidates",
            new=AsyncMock(return_value=[emp_busy, emp_online, emp_offline]),
        ), patch.object(
            ts.AgentStatusService,
            "get_status",
            new=AsyncMock(side_effect=fake_get_status),
        ):
            result = await TransferService.list_targets(
                db=fake_db,
                r=fake_redis,
                tenant_id=7,
                current_user_id=99,
            )

        statuses = [item["online_status"] for item in result["items"]]
        assert statuses == [
            AgentOnlineStatus.ONLINE.value,
            AgentOnlineStatus.BUSY.value,
            AgentOnlineStatus.OFFLINE.value,
        ]
        assert result["total"] == 3

    @pytest.mark.asyncio
    async def test_passes_keyword_and_excludes_self(self, fake_db, fake_redis):
        repo_mock = AsyncMock(return_value=[])
        with patch.object(
            ts.EmployeeRepository, "get_transfer_candidates", new=repo_mock
        ):
            await TransferService.list_targets(
                db=fake_db,
                r=fake_redis,
                tenant_id=7,
                current_user_id=99,
                keyword="alice",
            )
        repo_mock.assert_awaited_once()
        kwargs = repo_mock.await_args.kwargs
        assert kwargs["keyword"] == "alice"
        assert kwargs["exclude_user_ids"] == [99]

    @pytest.mark.asyncio
    async def test_admin_excludes_conversation_owner_when_conversation_id_provided(
        self, fake_db, fake_redis
    ):
        """Admin browsing another agent's conversation must not see that
        agent in the candidate list."""
        conversation = _make_conversation(agent_id=42, tenant_id=7)
        repo_mock = AsyncMock(return_value=[])
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ), patch.object(
            ts.DataScopeService,
            "can_access_conversation",
            new=AsyncMock(return_value=True),
        ), patch.object(
            ts.EmployeeRepository, "get_transfer_candidates", new=repo_mock
        ):
            await TransferService.list_targets(
                db=fake_db,
                r=fake_redis,
                tenant_id=7,
                current_user_id=99,
                conversation_id=conversation.id,
                principal=_principal(99),
            )

        kwargs = repo_mock.await_args.kwargs
        assert set(kwargs["exclude_user_ids"]) == {42}

    @pytest.mark.asyncio
    async def test_cross_tenant_conversation_id_raises_not_found(
        self, fake_db, fake_redis
    ):
        """Cross-tenant probing must surface as NotFound (never leak data)."""
        conversation = _make_conversation(agent_id=42, tenant_id=999)
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ):
            with pytest.raises(NotFoundError):
                await TransferService.list_targets(
                    db=fake_db,
                    r=fake_redis,
                    tenant_id=7,
                    current_user_id=99,
                    conversation_id=conversation.id,
                    roles=["admin"],
                )


# ---------------------------------------------------------------------------
# transfer_conversation
# ---------------------------------------------------------------------------


class _TransferPatches:
    """Convenience wrapper that patches every collaborator the service uses."""

    def __init__(
        self,
        conversation,
        target,
        initiator,
        *,
        target_status,
        history_for_target: list | None = None,
        history_for_initiator: list | None = None,
    ):
        self._patches = []
        self.conv_repo_get_by_id = AsyncMock(return_value=conversation)
        self.emp_repo_get_by_id = AsyncMock(side_effect=[target, initiator])
        self.has_permission = AsyncMock(return_value=True)
        # Principal-based history view: ``get_current_principal`` is invoked
        # for the receiver (and the initiator when no principal is supplied),
        # while ``session_history_filters`` decides the history query scope.
        self.get_principal = AsyncMock(side_effect=lambda _db, payload: _principal(payload["user_id"]))
        self.session_history_filters = AsyncMock(return_value=(None, None))
        self.can_access = AsyncMock(return_value=True)
        self.status_get = AsyncMock(return_value={
            "user_id": getattr(target, "id", 0),
            "status": target_status,
            "current_count": 0,
            "max_concurrent": 10,
        })
        self.status_inc = AsyncMock()
        self.status_dec = AsyncMock()
        # Two calls happen in transfer_conversation: receiver first, then
        # initiator. Default to no history for both unless overridden.
        self.history_mock = AsyncMock(
            side_effect=[history_for_target or [], history_for_initiator or []]
        )
        self.rt = MagicMock()
        self.rt.emit = AsyncMock()
        self.get_rt = MagicMock(return_value=self.rt)

    def __enter__(self):
        self._patches = [
            patch.object(ts.ConversationRepository, "get_by_id", new=self.conv_repo_get_by_id),
            patch.object(
                ts.ConversationRepository, "get_visitor_history", new=self.history_mock
            ),
            patch.object(ts.EmployeeRepository, "get_by_id", new=self.emp_repo_get_by_id),
            patch.object(
                ts.EmployeeRepository, "has_effective_permission", new=self.has_permission
            ),
            patch.object(
                ts.PermissionService, "get_current_principal", new=self.get_principal
            ),
            patch.object(
                ts.DataScopeService, "session_history_filters", new=self.session_history_filters
            ),
            patch.object(
                ts.DataScopeService, "can_access_conversation", new=self.can_access
            ),
            patch.object(ts.AgentStatusService, "get_status", new=self.status_get),
            patch.object(ts.AgentStatusService, "increment_count", new=self.status_inc),
            patch.object(ts.AgentStatusService, "decrement_count", new=self.status_dec),
            patch.object(ts, "get_realtime_transport", new=self.get_rt),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        for p in self._patches:
            p.stop()


class TestTransferConversation:

    @pytest.mark.asyncio
    async def test_success_writes_system_message_and_emits_events(self, fake_db, fake_redis):
        conversation = _make_conversation(agent_id=11)
        target = _make_employee(id=22, name="Bob", display_name="Bob 客服", nickname="Bob酱")
        initiator = _make_employee(id=11, name="Alice", display_name="Alice 客服", nickname="小艾")

        with _TransferPatches(
            conversation, target, initiator,
            target_status=AgentOnlineStatus.ONLINE.value,
        ) as p:
            result = await TransferService.transfer_conversation(
                db=fake_db,
                r=fake_redis,
                conversation_id=conversation.id,
                target_agent_id=target.id,
                current_user_id=11,
                tenant_id=7,
                roles=["agent"],
            )

        # 1) Atomic DB write — single commit, conditional UPDATE happened,
        #    audit message added
        assert fake_db.commit.await_count == 1
        assert fake_db.rollback.await_count == 0
        # Conditional UPDATE for the reassign + last_message preview; no
        # second UPDATE is needed any more.
        assert fake_db.execute.await_count == 1

        added_messages = [obj for obj in fake_db.added if isinstance(obj, Message)]
        assert len(added_messages) == 1
        assert "Alice 将会话转接给 Bob" == added_messages[0].content
        assert added_messages[0].metadata_ == {
            "event_type": "session_transfer",
            "from_agent_name": "Alice",
            "to_agent_name": "Bob",
            "from_agent_nickname": "小艾",
            "to_agent_nickname": "Bob酱",
        }

        # 2) Redis side effects
        assert p.status_dec.await_count == 1
        assert p.status_inc.await_count == 1

        # 3) Realtime broadcast: 3 new_message + 2 conversation_transferred + 1 list invalidation
        assert p.rt.emit.await_count == 6
        event_names = [call.args[0] for call in p.rt.emit.await_args_list]
        assert event_names.count("new_message") == 3
        assert event_names.count("conversation_transferred") == 2
        assert event_names.count("conversation_list_updated") == 1

        # 4) Receiving room gets a complete conversation payload
        to_call = next(
            call for call in p.rt.emit.await_args_list
            if call.args[0] == "conversation_transferred"
            and call.kwargs.get("room") == "agent:7:22"
        )
        payload = to_call.args[1]
        assert payload["conversation_id"] == conversation.id
        assert payload["from_agent_id"] == 11
        assert payload["to_agent_id"] == 22
        assert "conversation" in payload
        assert payload["conversation"]["id"] == conversation.id
        assert "started_at" in payload["conversation"]

        # 4a) The realtime payload MUST be JSON-serializable: Socket.IO has
        #     no Pydantic layer, so a stray ``datetime`` would silently fail
        #     the broadcast in production. Guard against that regression.
        json.dumps(payload)
        for key in ("started_at", "created_at", "last_message_at"):
            value = payload["conversation"][key]
            assert value is None or isinstance(value, str), (
                f"{key} must be ISO string or None, got {type(value).__name__}"
            )

        # Likewise for the system message payload broadcast over Socket.IO.
        msg_call = next(
            call for call in p.rt.emit.await_args_list
            if call.args[0] == "new_message"
        )
        json.dumps(msg_call.args[1])

        # 5) Returned dict matches the ConversationResponse shape
        assert result["id"] == conversation.id
        assert result["public_id"] == conversation.public_id
        assert result["share_code"] == conversation.share_code
        assert "started_at" in result
        assert "last_message_preview" in result
        # REST response is also JSON-safe (kept on the same shape as the
        # realtime payload to prevent drift between the two surfaces).
        json.dumps(result)
        assert isinstance(result["started_at"], str)

    @pytest.mark.asyncio
    async def test_admin_initiator_appears_as_message_author(self, fake_db, fake_redis):
        """When admin transfers someone else's conversation, the audit
        message names the admin (the requirement names the initiator)."""
        conversation = _make_conversation(agent_id=11)
        target = _make_employee(id=22, name="Bob", display_name="Bob 客服")
        admin = _make_employee(
            id=999, name="管理员", display_name="管理员", roles=["admin"]
        )

        with _TransferPatches(
            conversation, target, admin,
            target_status=AgentOnlineStatus.ONLINE.value,
        ):
            await TransferService.transfer_conversation(
                db=fake_db,
                r=fake_redis,
                conversation_id=conversation.id,
                target_agent_id=target.id,
                current_user_id=999,  # admin, not the conversation owner
                tenant_id=7,
                principal=_principal(999),
            )

        added_messages = [obj for obj in fake_db.added if isinstance(obj, Message)]
        assert added_messages[0].content == "管理员 将会话转接给 Bob"

    @pytest.mark.asyncio
    async def test_peer_view_principal_can_transfer_peer_conversation(
        self, fake_db, fake_redis
    ):
        conversation = _make_conversation(agent_id=11)
        target = _make_employee(id=22, name="Bob", display_name="Bob 客服")
        initiator = _make_employee(id=99, name="Supervisor", display_name="Supervisor")

        with _TransferPatches(
            conversation, target, initiator,
            target_status=AgentOnlineStatus.ONLINE.value,
        ):
            await TransferService.transfer_conversation(
                db=fake_db,
                r=fake_redis,
                conversation_id=conversation.id,
                target_agent_id=target.id,
                current_user_id=99,
                tenant_id=7,
                principal=_peer_principal(99),
            )

        added_messages = [obj for obj in fake_db.added if isinstance(obj, Message)]
        assert added_messages[0].content == "Supervisor 将会话转接给 Bob"

    @pytest.mark.asyncio
    async def test_peer_view_self_scope_cannot_transfer_peer_conversation(
        self, fake_db, fake_redis
    ):
        conversation = _make_conversation(agent_id=11)
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ):
            with pytest.raises(ForbiddenError):
                await TransferService.transfer_conversation(
                    db=fake_db,
                    r=fake_redis,
                    conversation_id=conversation.id,
                    target_agent_id=22,
                    current_user_id=99,
                    tenant_id=7,
                    principal=_peer_principal(99, data_scope="self"),
                )

    @pytest.mark.asyncio
    async def test_db_failure_rolls_back_and_skips_emit(self, fake_db, fake_redis):
        """If commit fails the service must rollback and never broadcast."""
        conversation = _make_conversation(agent_id=11)
        target = _make_employee(id=22, name="Bob")
        initiator = _make_employee(id=11, name="Alice")
        fake_db.commit = AsyncMock(side_effect=RuntimeError("DB down"))

        with _TransferPatches(
            conversation, target, initiator,
            target_status=AgentOnlineStatus.ONLINE.value,
        ) as p:
            with pytest.raises(RuntimeError):
                await TransferService.transfer_conversation(
                    db=fake_db,
                    r=fake_redis,
                    conversation_id=conversation.id,
                    target_agent_id=target.id,
                    current_user_id=11,
                    tenant_id=7,
                    roles=["agent"],
                )

        assert fake_db.rollback.await_count == 1
        assert p.rt.emit.await_count == 0
        assert p.status_inc.await_count == 0
        assert p.status_dec.await_count == 0

    @pytest.mark.asyncio
    async def test_conversation_not_found_raises(self, fake_db, fake_redis):
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await TransferService.transfer_conversation(
                    db=fake_db,
                    r=fake_redis,
                    conversation_id=1,
                    target_agent_id=2,
                    current_user_id=11,
                    tenant_id=7,
                    roles=["agent"],
                )

    @pytest.mark.asyncio
    async def test_non_owner_non_admin_raises_forbidden(self, fake_db, fake_redis):
        conversation = _make_conversation(agent_id=11)
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ):
            with pytest.raises(ForbiddenError):
                await TransferService.transfer_conversation(
                    db=fake_db,
                    r=fake_redis,
                    conversation_id=conversation.id,
                    target_agent_id=22,
                    current_user_id=999,  # not the owner
                    tenant_id=7,
                    roles=["agent"],
                )

    @pytest.mark.asyncio
    async def test_closed_conversation_raises(self, fake_db, fake_redis):
        conversation = _make_conversation(
            agent_id=11, status=ConversationStatus.CLOSED.value
        )
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ):
            with pytest.raises(BusinessError):
                await TransferService.transfer_conversation(
                    db=fake_db,
                    r=fake_redis,
                    conversation_id=conversation.id,
                    target_agent_id=22,
                    current_user_id=11,
                    tenant_id=7,
                    roles=["agent"],
                )

    @pytest.mark.asyncio
    async def test_target_equals_current_agent_raises(self, fake_db, fake_redis):
        conversation = _make_conversation(agent_id=11)
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ):
            with pytest.raises(BusinessError):
                await TransferService.transfer_conversation(
                    db=fake_db,
                    r=fake_redis,
                    conversation_id=conversation.id,
                    target_agent_id=11,
                    current_user_id=11,
                    tenant_id=7,
                    roles=["agent"],
                )

    @pytest.mark.asyncio
    async def test_target_not_found_raises(self, fake_db, fake_redis):
        conversation = _make_conversation(agent_id=11)
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ), patch.object(
            ts.EmployeeRepository,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await TransferService.transfer_conversation(
                    db=fake_db,
                    r=fake_redis,
                    conversation_id=conversation.id,
                    target_agent_id=22,
                    current_user_id=11,
                    tenant_id=7,
                    roles=["agent"],
                )

    @pytest.mark.asyncio
    async def test_target_without_chat_access_raises_not_found(self, fake_db, fake_redis):
        """A target employee lacking ``chat.workspace.use`` is treated as a
        non-candidate (NotFound), matching the candidate-list eligibility."""
        conversation = _make_conversation(agent_id=11)
        target = _make_employee(id=22, name="Bob")

        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ), patch.object(
            ts.EmployeeRepository,
            "get_by_id",
            new=AsyncMock(return_value=target),
        ), patch.object(
            ts.EmployeeRepository,
            "has_effective_permission",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(NotFoundError):
                await TransferService.transfer_conversation(
                    db=fake_db,
                    r=fake_redis,
                    conversation_id=conversation.id,
                    target_agent_id=22,
                    current_user_id=11,
                    tenant_id=7,
                    roles=["agent"],
                )

    @pytest.mark.asyncio
    async def test_target_offline_raises(self, fake_db, fake_redis):
        conversation = _make_conversation(agent_id=11)
        target = _make_employee(id=22, name="Bob")

        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ), patch.object(
            ts.EmployeeRepository,
            "get_by_id",
            new=AsyncMock(return_value=target),
        ), patch.object(
            ts.EmployeeRepository,
            "has_effective_permission",
            new=AsyncMock(return_value=True),
        ), patch.object(
            ts.AgentStatusService,
            "get_status",
            new=AsyncMock(return_value={
                "user_id": 22,
                "status": AgentOnlineStatus.OFFLINE.value,
                "current_count": 0,
                "max_concurrent": 10,
            }),
        ):
            with pytest.raises(BusinessError):
                await TransferService.transfer_conversation(
                    db=fake_db,
                    r=fake_redis,
                    conversation_id=conversation.id,
                    target_agent_id=22,
                    current_user_id=11,
                    tenant_id=7,
                    roles=["agent"],
                )

    @pytest.mark.asyncio
    async def test_concurrent_transfer_loses_race_and_aborts(self, fake_db, fake_redis):
        """If a concurrent request mutated the row first, the conditional
        UPDATE returns rowcount=0; the loser must roll back, refuse to write
        the audit message, and skip the realtime broadcast entirely."""
        conversation = _make_conversation(agent_id=11)
        target = _make_employee(id=22, name="Bob")
        initiator = _make_employee(id=11, name="Alice")
        fake_db.update_rowcount = 0  # simulate concurrent winner

        with _TransferPatches(
            conversation, target, initiator,
            target_status=AgentOnlineStatus.ONLINE.value,
        ) as p:
            with pytest.raises(BusinessError):
                await TransferService.transfer_conversation(
                    db=fake_db,
                    r=fake_redis,
                    conversation_id=conversation.id,
                    target_agent_id=target.id,
                    current_user_id=11,
                    tenant_id=7,
                    roles=["agent"],
                )

        # No commit, but the loser still rolled back, didn't add a system
        # message, didn't touch Redis counters and didn't broadcast.
        assert fake_db.commit.await_count == 0
        assert fake_db.rollback.await_count == 1
        assert not [obj for obj in fake_db.added if isinstance(obj, Message)]
        assert p.status_inc.await_count == 0
        assert p.status_dec.await_count == 0
        assert p.rt.emit.await_count == 0

    @pytest.mark.asyncio
    async def test_receiver_payload_includes_real_history_flag(
        self, fake_db, fake_redis
    ):
        """``has_history_conversations`` must reflect the receiver's
        permission view, not be hard-coded to False."""
        conversation = _make_conversation(agent_id=11)
        target = _make_employee(id=22, name="Bob")
        initiator = _make_employee(id=11, name="Alice")

        # Receiver has visible history; initiator does not.
        with _TransferPatches(
            conversation, target, initiator,
            target_status=AgentOnlineStatus.ONLINE.value,
            history_for_target=[SimpleNamespace(id=1)],
            history_for_initiator=[],
        ) as p:
            result = await TransferService.transfer_conversation(
                db=fake_db,
                r=fake_redis,
                conversation_id=conversation.id,
                target_agent_id=target.id,
                current_user_id=11,
                tenant_id=7,
                roles=["agent"],
            )

        to_call = next(
            call for call in p.rt.emit.await_args_list
            if call.args[0] == "conversation_transferred"
            and call.kwargs.get("room") == "agent:7:22"
        )
        receiver = to_call.args[1]["conversation"]
        assert receiver["has_history_conversations"] is True
        # Initiator's REST response uses their own perspective.
        assert result["has_history_conversations"] is False


# ---------------------------------------------------------------------------
# list_targets authorization
# ---------------------------------------------------------------------------


class TestListTargetsAuthorization:

    @pytest.mark.asyncio
    async def test_non_owner_non_admin_cannot_inspect_conversation(
        self, fake_db, fake_redis
    ):
        """A regular agent passing a conversation_id they don't own must be
        rejected — otherwise they could probe the candidate list to infer
        the conversation's current owner."""
        conversation = _make_conversation(agent_id=42, tenant_id=7)
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ):
            with pytest.raises(ForbiddenError):
                await TransferService.list_targets(
                    db=fake_db,
                    r=fake_redis,
                    tenant_id=7,
                    current_user_id=99,  # not the owner
                    conversation_id=conversation.id,
                    roles=["agent"],
                )

    @pytest.mark.asyncio
    async def test_owner_can_inspect_their_conversation(self, fake_db, fake_redis):
        conversation = _make_conversation(agent_id=99, tenant_id=7)
        repo_mock = AsyncMock(return_value=[])
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ), patch.object(
            ts.EmployeeRepository, "get_transfer_candidates", new=repo_mock
        ):
            await TransferService.list_targets(
                db=fake_db,
                r=fake_redis,
                tenant_id=7,
                current_user_id=99,
                conversation_id=conversation.id,
                roles=["agent"],
            )
        # Owner is excluded twice via current_user_id and exclude_user_ids
        # (set semantics already de-duplicate inside the service).
        kwargs = repo_mock.await_args.kwargs
        assert set(kwargs["exclude_user_ids"]) == {99}

    @pytest.mark.asyncio
    async def test_admin_can_inspect_any_conversation(self, fake_db, fake_redis):
        conversation = _make_conversation(agent_id=42, tenant_id=7)
        repo_mock = AsyncMock(return_value=[])
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ), patch.object(
            ts.DataScopeService,
            "can_access_conversation",
            new=AsyncMock(return_value=True),
        ), patch.object(
            ts.EmployeeRepository, "get_transfer_candidates", new=repo_mock
        ):
            await TransferService.list_targets(
                db=fake_db,
                r=fake_redis,
                tenant_id=7,
                current_user_id=999,  # admin, not owner
                conversation_id=conversation.id,
                principal=_principal(999),
            )
        kwargs = repo_mock.await_args.kwargs
        assert set(kwargs["exclude_user_ids"]) == {42}

    @pytest.mark.asyncio
    async def test_peer_view_principal_can_inspect_peer_conversation(
        self, fake_db, fake_redis
    ):
        conversation = _make_conversation(agent_id=42, tenant_id=7)
        repo_mock = AsyncMock(return_value=[])
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=conversation),
        ), patch.object(
            ts.EmployeeRepository, "get_transfer_candidates", new=repo_mock
        ):
            await TransferService.list_targets(
                db=fake_db,
                r=fake_redis,
                tenant_id=7,
                current_user_id=99,
                conversation_id=conversation.id,
                principal=_peer_principal(99),
            )

        kwargs = repo_mock.await_args.kwargs
        assert set(kwargs["exclude_user_ids"]) == {42}

    @pytest.mark.asyncio
    async def test_peer_view_without_conversation_context_cannot_inspect_targets(
        self, fake_db, fake_redis
    ):
        with pytest.raises(ForbiddenError):
            await TransferService.list_targets(
                db=fake_db,
                r=fake_redis,
                tenant_id=7,
                current_user_id=99,
                principal=_peer_principal(99),
            )

    @pytest.mark.asyncio
    async def test_unknown_conversation_raises_not_found(self, fake_db, fake_redis):
        with patch.object(
            ts.ConversationRepository,
            "get_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(NotFoundError):
                await TransferService.list_targets(
                    db=fake_db,
                    r=fake_redis,
                    tenant_id=7,
                    current_user_id=99,
                    conversation_id=12345,
                    roles=["agent"],
                )
