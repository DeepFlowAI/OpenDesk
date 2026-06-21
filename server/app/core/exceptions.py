import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UnauthorizedError)
    async def unauthorized_error_handler(request: Request, exc: UnauthorizedError):
        client_host = request.client.host if request.client else "-"
        logger.warning(
            "Unauthorized request: path=%s reason=%s client=%s",
            request.url.path,
            exc.message,
            client_host,
        )
        body = {"code": exc.code, "message": exc.message, "status": exc.status_code}
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, exc: BusinessError):
        body = {"code": exc.code, "message": exc.message, "status": exc.status_code}
        if exc.details is not None:
            body["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=body)
