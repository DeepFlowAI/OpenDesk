"""
OpenAgent client factory.
"""
from app.configs.settings import settings
from app.libs.open_agent.base import BaseOpenAgentClient


def create_open_agent_client() -> BaseOpenAgentClient:
    provider = settings.OPEN_AGENT_PROVIDER
    match provider:
        case "http":
            from app.libs.open_agent.providers.http import HTTPOpenAgentClient
            return HTTPOpenAgentClient()
        case _:
            raise ValueError(f"Unsupported OpenAgent provider: {provider}")
