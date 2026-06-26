"""Tests for K-Book upload configuration API."""

from fastapi.testclient import TestClient

from api.routers.kbook_upload_config import router
from api.kbook_services.upload_config import (
    KBOOK_SUPPORTED_UPLOAD_EXTENSIONS,
    get_upload_accept,
    is_supported_upload_extension,
)


def test_get_kbook_upload_config_returns_supported_formats():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/api/kbook")
    client = TestClient(app)

    response = client.get("/api/kbook/upload/config")

    assert response.status_code == 200
    data = response.json()

    assert data["max_file_size_mb"] == 100
    assert data["max_files_per_batch"] == 50
    assert data["extensions"] == KBOOK_SUPPORTED_UPLOAD_EXTENSIONS
    assert data["accept"] == get_upload_accept()
    assert data["format_summary"] == (
        "PDF、Word、PPT、Excel、文本、Markdown、网页、图片、音视频、压缩包等"
    )


def test_upload_accept_matches_extensions_exactly():
    accept_items = get_upload_accept().split(",")

    assert accept_items == [
        f".{extension}" for extension in KBOOK_SUPPORTED_UPLOAD_EXTENSIONS
    ]
    assert len(accept_items) == len(set(accept_items))


def test_supported_extensions_include_current_frontend_upload_whitelist():
    current_frontend_extensions = {
        "pdf",
        "doc",
        "docx",
        "pptx",
        "ppt",
        "xlsx",
        "xls",
        "txt",
        "md",
        "epub",
        "mp4",
        "avi",
        "mov",
        "wmv",
        "mp3",
        "wav",
        "m4a",
        "aac",
        "jpg",
        "jpeg",
        "png",
        "tiff",
        "zip",
        "tar",
        "gz",
        "html",
    }

    assert current_frontend_extensions.issubset(set(KBOOK_SUPPORTED_UPLOAD_EXTENSIONS))


def test_is_supported_upload_extension_is_case_insensitive():
    assert is_supported_upload_extension("Blueprint.PDF")
    assert is_supported_upload_extension("archive.tar")
    assert not is_supported_upload_extension("script.exe")
    assert not is_supported_upload_extension("no-extension")
