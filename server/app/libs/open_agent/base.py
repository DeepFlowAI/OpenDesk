"""
Abstract base class for OpenAgent clients.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


class OpenAgentClientError(Exception):
    """Raised when OpenAgent API calls fail."""


@dataclass(frozen=True)
class OpenAgentConnectionResult:
    ok: bool
    message: str


@dataclass(frozen=True)
class OpenAgentAgentSummary:
    id: int
    name: str
    description: str | None
    status: str


@dataclass(frozen=True)
class OpenAgentAgentListResult:
    items: list[OpenAgentAgentSummary]
    total: int
    page: int
    per_page: int
    pages: int


@dataclass(frozen=True)
class OpenAgentAgentDetail(OpenAgentAgentSummary):
    welcome_message: dict[str, Any] | None = None
    faq: dict[str, Any] | None = None
    ai_disclaimer: dict[str, Any] | None = None


@dataclass(frozen=True)
class OpenAgentFeedbackResult:
    step_id: int
    rating: str
    comment: str | None = None
    updated_at: str | None = None


class BaseOpenAgentClient(ABC):

    @abstractmethod
    async def test_connection(self, base_url: str, api_key: str) -> OpenAgentConnectionResult:
        """Test whether the OpenAgent endpoint accepts the provided API key."""
        ...

    @abstractmethod
    async def list_agents(
        self,
        base_url: str,
        api_key: str,
        status_filter: str = "active",
        page: int = 1,
        per_page: int = 100,
    ) -> OpenAgentAgentListResult:
        """List OpenAgent agents available to the provided API key."""
        ...

    @abstractmethod
    async def get_agent(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
    ) -> OpenAgentAgentDetail:
        """Get a single OpenAgent agent including configuration."""
        ...

    @abstractmethod
    async def stream_chat(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
        payload: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """Stream an OpenAgent chat response as raw SSE bytes."""
        ...

    @abstractmethod
    async def stream_tool_result(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
        conversation_id: int,
        payload: dict[str, Any],
    ) -> AsyncIterator[bytes]:
        """Stream an OpenAgent external tool result response as raw SSE bytes."""
        ...

    @abstractmethod
    async def submit_feedback(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
        conversation_id: int,
        step_id: int,
        payload: dict[str, Any],
    ) -> OpenAgentFeedbackResult:
        """Submit feedback for an OpenAgent assistant reply step."""
        ...
