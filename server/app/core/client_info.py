"""Extract client identity fields from an HTTP request for logging."""
from __future__ import annotations

from fastapi import Request

_USER_AGENT_MAX_LEN = 200


def _first_forwarded_ip(value: str | None) -> str | None:
    if not value:
        return None
    first = value.split(",", 1)[0].strip()
    return first or None


def get_client_ip(request: Request) -> str:
    """Best-effort real client IP behind reverse proxies / CDNs."""
    for key in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        ip = _first_forwarded_ip(request.headers.get(key))
        if ip:
            return ip
    if request.client and request.client.host:
        return request.client.host
    return "-"


def get_user_agent(request: Request) -> str:
    """Return a truncated User-Agent suitable for logs."""
    raw = request.headers.get("user-agent")
    if not raw:
        return "-"
    ua = raw.strip()
    if not ua:
        return "-"
    if len(ua) > _USER_AGENT_MAX_LEN:
        return ua[:_USER_AGENT_MAX_LEN]
    return ua
