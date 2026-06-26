"""Tests for K-Book folder tree and folder write API."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import kbook_folders
from api.routers.kbook_folders import router
from api.kbook_models import KBookFolderResponse, KBookFolderTreeResponse
from api.kbook_services import folders as folders_service
from api.kbook_services.folders import (
    FolderValidationError,
    build_folder_tree,
    normalize_folder_name,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/kbook")
    return TestClient(app)


def test_build_folder_tree_sorts_and_nests_children():
    tree = build_folder_tree(
        [
            {
                "id": "folder:child",
                "parent": "folder:root",
                "name": "差异分析",
                "description": "",
                "sort_order": 20,
            },
            {
                "id": "folder:root",
                "parent": None,
                "name": "需求",
                "description": "",
                "sort_order": 10,
            },
            {
                "id": "folder:blueprint",
                "parent": None,
                "name": "蓝图",
                "description": "",
                "sort_order": 5,
            },
        ],
        {"folder:root": 3, "folder:child": 1},
    )

    assert [node.id for node in tree] == ["folder:blueprint", "folder:root"]
    assert tree[1].source_count == 3
    assert tree[1].children[0].id == "folder:child"
    assert tree[1].children[0].source_count == 1


def test_normalize_folder_name_uses_nfkc_trim_and_casefold():
    assert normalize_folder_name("  Ａbc  ") == "abc"


def test_get_folder_tree_route(monkeypatch):
    expected = KBookFolderTreeResponse(
        notebook_id="notebook:1",
        items=[
            {
                "id": "folder:root",
                "name": "需求",
                "description": "",
                "parent": None,
                "sort_order": 10,
                "source_count": 2,
                "children": [],
            }
        ],
    )
    mock_list = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_folders, "list_folder_tree", mock_list)

    response = _client().get("/api/kbook/notebooks/notebook:1/folders")

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    mock_list.assert_awaited_once_with("notebook:1")


def test_create_folder_route(monkeypatch):
    expected = KBookFolderResponse(
        id="folder:blueprint",
        notebook_id="notebook:1",
        parent=None,
        name="蓝图",
        description="蓝图资料",
        sort_order=10,
        created="2026-06-25T12:00:00Z",
        updated="2026-06-25T12:00:00Z",
    )
    mock_create = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_folders, "create_folder", mock_create)

    response = _client().post(
        "/api/kbook/notebooks/notebook:1/folders",
        json={
            "parent": None,
            "name": "蓝图",
            "description": "蓝图资料",
            "sort_order": 10,
        },
    )

    assert response.status_code == 201
    assert response.json() == expected.model_dump()
    mock_create.assert_awaited_once_with(
        notebook_id="notebook:1",
        parent=None,
        name="蓝图",
        description="蓝图资料",
        sort_order=10,
    )


def test_folder_route_maps_validation_error(monkeypatch):
    mock_create = AsyncMock(
        side_effect=FolderValidationError(
            "validation_failed",
            "Folder name cannot be empty",
            {"field": "name"},
        )
    )
    monkeypatch.setattr(kbook_folders, "create_folder", mock_create)

    response = _client().post(
        "/api/kbook/notebooks/notebook:1/folders",
        json={"name": "   "},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"]["code"] == "validation_failed"
    assert detail["error"]["details"] == {"field": "name"}


def test_delete_folder_route_returns_204(monkeypatch):
    mock_delete = AsyncMock(return_value=None)
    monkeypatch.setattr(kbook_folders, "delete_empty_folder", mock_delete)

    response = _client().delete("/api/kbook/notebooks/notebook:1/folders/folder:1")

    assert response.status_code == 204
    mock_delete.assert_awaited_once_with("notebook:1", "folder:1")


@pytest.mark.asyncio
async def test_list_folder_tree_queries_notebook_folders_and_counts(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "FROM folder" in query:
            return [
                {
                    "id": "folder:root",
                    "notebook": "notebook:1",
                    "parent": None,
                    "name": "需求",
                    "description": "",
                    "sort_order": 10,
                }
            ]
        if "FROM reference" in query:
            return [{"folder": "folder:root", "total": 2}]
        return []

    mock_repo_query = AsyncMock(side_effect=fake_repo_query)
    monkeypatch.setattr(folders_service, "repo_query", mock_repo_query)

    result = await folders_service.list_folder_tree("notebook:1")

    assert result.notebook_id == "notebook:1"
    assert result.items[0].id == "folder:root"
    assert result.items[0].source_count == 2


@pytest.mark.asyncio
async def test_create_folder_rejects_duplicate_sibling(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "SELECT id FROM folder" in query and "normalized_name" in query:
            return [{"id": "folder:existing"}]
        return []

    monkeypatch.setattr(folders_service, "repo_query", AsyncMock(side_effect=fake_repo_query))

    with pytest.raises(FolderValidationError) as exc:
        await folders_service.create_folder(
            notebook_id="notebook:1",
            parent=None,
            name="需求",
        )

    assert exc.value.code == "validation_failed"


@pytest.mark.asyncio
async def test_move_folder_rejects_descendant_cycle(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "FROM $folder_id" in query:
            return [
                {
                    "id": "folder:root",
                    "notebook": "notebook:1",
                    "parent": None,
                    "name": "需求",
                    "normalized_name": "需求",
                    "sort_order": 10,
                }
            ]
        if "WHERE notebook = $notebook_id" in query and "LIMIT 1" in query:
            return [{"id": "folder:child"}]
        if "FROM folder" in query and "ORDER BY" in query:
            return [
                {"id": "folder:root", "parent": None, "name": "需求", "sort_order": 10},
                {
                    "id": "folder:child",
                    "parent": "folder:root",
                    "name": "子目录",
                    "sort_order": 10,
                },
            ]
        return []

    monkeypatch.setattr(folders_service, "repo_query", AsyncMock(side_effect=fake_repo_query))

    with pytest.raises(FolderValidationError) as exc:
        await folders_service.move_folder(
            notebook_id="notebook:1",
            folder_id="folder:root",
            parent="folder:child",
        )

    assert exc.value.code == "folder_cycle"


@pytest.mark.asyncio
async def test_delete_empty_folder_rejects_non_empty_folder(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "FROM $folder_id" in query:
            return [
                {
                    "id": "folder:root",
                    "notebook": "notebook:1",
                    "parent": None,
                    "name": "需求",
                }
            ]
        if "FROM folder WHERE parent" in query:
            return [{"id": "folder:child"}]
        return []

    monkeypatch.setattr(folders_service, "repo_query", AsyncMock(side_effect=fake_repo_query))

    with pytest.raises(FolderValidationError) as exc:
        await folders_service.delete_empty_folder("notebook:1", "folder:root")

    assert exc.value.code == "folder_not_empty"
