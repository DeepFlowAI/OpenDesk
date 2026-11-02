"""Tenant Platform API extension.

Registers ``/api/v1/tenants/*`` for managing tenants from an external admin
platform or the built-in tenant console, plus ``/api/v1/tenant-console/auth/*``
for console login. A deployment with an empty tenants table still seeds one
default tenant on startup.
"""
from fastapi import FastAPI


def register(app: FastAPI) -> None:
    from . import console_router
    from . import router as router_module
    app.include_router(router_module.router, prefix="/api/v1")
    app.include_router(console_router.router, prefix="/api/v1")
