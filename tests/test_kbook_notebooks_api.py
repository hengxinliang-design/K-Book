"""Tests for K-Book notebook metadata API."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.kbook_errors import add_kbook_exception_handler
from api.kbook_models import KBookNotebookItem, KBookNotebooksResponse
from api.kbook_services import notebooks as notebooks_service
from api.kbook_services.notebooks import NotebookMetadataValidationError
from api.routers import kbook_notebooks
from api.routers.kbook_notebooks import router


def _record_text(value) -> str:
    return str(value).replace("⟨", "").replace("⟩", "")


def _client() -> TestClient:
    app = FastAPI()
    add_kbook_exception_handler(app)
    app.include_router(router, prefix="/api/kbook")
    return TestClient(app)


def _notebook_item(**overrides):
    data = {
        "id": "notebook:1",
        "name": "A 客户 LN 项目知识库",
        "description": "实施项目资料",
        "customer": {"id": "customer:a", "name": "A 客户"},
        "project": {"id": "project:a-ln", "name": "A 客户 LN 实施"},
        "ln_versions": [{"id": "dictionary_item:ln108", "name": "LN 10.8"}],
        "scope": "仅适用于 A 客户 LN 10.8 实施项目",
        "source_count": 12,
        "created": "2026-06-26T12:00:00Z",
        "updated": "2026-06-26T12:00:00Z",
    }
    data.update(overrides)
    return KBookNotebookItem(**data)


def test_list_kbook_notebooks_route(monkeypatch):
    expected = KBookNotebooksResponse(
        items=[_notebook_item()],
        total=1,
        limit=20,
        offset=5,
    )
    mock_list = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_notebooks, "list_kbook_notebooks", mock_list)

    response = _client().get(
        "/api/kbook/notebooks",
        params={"keyword": "LN", "limit": "20", "offset": "5"},
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    mock_list.assert_awaited_once_with(keyword="LN", limit=20, offset=5)


def test_update_kbook_notebook_route_maps_not_found(monkeypatch):
    mock_update = AsyncMock(
        side_effect=NotebookMetadataValidationError(
            "notebook_not_found",
            "Notebook not found",
            {"notebook_id": "notebook:missing"},
        )
    )
    monkeypatch.setattr(kbook_notebooks, "update_kbook_notebook", mock_update)

    response = _client().patch(
        "/api/kbook/notebooks/notebook:missing",
        json={"name": "新名称"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "notebook_not_found"


@pytest.mark.asyncio
async def test_list_kbook_notebooks_maps_metadata_and_counts(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "FROM notebook" in query and "ORDER BY" in query:
            return [
                {
                    "id": "notebook:1",
                    "name": "A 客户 LN 项目知识库",
                    "description": "实施项目资料",
                    "customer": {"id": "customer:a", "name": "A 客户"},
                    "project": {"id": "project:a-ln", "name": "A 客户 LN 实施"},
                    "scope": "仅适用于 A 客户",
                    "created": "2026-06-26T12:00:00Z",
                    "updated": "2026-06-26T12:00:00Z",
                }
            ]
        if "SELECT count() AS total" in query and "FROM notebook" in query:
            return [{"total": 1}]
        if "FROM notebook_ln_version" in query:
            return [{"out": {"id": "dictionary_item:ln108", "name": "LN 10.8"}}]
        if "FROM reference" in query:
            return [{"total": 12}]
        return []

    monkeypatch.setattr(notebooks_service, "repo_query", AsyncMock(side_effect=fake_repo_query))

    result = await notebooks_service.list_kbook_notebooks(keyword="LN", limit=20, offset=5)

    assert result.total == 1
    assert result.items[0].customer.name == "A 客户"
    assert result.items[0].ln_versions[0].name == "LN 10.8"
    assert result.items[0].source_count == 12


@pytest.mark.asyncio
async def test_update_kbook_notebook_rejects_project_customer_mismatch(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if "FROM $customer_id" in query:
            return [{"id": "customer:a", "name": "A 客户"}]
        if "FROM $project_id" in query:
            return [
                {
                    "id": "project:b-ln",
                    "name": "B 客户 LN 实施",
                    "customer": {"id": "customer:b", "name": "B 客户"},
                }
            ]
        return []

    monkeypatch.setattr(notebooks_service, "repo_query", AsyncMock(side_effect=fake_repo_query))

    with pytest.raises(NotebookMetadataValidationError) as exc:
        await notebooks_service.update_kbook_notebook(
            "notebook:1",
            customer_id="customer:a",
            project_id="project:b-ln",
        )

    assert exc.value.code == "validation_failed"
    assert exc.value.details["customer_id"] == "customer:a"


@pytest.mark.asyncio
async def test_update_kbook_notebook_replaces_ln_versions(monkeypatch):
    calls = []

    async def fake_repo_query(query, params=None):
        calls.append((query, params))
        if "SELECT id FROM $record_id" in query:
            return [{"id": "notebook:1"}]
        if query.strip().startswith("UPDATE $notebook_id"):
            return [
                {
                    "id": "notebook:1",
                    "name": params["patch"]["name"],
                    "description": "实施项目资料",
                    "customer": None,
                    "project": None,
                    "scope": params["patch"]["scope"],
                    "updated": "2026-06-26T12:00:00Z",
                }
            ]
        if "FROM notebook_ln_version" in query:
            return [{"out": {"id": "dictionary_item:ln108", "name": "LN 10.8"}}]
        if "FROM reference" in query:
            return [{"total": 0}]
        return []

    async def fake_validate(item_id, expected_type, require_active=True):
        return {"id": item_id, "dictionary_type": {"code": expected_type}, "status": "active"}

    monkeypatch.setattr(notebooks_service, "repo_query", AsyncMock(side_effect=fake_repo_query))
    monkeypatch.setattr(notebooks_service, "validate_dictionary_item", fake_validate)

    result = await notebooks_service.update_kbook_notebook(
        "notebook:1",
        name=" A 客户 LN 项目知识库 ",
        ln_version_ids=["dictionary_item:ln108"],
        scope="仅适用于 A 客户",
    )

    assert result.name == "A 客户 LN 项目知识库"
    delete_call = [call for call in calls if call[0].strip().startswith("DELETE")][0]
    relate_call = [call for call in calls if call[0].strip().startswith("RELATE")][0]
    assert "notebook_ln_version" in delete_call[0]
    assert _record_text(relate_call[1]["ln_version_id"]) == "dictionary_item:ln108"
