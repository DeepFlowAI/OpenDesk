import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.client_info import get_client_ip, get_user_agent
from app.core.security import decode_token_claims_unverified

logger = logging.getLogger(__name__)


class BusinessError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "BUSINESS_ERROR",
        details: dict | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details


class NotFoundError(BusinessError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404, code="NOT_FOUND")


class ValidationError(BusinessError):
    def __init__(self, message: str = "Validation failed", details: dict | None = None):
        super().__init__(message, status_code=400, code="VALIDATION_ERROR", details=details)


class UnauthorizedError(BusinessError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, status_code=401, code="UNAUTHORIZED")


class SessionReplacedError(UnauthorizedError):
    def __init__(self, message: str = "Session replaced"):
        BusinessError.__init__(self, message, status_code=401, code="SESSION_REPLACED")


class ForbiddenError(BusinessError):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, status_code=403, code="FORBIDDEN")


class RateLimitedError(BusinessError):
    def __init__(self, message: str = "Too many requests"):
        super().__init__(message, status_code=429, code="RATE_LIMITED")


class ConflictError(BusinessError):
    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message, status_code=409, code="CONFLICT")


class InvalidCodeError(BusinessError):
    def __init__(self, message: str = "Invalid or expired code"):
        super().__init__(message, status_code=400, code="INVALID_CODE")


class NotImplementedApiError(BusinessError):
    """The requested operation isn't supported by the current backend.

    Returned when a call-control action depends on a media-kernel capability
    that isn't wired up yet, so callers get a clear 501 instead of a silent
    no-op or a misleading success.
    """

    def __init__(self, message: str = "Operation not supported"):
        super().__init__(message, status_code=501, code="NOT_IMPLEMENTED")


def _short_session_id(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    if not text:
        return "-"
    return text[:8]


def _token_expired_for_s(claims: dict | None) -> str:
    if not claims:
        return "-"
    exp = claims.get("exp")
    if exp is None:
        return "-"
    try:
        exp_ts = int(exp)
    except (TypeError, ValueError):
        return "-"
    now_ts = int(datetime.now(timezone.utc).timestamp())
    delta = now_ts - exp_ts
    if delta <= 0:
        return "-"
    return str(delta)


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if not auth:
        return None
    prefix = "Bearer "
    if not auth.startswith(prefix):
        return None
    token = auth[len(prefix) :].strip()
    return token or None


def _log_unauthorized(request: Request, exc: UnauthorizedError) -> None:
    """Best-effort 401 diagnostics; must never raise into the response path."""
    try:
        token = _bearer_token(request)
        claims = decode_token_claims_unverified(token) if token else None
        user_id = "-"
        tenant_id = "-"
        session_id = "-"
        if claims:
            user_id = str(claims.get("sub") or claims.get("user_id") or "-")
            tenant_id = str(claims.get("tenant_id") or "-")
            session_id = _short_session_id(claims.get("session_id"))
        token_expired_for_s = _token_expired_for_s(claims)
        client_ip = get_client_ip(request)
        user_agent = get_user_agent(request)
        extra = {
            "error_code": exc.code,
            "request_path": request.url.path,
            "http_method": request.method,
            "reason": exc.message,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "token_expired_for_s": token_expired_for_s,
            "client_ip": client_ip,
            "user_agent": user_agent,
        }
        logger.warning(
            "Unauthorized request: error_code=%s method=%s request_path=%s "
            "reason=%s user_id=%s tenant_id=%s session_id=%s "
            "token_expired_for_s=%s client_ip=%s user_agent=%s",
            exc.code,
            request.method,
            request.url.path,
            exc.message,
            user_id,
            tenant_id,
            session_id,
            token_expired_for_s,
            client_ip,
            user_agent,
            extra=extra,
        )
    except Exception:
        logger.warning(
            "Unauthorized request: error_code=%s request_path=%s reason=%s",
            getattr(exc, "code", "UNAUTHORIZED"),
            getattr(request.url, "path", "-"),
            getattr(exc, "message", "Unauthorized"),
            exc_info=True,
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UnauthorizedError)
    async def unauthorized_error_handler(request: Request, exc: UnauthorizedError):
        _log_unauthorized(request, exc)
        body = {"code": exc.code, "message": exc.message, "status": exc.status_code}
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, exc: BusinessError):
        body = {"code": exc.code, "message": exc.message, "status": exc.status_code}
        if exc.details is not None:
            body["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Unhandled exceptions would otherwise only be printed by uvicorn's own
        # stdout handler, which does not propagate to the root logger (and thus
        # never reaches the remote log backend). Log the full traceback through
        # the app logger so every 500 is captured with its trace_id.
        logger.error(
            "Unhandled server error: method=%s path=%s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        body = {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "Internal server error",
            "status": 500,
        }
        return JSONResponse(status_code=500, content=body)
