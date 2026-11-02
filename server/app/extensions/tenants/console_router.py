"""Tenant console auth router — login for the built-in /tenant admin UI."""
from fastapi import APIRouter, Depends, Request

from app.core.client_info import get_client_ip
from app.core.tenant_platform_auth import verify_tenant_console_token

from .console_service import TenantConsoleAuthService
from .schemas import (
    TenantConsoleLoginRequest,
    TenantConsoleMeResponse,
    TenantConsoleTokenResponse,
)

router = APIRouter(prefix="/tenant-console/auth", tags=["Tenant Console"])


@router.post("/login", response_model=TenantConsoleTokenResponse)
async def login(body: TenantConsoleLoginRequest, request: Request) -> TenantConsoleTokenResponse:
    return await TenantConsoleAuthService.login(body, get_client_ip(request))


@router.get("/me", response_model=TenantConsoleMeResponse)
async def me(username: str = Depends(verify_tenant_console_token)) -> TenantConsoleMeResponse:
    return TenantConsoleMeResponse(username=username)
