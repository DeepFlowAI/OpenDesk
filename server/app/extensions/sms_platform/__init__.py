"""SMS platform API extension.

Registers ``/api/v1/sms-signatures/*``, ``/api/v1/sms-templates/*`` and
``/api/v1/sms-template-grants/*`` for the Tenant Platform to maintain
OpenDesk SMS signatures/templates and grant them to tenants.
"""
from fastapi import FastAPI


def register(app: FastAPI) -> None:
    from .router import sms_signatures_router, sms_template_grants_router, sms_templates_router

    app.include_router(sms_signatures_router, prefix="/api/v1")
    app.include_router(sms_templates_router, prefix="/api/v1")
    app.include_router(sms_template_grants_router, prefix="/api/v1")
