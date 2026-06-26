"""Tests for shared K-Book API error helpers."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.kbook_errors import (
    KBookHTTPException,
    add_kbook_exception_handler,
    kbook_error_body,
    kbook_http_error,
)


def test_kbook_error_body_uses_top_level_error_shape():
    exc = KBookHTTPException(
        status_code=400,
        code="validation_failed",
        message="Invalid request",
        details={"field": "name"},
    )

    assert kbook_error_body(exc) == {
        "error": {
            "code": "validation_failed",
            "message": "Invalid request",
            "details": {"field": "name"},
        }
    }


def test_kbook_exception_handler_renders_without_detail_wrapper():
    app = FastAPI()
    add_kbook_exception_handler(app)

    @app.get("/boom")
    async def boom():
        raise KBookHTTPException(
            status_code=404,
            code="folder_not_found",
            message="Folder not found",
            details={"folder_id": "folder:1"},
        )

    response = TestClient(app).get("/boom")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "folder_not_found",
            "message": "Folder not found",
            "details": {"folder_id": "folder:1"},
        }
    }


def test_kbook_http_error_maps_service_code_and_status():
    class ServiceError(ValueError):
        code = "source_not_found"
        details = {"source_id": "source:1"}

    exc = kbook_http_error(
        ServiceError("Source not found"),
        not_found_codes={"source_not_found"},
    )

    assert exc.status_code == 404
    assert exc.code == "source_not_found"
    assert exc.details == {"source_id": "source:1"}
