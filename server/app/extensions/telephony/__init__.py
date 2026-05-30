"""Telephony catalog API extension.

Registers ``/api/v1/sip-trunks/*`` and ``/api/v1/phone-numbers/*`` for the
Tenant Platform to persist SIP trunk and phone number inventory in OpenDesk.
"""
from fastapi import FastAPI


def register(app: FastAPI) -> None:
    from .router import phone_numbers_router, sip_trunks_router

    app.include_router(sip_trunks_router, prefix="/api/v1")
    app.include_router(phone_numbers_router, prefix="/api/v1")
