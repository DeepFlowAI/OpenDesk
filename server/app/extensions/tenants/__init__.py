"""Tenant Platform API extension.

Registers ``/api/v1/tenants/*`` for managing tenants from an external admin
platform. A deployment with an empty tenants table still seeds one default
tenant on startup.
"""
from fastapi import FastAPI


def register(app: FastAPI) -> None:
    from . import router as router_module
    app.include_router(router_module.router, prefix="/api/v1")
