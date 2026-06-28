"""
Unit tests for conversation collaboration invites.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ForbiddenError
from app.enums import AgentOnlineStatus
from app.repositories.conversation_collaboration_repository import (
    INVITATION_ACCEPTED,
    INVITATION_PENDING,
    ConversationCollaborationRepository,
)
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.permission import EffectivePrincipal
from app.services.agent_status_service import AgentStatusService
from app.services.conversation_collaboration_service import (
    COLLABORATION_INVITE_PERMISSION,
    COLLABORATION_RESPOND_PERMISSION,
    ConversationCollaborationService,
)
from app.services.data_scope_service import DataScopeService


def _principal() -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=1,
        permissions=[COLLABORATION_RESPOND_PERMISSION],
        data_scopes={},
        group_ids=[],
    )


def _invite_principal(
    *,
    data_scope: str = "group",
    group_ids: list[int] | None = None,
) -> EffectivePrincipal:
    return EffectivePrincipal(
        user_id=10,
        tenant_id=1,
        permissions=[COLLABORATION_INVITE_PERMISSION],
        data_scopes={"session_record": data_scope},
        group_ids=group_ids if group_ids is not None else [7],
    )


def _conversation():
    return SimpleNamespace(
        id=100,
        tenant_id=1,
        agent_id=10,
        status="active",
        group_id=7,
    )


def _employee(employee_id: int, name: str):
    return SimpleNamespace(
        id=employee_id,
        tenant_id=1,
        username=f"user{employee_id}",
        name=name,
        display_name=name,
        job_number=f"J{employee_id}",
        avatar=None,
        max_concurrent=10,
        is_active=True,
    )


def _invitation():
    now = datetime(2099, 6, 24, 8, 0, tzinfo=timezone.utc)
    conversation = SimpleNamespace(
        id=100,
        public_id="cv_collab",
        tenant_id=1,
        agent_id=20,
        agent=SimpleNamespace(id=20, display_name="Owner", name="owner", avatar=None),
        visitor=SimpleNamespace(name="Visitor"),
        channel=SimpleNamespace(name="Web"),
        status="active",
        last_message_preview="hello",
        last_message_at=now,
    )
    return SimpleNamespace(
        id=300,
        tenant_id=1,
        conversation_id=100,
        conversation=conversation,
        inviter_id=20,
        invitee_id=10,
        inviter=SimpleNamespace(id=20, display_name="Owner", name="owner", avatar=None),
        invitee=SimpleNamespace(
            id=10,
            display_name="Helper Display",
            name="Legal Helper",
            nickname="Friendly Helper",
            username="helper",
            avatar=None,
        ),
        status=INVITATION_PENDING,
        expires_at=now + timedelta(minutes=5),
        responded_at=None,
        created_at=now,
    )


@pytest.mark.asyncio
async def test_accept_invitation_creates_collaborator_without_changing_owner(monkeypatch):
    invitation = _invitation()
    added_messages = []
    db = SimpleNamespace(
        add=lambda obj: (setattr(obj, "id", 501), added_messages.append(obj)),
        flush=AsyncMock(),
        commit=AsyncMock(),
    )
    create_collaborator = AsyncMock()
    emit_accepted = AsyncMock()
    conversation_payload = {
        "id": invitation.conversation_id,
        "viewer_relation": "collaborator",
        "agent": {"id": 20, "display_name": "Owner", "name": "owner", "avatar": None},
    }

    monkeypatch.setattr(
        ConversationCollaborationRepository,
        "get_invitation_by_id",
        AsyncMock(side_effect=[invitation, invitation]),
    )
    monkeypatch.setattr(
        ConversationCollaborationRepository,
        "get_active_collaborator",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        ConversationCollaborationRepository,
        "create_collaborator",
        create_collaborator,
    )
    monkeypatch.setattr(
        "app.services.conversation_service.ConversationService.get_agent_conversation",
        AsyncMock(return_value=conversation_payload),
    )
    monkeypatch.setattr(
        ConversationCollaborationService,
        "_emit_invitation_accepted",
        emit_accepted,
    )

    result = await ConversationCollaborationService.respond_invitation(
        db,
        tenant_id=1,
        invitation_id=invitation.id,
        action="accept",
        principal=_principal(),
    )

    assert invitation.status == INVITATION_ACCEPTED
    assert invitation.conversation.agent_id == 20
    create_collaborator.assert_awaited_once()
    collaborator_payload = create_collaborator.await_args.args[1]
    assert collaborator_payload["conversation_id"] == invitation.conversation_id
    assert collaborator_payload["agent_id"] == 10
    assert added_messages[0].content.startswith("Legal Helper ")
    assert added_messages[0].metadata_["event_type"] == "collaborator_joined"
    assert added_messages[0].metadata_["collaborator_name"] == "Legal Helper"
    assert added_messages[0].metadata_["collaborator_nickname"] == "Friendly Helper"
    assert result["conversation"]["viewer_relation"] == "collaborator"
    emit_accepted.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_targets_filters_candidates_by_invite_group_scope(monkeypatch):
    db = SimpleNamespace()
    r = SimpleNamespace()
    same_group = _employee(30, "Same Group")
    other_group = _employee(40, "Other Group")

    monkeypatch.setattr(
        ConversationRepository,
        "get_by_id",
        AsyncMock(return_value=_conversation()),
    )
    monkeypatch.setattr(
        ConversationCollaborationRepository,
        "get_active_collaborator_agent_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        ConversationCollaborationRepository,
        "get_pending_invitee_ids",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        DataScopeService,
        "get_group_peer_employee_ids",
        AsyncMock(return_value=[same_group.id]),
    )
    monkeypatch.setattr(
        EmployeeRepository,
        "get_transfer_candidates",
        AsyncMock(return_value=[same_group, other_group]),
    )
    monkeypatch.setattr(EmployeeRepository, "has_effective_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(
        AgentStatusService,
        "get_status",
        AsyncMock(
            return_value={
                "status": AgentOnlineStatus.ONLINE.value,
                "current_count": 0,
                "max_concurrent": 10,
            }
        ),
    )

    result = await ConversationCollaborationService.list_targets(
        db,
        r,
        tenant_id=1,
        conversation_id=100,
        keyword=None,
        principal=_invite_principal(),
    )

    assert [item["id"] for item in result["items"]] == [same_group.id]


@pytest.mark.asyncio
async def test_create_invitation_rejects_target_outside_invite_group_scope(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock())
    r = SimpleNamespace()
    target = _employee(40, "Other Group")

    monkeypatch.setattr(
        ConversationRepository,
        "get_by_id",
        AsyncMock(return_value=_conversation()),
    )
    monkeypatch.setattr(
        ConversationCollaborationRepository,
        "is_active_collaborator",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        ConversationCollaborationRepository,
        "get_pending_invitation",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(EmployeeRepository, "get_by_id", AsyncMock(return_value=target))
    monkeypatch.setattr(EmployeeRepository, "has_effective_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(
        DataScopeService,
        "get_group_peer_employee_ids",
        AsyncMock(return_value=[30]),
    )

    with pytest.raises(ForbiddenError):
        await ConversationCollaborationService.create_invitation(
            db,
            r,
            tenant_id=1,
            conversation_id=100,
            invitee_id=target.id,
            principal=_invite_principal(),
        )
