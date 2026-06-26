"""Tests for K-Book file list and file move API."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.kbook_errors import add_kbook_exception_handler
from api.routers import kbook_files
from api.routers.kbook_files import router
from api.kbook_models import (
    KBookAddExistingSourceResponse,
    KBookFileDetailResponse,
    KBookFileListItem,
    KBookFileListResponse,
    KBookFileProcessingValue,
    KBookRemoveFileResponse,
    KBookSourceSearchResponse,
)
from api.kbook_services import files as files_service
from api.kbook_services.files import FileValidationError, KBookFileFilters


def _record_text(value) -> str:
    return str(value).replace("⟨", "").replace("⟩", "")


def _client() -> TestClient:
    app = FastAPI()
    add_kbook_exception_handler(app)
    app.include_router(router, prefix="/api/kbook")
    return TestClient(app)


def _file_item(**overrides):
    data = {
        "source_id": "source:1",
        "reference_id": "reference:1",
        "title": "采购订单蓝图设计",
        "original_filename": "PO.docx",
        "folder": None,
        "tags": [],
        "profile": {},
        "processing": {"status": "ready", "embedded": True, "error": None},
        "created": "2026-06-25T12:00:00Z",
        "updated": "2026-06-25T12:00:00Z",
    }
    data.update(overrides)
    return KBookFileListItem(**data)


def test_get_files_route_passes_filters(monkeypatch):
    expected = KBookFileListResponse(items=[_file_item()], total=1, limit=20, offset=5)
    mock_list = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_files, "list_notebook_files", mock_list)

    response = _client().get(
        "/api/kbook/notebooks/notebook:1/files",
        params=[
            ("folder_id", "folder:1"),
            ("tag_ids", "dictionary_item:tag1"),
            ("tag_ids", "dictionary_item:tag2"),
            ("module_id", "dictionary_item:module"),
            ("document_type_id", "dictionary_item:type"),
            ("status_id", "dictionary_item:status"),
            ("business_version", "v1"),
            ("keyword", "采购"),
            ("processing_status", "ready"),
            ("sort_by", "title"),
            ("sort_order", "asc"),
            ("limit", "20"),
            ("offset", "5"),
        ],
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    _, kwargs = mock_list.await_args
    filters = kwargs["filters"]
    assert kwargs["notebook_id"] == "notebook:1"
    assert filters.folder_id == "folder:1"
    assert filters.tag_ids == ["dictionary_item:tag1", "dictionary_item:tag2"]
    assert filters.keyword == "采购"
    assert kwargs["sort_by"] == "title"
    assert kwargs["sort_order"] == "asc"
    assert kwargs["limit"] == 20
    assert kwargs["offset"] == 5


def test_get_file_detail_route(monkeypatch):
    expected = KBookFileDetailResponse(
        **_file_item().model_dump(),
        shared_notebook_count=2,
        global_metadata_warning=True,
        full_text_available=True,
    )
    mock_detail = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_files, "get_notebook_file_detail", mock_detail)

    response = _client().get("/api/kbook/notebooks/notebook:1/files/source:1")

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    mock_detail.assert_awaited_once_with("notebook:1", "source:1")


def test_move_file_route(monkeypatch):
    expected = KBookFileDetailResponse(
        **_file_item().model_dump(),
        shared_notebook_count=1,
        global_metadata_warning=False,
        full_text_available=False,
    )
    mock_move = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_files, "move_file_to_folder", mock_move)

    response = _client().patch(
        "/api/kbook/notebooks/notebook:1/files/source:1/folder",
        json={"folder_id": "folder:1"},
    )

    assert response.status_code == 200
    mock_move.assert_awaited_once_with(
        notebook_id="notebook:1",
        source_id="source:1",
        folder_id="folder:1",
    )


def test_remove_file_route(monkeypatch):
    expected = KBookRemoveFileResponse(
        notebook_id="notebook:1",
        source_id="source:1",
        removed=True,
    )
    mock_remove = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_files, "remove_file_from_notebook", mock_remove)

    response = _client().delete("/api/kbook/notebooks/notebook:1/files/source:1")

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    mock_remove.assert_awaited_once_with("notebook:1", "source:1")


def test_add_existing_source_route(monkeypatch):
    expected = KBookAddExistingSourceResponse(
        source_id="source:1",
        reference_id="reference:1",
        notebook_id="notebook:1",
        folder_id="folder:1",
        already_exists=False,
    )
    mock_add = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_files, "add_existing_source_to_notebook", mock_add)

    response = _client().post(
        "/api/kbook/notebooks/notebook:1/files",
        json={"source_id": "source:1", "folder_id": "folder:1"},
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    mock_add.assert_awaited_once_with(
        notebook_id="notebook:1",
        source_id="source:1",
        folder_id="folder:1",
    )


def test_search_existing_sources_route(monkeypatch):
    expected = KBookSourceSearchResponse(
        items=[],
        total=0,
        limit=20,
        offset=5,
    )
    mock_search = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_files, "search_existing_sources", mock_search)

    response = _client().get(
        "/api/kbook/sources/search",
        params={
            "keyword": "采购",
            "exclude_notebook_id": "notebook:1",
            "limit": "20",
            "offset": "5",
        },
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    mock_search.assert_awaited_once_with(
        keyword="采购",
        exclude_notebook_id="notebook:1",
        limit=20,
        offset=5,
    )


def test_file_route_maps_not_found(monkeypatch):
    mock_detail = AsyncMock(
        side_effect=FileValidationError(
            "source_not_found",
            "Source is not linked to notebook",
            {"source_id": "source:1"},
        )
    )
    monkeypatch.setattr(kbook_files, "get_notebook_file_detail", mock_detail)

    response = _client().get("/api/kbook/notebooks/notebook:1/files/source:1")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "source_not_found"


def test_matches_filters_supports_tags_profile_keyword_and_root():
    item = _file_item(
        title="采购订单蓝图设计",
        folder=None,
        tags=[{"id": "dictionary_item:blueprint", "name": "蓝图"}],
        profile={
            "module": {"id": "dictionary_item:procurement", "name": "采购"},
            "document_type": {"id": "dictionary_item:solution", "name": "方案设计"},
            "business_version": "v1.0",
            "status": {"id": "dictionary_item:effective", "name": "有效"},
        },
    )
    filters = KBookFileFilters(
        folder_id="root",
        tag_ids=["dictionary_item:blueprint"],
        module_id="dictionary_item:procurement",
        document_type_id="dictionary_item:solution",
        status_id="dictionary_item:effective",
        business_version="V1",
        keyword="采购",
        processing_status="ready",
    )

    assert files_service._matches_filters(item, filters)


def test_sort_items_rejects_invalid_sort_field():
    with pytest.raises(FileValidationError) as exc:
        files_service._sort_items([_file_item()], "status", "asc")

    assert exc.value.code == "validation_failed"


@pytest.mark.asyncio
async def test_list_notebook_files_filters_and_paginates(monkeypatch):
    references = [
        {
            "id": "reference:1",
            "folder": None,
            "in": {
                "id": "source:1",
                "title": "采购订单蓝图设计",
                "created": "2026-06-25T12:00:00Z",
                "updated": "2026-06-25T12:00:00Z",
                "full_text": "text",
            },
        },
        {
            "id": "reference:2",
            "folder": None,
            "in": {
                "id": "source:2",
                "title": "销售订单技术设计",
                "created": "2026-06-25T12:00:00Z",
                "updated": "2026-06-25T13:00:00Z",
            },
        },
    ]

    async def fake_repo_query(query, params=None):
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "FROM folder" in query:
            return []
        if "FROM reference" in query and "ORDER BY updated" in query:
            return references
        if "FROM source_profile" in query:
            source_id = _record_text(params["source_id"])
            if "source:1" in source_id:
                return [
                    {
                        "original_filename": "PO.docx",
                        "module": {"id": "dictionary_item:procurement", "name": "采购"},
                        "document_type": None,
                        "business_version": "v1.0",
                        "status": None,
                    }
                ]
            return []
        if "FROM source_tag" in query:
            source_id = _record_text(params["source_id"])
            if "source:1" in source_id:
                return [
                    {
                        "out": {
                            "id": "dictionary_item:blueprint",
                            "name": "蓝图",
                        }
                    }
                ]
            return []
        if "FROM source_embedding" in query:
            source_id = _record_text(params["source_id"])
            return [{"id": "source_embedding:1"}] if "source:1" in source_id else []
        return []

    monkeypatch.setattr(files_service, "repo_query", AsyncMock(side_effect=fake_repo_query))

    result = await files_service.list_notebook_files(
        "notebook:1",
        filters=KBookFileFilters(
            tag_ids=["dictionary_item:blueprint"],
            keyword="采购",
        ),
        limit=10,
        offset=0,
    )

    assert result.total == 1
    assert result.items[0].source_id == "source:1"
    assert result.items[0].original_filename == "PO.docx"
    assert result.items[0].processing == KBookFileProcessingValue(
        status="ready", embedded=True, error=None
    )


@pytest.mark.asyncio
async def test_get_notebook_file_detail_returns_shared_count(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "WHERE out = $notebook_id AND in = $source_id" in query:
            return [
                {
                    "id": "reference:1",
                    "folder": None,
                    "in": {
                        "id": "source:1",
                        "title": "采购订单蓝图设计",
                        "full_text": "content",
                    },
                }
            ]
        if "FROM folder" in query:
            return []
        if "FROM source_profile" in query or "FROM source_tag" in query:
            return []
        if "FROM source_embedding" in query:
            return []
        if "SELECT count() AS total FROM reference WHERE in" in query:
            return [{"total": 2}]
        return []

    monkeypatch.setattr(files_service, "repo_query", AsyncMock(side_effect=fake_repo_query))

    detail = await files_service.get_notebook_file_detail("notebook:1", "source:1")

    assert detail.source_id == "source:1"
    assert detail.shared_notebook_count == 2
    assert detail.global_metadata_warning is True
    assert detail.full_text_available is True


@pytest.mark.asyncio
async def test_move_file_to_folder_updates_reference_only(monkeypatch):
    calls = []

    async def fake_repo_query(query, params=None):
        calls.append((query, params))
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "SELECT id FROM $folder_id" in query:
            return [{"id": "folder:1"}]
        if "SELECT id FROM reference" in query:
            return [{"id": "reference:1"}]
        if query.strip().startswith("UPDATE $reference_id"):
            return [{"id": "reference:1"}]
        return []

    monkeypatch.setattr(files_service, "repo_query", AsyncMock(side_effect=fake_repo_query))
    monkeypatch.setattr(files_service, "folder_belongs_to_notebook", AsyncMock(return_value=True))
    monkeypatch.setattr(
        files_service,
        "get_notebook_file_detail",
        AsyncMock(
            return_value=KBookFileDetailResponse(
                **_file_item().model_dump(),
                shared_notebook_count=1,
                global_metadata_warning=False,
                full_text_available=False,
            )
        ),
    )

    await files_service.move_file_to_folder("notebook:1", "source:1", "folder:1")

    update_call = [call for call in calls if call[0].strip().startswith("UPDATE $reference_id")][0]
    assert "folder = $folder_id" in update_call[0]
    assert "source_profile" not in update_call[0]
    assert "source_tag" not in update_call[0]
    assert _record_text(update_call[1]["folder_id"]) == "folder:1"


@pytest.mark.asyncio
async def test_remove_file_from_notebook_deletes_reference_only(monkeypatch):
    calls = []

    async def fake_repo_query(query, params=None):
        calls.append((query, params))
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "FROM reference" in query and "LIMIT 1" in query:
            return [{"id": "reference:1"}]
        if query.strip().startswith("DELETE $reference_id"):
            return []
        return []

    monkeypatch.setattr(files_service, "repo_query", AsyncMock(side_effect=fake_repo_query))

    result = await files_service.remove_file_from_notebook("notebook:1", "source:1")

    assert result.removed is True
    delete_call = [call for call in calls if call[0].strip().startswith("DELETE $reference_id")][0]
    assert "source " not in delete_call[0]
    assert "source_profile" not in delete_call[0]


@pytest.mark.asyncio
async def test_add_existing_source_is_idempotent_when_reference_exists(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "SELECT id FROM $record_id" in query:
            return [{"id": _record_text(params["record_id"])}]
        if "FROM reference" in query and "LIMIT 1" in query:
            return [{"id": "reference:1", "folder": "folder:1"}]
        return []

    monkeypatch.setattr(files_service, "repo_query", AsyncMock(side_effect=fake_repo_query))
    monkeypatch.setattr(files_service, "folder_belongs_to_notebook", AsyncMock(return_value=True))

    result = await files_service.add_existing_source_to_notebook(
        "notebook:1",
        "source:1",
        "folder:1",
    )

    assert result.already_exists is True
    assert result.reference_id == "reference:1"


@pytest.mark.asyncio
async def test_add_existing_source_creates_reference_with_folder(monkeypatch):
    calls = []

    async def fake_repo_query(query, params=None):
        calls.append((query, params))
        if "SELECT id FROM $record_id" in query:
            return [{"id": _record_text(params["record_id"])}]
        if "FROM reference" in query and "LIMIT 1" in query:
            return []
        if query.strip().startswith("RELATE"):
            return [{"id": "reference:1"}]
        return []

    monkeypatch.setattr(files_service, "repo_query", AsyncMock(side_effect=fake_repo_query))
    monkeypatch.setattr(files_service, "folder_belongs_to_notebook", AsyncMock(return_value=True))

    result = await files_service.add_existing_source_to_notebook(
        "notebook:1",
        "source:1",
        "folder:1",
    )

    assert result.already_exists is False
    relate_call = [call for call in calls if call[0].strip().startswith("RELATE")][0]
    assert "folder = $folder_id" in relate_call[0]
    assert _record_text(relate_call[1]["folder_id"]) == "folder:1"


@pytest.mark.asyncio
async def test_search_existing_sources_excludes_notebook_sources(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "FROM source" in query:
            return [
                {"id": "source:1", "title": "采购订单蓝图"},
                {"id": "source:2", "title": "销售订单蓝图"},
            ]
        if "FROM reference" in query and "LIMIT 1" in query:
            source_id = _record_text(params["source_id"])
            return [{"id": "reference:1"}] if source_id == "source:1" else []
        if "FROM source_profile" in query or "FROM source_tag" in query:
            return []
        if "SELECT count() AS total FROM reference WHERE in" in query:
            return [{"total": 0}]
        return []

    monkeypatch.setattr(files_service, "repo_query", AsyncMock(side_effect=fake_repo_query))

    result = await files_service.search_existing_sources(
        keyword="订单",
        exclude_notebook_id="notebook:1",
    )

    assert result.total == 1
    assert result.items[0].source_id == "source:2"
