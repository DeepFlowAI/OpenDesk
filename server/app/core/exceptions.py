from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class BusinessError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "BUSINESS_ERROR"):
        self.message = message
        self.status_code = status_code
        self.code = code


class NotFoundError(BusinessError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404, code="NOT_FOUND")


class ValidationError(BusinessError):
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status_code=400, code="VALIDATION_ERROR")


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
    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "status": exc.status_code},
        )
