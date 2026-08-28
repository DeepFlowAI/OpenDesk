"""
Schemas for tenant Open API calls.
"""

from pydantic import BaseModel

from app.schemas.permission import EffectivePrincipal


class OpenApiContext(BaseModel):
    tenant_id: int
    api_key_id: int
    api_key_name: str
    api_key_version: int
    is_active: bool

    @property
    def actor_name(self) -> str:
        return f"API Key: {self.api_key_name}"


class OpenApiTaskPrincipal(EffectivePrincipal):
    """Tenant-scoped principal used by task services for API Key calls."""

    user_id: None = None
    api_key_id: int
    api_key_name: str

    def has_permission(self, permission: str) -> bool:
        """Open task APIs currently allow every active tenant API Key."""
        return True

    @classmethod
    def from_context(cls, context: OpenApiContext) -> "OpenApiTaskPrincipal":
        return cls(
            tenant_id=context.tenant_id,
            api_key_id=context.api_key_id,
            api_key_name=context.api_key_name,
        )
