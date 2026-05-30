"""
Telephony client factory — returns a singleton instance configured via
settings.TELEPHONY_PROVIDER.

Service-layer code (orchestrator, agent API) only ever depends on the
abstract `BaseTelephonyClient`. Adding a new provider is just:
  1. Implement `providers/<name>/client.py` extending the base.
  2. Add a `case "<name>"` here.
No business-logic changes required.
"""
from __future__ import annotations

from app.configs.settings import settings
from app.libs.telephony.base import BaseTelephonyClient


_instance: BaseTelephonyClient | None = None


def get_telephony_client() -> BaseTelephonyClient:
    global _instance
    if _instance is not None:
        return _instance

    provider = settings.TELEPHONY_PROVIDER
    match provider:
        case "flowkit":
            if not settings.TELEPHONY_WS_URL:
                raise ValueError(
                    "TELEPHONY_PROVIDER=flowkit but TELEPHONY_WS_URL is empty. "
                    "Set the FlowKit kernel WebSocket URL in your env file "
                    "(e.g. TELEPHONY_WS_URL=ws://<kernel-host>:<port>/ws)."
                )
            from app.libs.telephony.providers.flowkit.client import FlowKitTelephonyClient
            _instance = FlowKitTelephonyClient(
                ws_url=settings.TELEPHONY_WS_URL,
                sdk_name=settings.TELEPHONY_SDK_NAME,
                sdk_version=settings.TELEPHONY_SDK_VERSION,
                rpc_timeout=settings.TELEPHONY_RPC_TIMEOUT,
            )
        case "mock":
            from app.libs.telephony.providers.mock.client import MockTelephonyClient
            _instance = MockTelephonyClient()
        case _:
            raise ValueError(f"Unsupported telephony provider: {provider}")
    return _instance


def reset_telephony_client() -> None:
    """Test helper — clears the singleton so a new provider can be installed."""

    global _instance
    _instance = None
