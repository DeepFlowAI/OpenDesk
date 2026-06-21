"""
Schemas for tenant Open API calls.
"""

from pydantic import BaseModel


class OpenApiContext(BaseModel):
    tenant_id: int
    api_key_id: int
    api_key_name: str
    api_key_version: int
    is_active: bool

    @property
    def actor_name(self) -> str:
        return f"API Key: {self.api_key_name}"
