"""Shared K-Book API error helpers."""

from collections.abc import Iterable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class KBookHTTPException(Exception):
    """Exception rendered as the standard K-Book API error response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def kbook_error_body(exc: KBookHTTPException) -> dict[str, Any]:
    """Return the standard K-Book error response body."""
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        }
    }


async def kbook_exception_handler(
    request: Request,
    exc: KBookHTTPException,
) -> JSONResponse:
    """Render KBookHTTPException without FastAPI's default detail wrapper."""
    return JSONResponse(status_code=exc.status_code, content=kbook_error_body(exc))


def add_kbook_exception_handler(app: FastAPI) -> None:
    """Register the K-Book exception handler on a FastAPI app."""
    app.add_exception_handler(KBookHTTPException, kbook_exception_handler)


def kbook_http_error(
    exc: Exception,
    *,
    default_code: str = "validation_failed",
    details: dict[str, Any] | None = None,
    not_found_codes: Iterable[str] = (),
) -> KBookHTTPException:
    """Map a service-layer exception to the standard K-Book HTTP exception."""
    code = str(getattr(exc, "code", default_code))
    error_details = getattr(exc, "details", details or {})
    status_code = 404 if code in set(not_found_codes) else 400
    return KBookHTTPException(
        status_code=status_code,
        code=code,
        message=str(exc),
        details=error_details,
    )
