"""
Abstract base class for OpenAgent clients.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


class OpenAgentClientError(Exception):
    """Raised when OpenAgent API calls fail."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


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
    attachment_handoff_tool_id: int | None = None


@dataclass(frozen=True)
class OpenAgentAgentTool:
    id: int
    agent_id: int
    name: str
    tool_type: str
    is_enabled: bool


@dataclass(frozen=True)
class OpenAgentFeedbackResult:
    step_id: int
    rating: str
    comment: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class OpenAgentKnowledgeBaseSummary:
    id: int
    name: str
    description: str | None
    status: str


@dataclass(frozen=True)
class OpenAgentKnowledgeBaseListResult:
    items: list[OpenAgentKnowledgeBaseSummary]
    total: int
    page: int
    per_page: int
    pages: int


@dataclass(frozen=True)
class OpenAgentQaDirectory:
    id: int
    parent_id: int | None
    name: str
    sort_order: int
    depth: int
    path: list[str]


@dataclass(frozen=True)
class OpenAgentQaDirectoryListResult:
    items: list[OpenAgentQaDirectory]
    total_qa_count: int


@dataclass(frozen=True)
class OpenAgentQaResult:
    id: int
    knowledge_base_id: int
    directory_id: int
    directory_path: list[str]
    question: str
    answer_markdown: str
    enabled: bool
    access_keywords: list[str]
    process_status: str


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

    async def get_agent_tool(
        self,
        base_url: str,
        api_key: str,
        agent_id: int,
        tool_id: int,
    ) -> OpenAgentAgentTool:
        """Get one OpenAgent tool configured for the selected agent."""
        raise NotImplementedError

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

    @abstractmethod
    async def list_knowledge_bases(
        self,
        base_url: str,
        api_key: str,
        page: int = 1,
        per_page: int = 100,
    ) -> OpenAgentKnowledgeBaseListResult:
        """List knowledge bases available to the provided API key."""
        ...

    @abstractmethod
    async def list_qa_directories(
        self,
        base_url: str,
        api_key: str,
        knowledge_base_id: int,
    ) -> OpenAgentQaDirectoryListResult:
        """List QA directories for a knowledge base."""
        ...

    @abstractmethod
    async def create_qa(
        self,
        base_url: str,
        api_key: str,
        knowledge_base_id: int,
        payload: dict[str, Any],
    ) -> OpenAgentQaResult:
        """Create a QA item in a knowledge base."""
        ...
