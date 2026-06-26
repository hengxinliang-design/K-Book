"""Tests for K-Book upload batch prevalidation and queue API."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.kbook_errors import add_kbook_exception_handler
from api.kbook_models import (
    KBookUploadBatchFileInput,
    KBookUploadBatchItemInput,
    KBookUploadBatchItemResponse,
    KBookUploadBatchResponse,
)
from api.kbook_services import upload_batches as upload_batches_service
from api.kbook_services.upload_batches import UploadBatchValidationError
from api.routers import kbook_upload_batches
from api.routers.kbook_upload_batches import router


def _record_text(value) -> str:
    return str(value).replace("⟨", "").replace("⟩", "")


def _client() -> TestClient:
    app = FastAPI()
    add_kbook_exception_handler(app)
    app.include_router(router, prefix="/api/kbook")
    return TestClient(app)


def _batch_response():
    return KBookUploadBatchResponse(
        batch_id="upload_batch:1",
        status="queued",
        total=1,
        accepted=1,
        rejected=0,
        items=[
            KBookUploadBatchItemResponse(
                client_file_id="local-1",
                filename="PO_Blueprint_v1.docx",
                status="queued",
            )
        ],
    )


def test_create_upload_batch_route_accepts_json(monkeypatch):
    expected = _batch_response()
    mock_create = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_upload_batches, "create_upload_batch", mock_create)

    response = _client().post(
        "/api/kbook/upload-batches",
        json={
            "notebook_id": "notebook:1",
            "files": [{"filename": "PO_Blueprint_v1.docx"}],
            "items": [
                {
                    "client_file_id": "local-1",
                    "filename": "PO_Blueprint_v1.docx",
                    "title": "采购订单蓝图设计",
                }
            ],
            "async_processing": True,
            "embed": True,
        },
    )

    assert response.status_code == 202
    assert response.json() == expected.model_dump()
    _, kwargs = mock_create.await_args
    assert kwargs["notebook_id"] == "notebook:1"
    assert kwargs["files"][0].filename == "PO_Blueprint_v1.docx"
    assert kwargs["items"][0].client_file_id == "local-1"


def test_get_upload_batch_route_maps_not_found(monkeypatch):
    mock_get = AsyncMock(
        side_effect=UploadBatchValidationError(
            "upload_batch_not_found",
            "Upload batch not found",
            {"batch_id": "upload_batch:missing"},
        )
    )
    monkeypatch.setattr(kbook_upload_batches, "get_upload_batch", mock_get)

    response = _client().get("/api/kbook/upload-batches/upload_batch:missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "upload_batch_not_found"


@pytest.mark.asyncio
async def test_validate_upload_batch_rejects_unsupported_extension(monkeypatch):
    monkeypatch.setattr(
        upload_batches_service,
        "repo_query",
        AsyncMock(return_value=[{"id": "notebook:1"}]),
    )

    with pytest.raises(UploadBatchValidationError) as exc:
        await upload_batches_service.validate_upload_batch(
            "notebook:1",
            [KBookUploadBatchFileInput(filename="script.exe")],
            [
                KBookUploadBatchItemInput(
                    client_file_id="local-1",
                    filename="script.exe",
                    title="脚本",
                )
            ],
        )

    assert exc.value.code == "unsupported_file_type"


@pytest.mark.asyncio
async def test_create_upload_batch_creates_batch_and_queued_items(monkeypatch):
    calls = []

    async def fake_repo_query(query, params=None):
        calls.append((query, params))
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "CREATE upload_batch CONTENT" in query:
            return [{"id": "upload_batch:1"}]
        if "CREATE upload_batch_item CONTENT" in query:
            content = params["content"]
            return [
                {
                    "client_file_id": content["client_file_id"],
                    "filename": content["filename"],
                    "status": content["status"],
                    "source": None,
                    "reference": None,
                    "error": None,
                }
            ]
        return []

    async def fake_validate(item_id, expected_type, require_active=True):
        return {"id": item_id, "dictionary_type": {"code": expected_type}, "status": "active"}

    monkeypatch.setattr(
        upload_batches_service,
        "repo_query",
        AsyncMock(side_effect=fake_repo_query),
    )
    monkeypatch.setattr(
        upload_batches_service,
        "folder_belongs_to_notebook",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(upload_batches_service, "validate_dictionary_item", fake_validate)

    result = await upload_batches_service.create_upload_batch(
        notebook_id="notebook:1",
        files=[KBookUploadBatchFileInput(filename="PO_Blueprint_v1.docx")],
        items=[
            KBookUploadBatchItemInput(
                client_file_id="local-1",
                filename="PO_Blueprint_v1.docx",
                title="采购订单蓝图设计",
                folder_id="folder:1",
                tag_ids=["dictionary_item:blueprint"],
                module_id="dictionary_item:module",
                document_type_id="dictionary_item:doc",
                status_id="dictionary_item:effective",
            )
        ],
    )

    assert result.status == "queued"
    assert result.accepted == 1
    batch_call = [call for call in calls if "CREATE upload_batch CONTENT" in call[0]][0]
    item_call = [call for call in calls if "CREATE upload_batch_item CONTENT" in call[0]][0]
    assert _record_text(batch_call[1]["content"]["notebook"]) == "notebook:1"
    assert item_call[1]["content"]["status"] == "queued"
    assert "source_embedding" not in item_call[0]


@pytest.mark.asyncio
async def test_create_upload_batch_with_saved_files_creates_processing_sources(monkeypatch):
    calls = []
    saved_sources = []

    async def fake_repo_query(query, params=None):
        calls.append((query, params))
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "CREATE upload_batch CONTENT" in query:
            return [{"id": "upload_batch:1"}]
        if "RELATE $source_id->reference->$notebook_id" in query:
            return [{"id": "reference:1"}]
        if "SELECT id FROM source_profile" in query:
            return []
        if "CREATE source_profile CONTENT" in query:
            return [{"id": "source_profile:1"}]
        if "CREATE upload_batch_item CONTENT" in query:
            content = params["content"]
            return [
                {
                    "client_file_id": content["client_file_id"],
                    "filename": content["filename"],
                    "status": content["status"],
                    "source": content["source"],
                    "reference": content["reference"],
                    "error": None,
                }
            ]
        return []

    async def fake_create_source(title, file_path):
        saved_sources.append({"title": title, "file_path": file_path})
        return "source:1"

    monkeypatch.setattr(
        upload_batches_service,
        "_create_source_for_upload",
        fake_create_source,
    )
    monkeypatch.setattr(
        upload_batches_service,
        "repo_query",
        AsyncMock(side_effect=fake_repo_query),
    )

    result = await upload_batches_service.create_upload_batch(
        notebook_id="notebook:1",
        files=[KBookUploadBatchFileInput(filename="ln-blueprint.txt")],
        items=[
            KBookUploadBatchItemInput(
                client_file_id="local-1",
                filename="ln-blueprint.txt",
                title="LN 蓝图",
                business_version="v1",
            )
        ],
        saved_files={"ln-blueprint.txt": "/tmp/ln-blueprint.txt"},
    )

    assert result.status == "processing"
    assert result.items[0].status == "processing"
    assert _record_text(result.items[0].source_id) == "source:1"
    assert _record_text(result.items[0].reference_id) == "reference:1"
    assert saved_sources[0]["title"] == "LN 蓝图"
    assert saved_sources[0]["file_path"] == "/tmp/ln-blueprint.txt"
    item_call = [call for call in calls if "CREATE upload_batch_item CONTENT" in call[0]][0]
    assert item_call[1]["content"]["file_path"] == "/tmp/ln-blueprint.txt"


@pytest.mark.asyncio
async def test_get_upload_batch_summarizes_item_statuses(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "FROM $batch_id" in query:
            return [
                {
                    "id": "upload_batch:1",
                    "status": "processing",
                    "total": 2,
                    "accepted": 2,
                    "rejected": 0,
                }
            ]
        if "FROM upload_batch_item" in query:
            return [
                {
                    "client_file_id": "local-1",
                    "filename": "a.pdf",
                    "status": "ready",
                    "source": "source:1",
                    "reference": "reference:1",
                    "error": None,
                },
                {
                    "client_file_id": "local-2",
                    "filename": "b.pdf",
                    "status": "processing",
                    "source": None,
                    "reference": None,
                    "error": None,
                },
            ]
        return []

    monkeypatch.setattr(
        upload_batches_service,
        "repo_query",
        AsyncMock(side_effect=fake_repo_query),
    )

    result = await upload_batches_service.get_upload_batch("upload_batch:1")

    assert result.status == "processing"
    assert result.ready == 1
    assert result.processing == 1


@pytest.mark.asyncio
async def test_process_upload_batch_marks_item_ready(monkeypatch):
    updates = []

    async def fake_repo_query(query, params=None):
        if "SELECT id, notebook, embed FROM $batch_id" in query:
            return [{"id": "upload_batch:1", "notebook": "notebook:1", "embed": True}]
        if "SELECT id, source, file_path" in query:
            assert "created" in query
            assert "client_file_id" in query
            return [
                {
                    "id": "upload_batch_item:1",
                    "source": "source:1",
                    "file_path": "/tmp/ln-blueprint.txt",
                }
            ]
        if "SELECT status" in query and "FROM upload_batch_item" in query:
            return [{"status": "ready"}]
        if query.strip().startswith("UPDATE"):
            updates.append((query, params))
            return []
        return []

    class FakeEmbedResult:
        success = True
        error_message = None

    async def fake_run_source_graph(payload):
        assert payload["source_id"] == "source:1"
        assert payload["content_state"]["file_path"] == "/tmp/ln-blueprint.txt"
        return {"source": object()}

    async def fake_embed_source(source_id):
        assert source_id == "source:1"
        return FakeEmbedResult()

    monkeypatch.setattr(
        upload_batches_service,
        "repo_query",
        AsyncMock(side_effect=fake_repo_query),
    )
    monkeypatch.setattr(upload_batches_service, "_run_source_graph", fake_run_source_graph)
    monkeypatch.setattr(upload_batches_service, "_embed_source", fake_embed_source)

    await upload_batches_service.process_upload_batch("upload_batch:1")

    assert any("status = 'ready'" in query for query, _ in updates)
    assert any(params.get("status") == "completed" for _, params in updates)
