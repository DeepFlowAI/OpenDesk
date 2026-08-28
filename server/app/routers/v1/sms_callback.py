"""
Provider delivery-receipt callback for SMS single-send.

The channel (e.g. Aliyun HTTP batch push) posts receipt items here; access is
guarded by a shared token (settings.SMS_CALLBACK_TOKEN) instead of tenant
auth, since the caller is the provider.

Aliyun probes the configured URL with a GET before saving it in the console,
and expects the ``{"code": 0, "msg": "成功"}`` acknowledgement body on both
the probe and the receipt push, so both handlers return it.
"""
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Body, Query

from app.configs.settings import settings
from app.core.exceptions import NotFoundError
from app.services.sms_service import SmsWorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SMS Callback"])

_ALIYUN_ACK = {"code": 0, "msg": "成功"}


def _check_callback_access(provider: str, token: str) -> None:
    expected = settings.SMS_CALLBACK_TOKEN or ""
    if not expected or not hmac.compare_digest(token, expected):
        raise NotFoundError()
    if provider != settings.SMS_PROVIDER:
        raise NotFoundError()


@router.get("/sms/callback/{provider}")
async def sms_delivery_callback_probe(
    provider: str,
    token: str = Query(default=""),
) -> dict:
    """Connectivity probe used by the provider when the URL is saved."""
    _check_callback_access(provider, token)
    return dict(_ALIYUN_ACK)


@router.post("/sms/callback/{provider}")
async def sms_delivery_callback(
    provider: str,
    token: str = Query(default=""),
    payload: list[dict[str, Any]] = Body(default_factory=list),
) -> dict:
    _check_callback_access(provider, token)
    received = await SmsWorkspaceService.handle_delivery_receipts(
        provider=provider, payload=payload
    )
    logger.info("Applied SMS delivery receipts (provider=%s, received=%s)", provider, received)
    return dict(_ALIYUN_ACK)