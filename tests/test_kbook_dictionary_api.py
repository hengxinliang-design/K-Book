"""Tests for K-Book dictionary query API and service."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.kbook_errors import add_kbook_exception_handler
from api.routers import kbook_dictionary
from api.routers.kbook_dictionary import router
from api.kbook_models import KBookDictionaryItemsResponse, KBookDictionaryTypesResponse
from api.kbook_services import dictionary as dictionary_service


def _client() -> TestClient:
    app = FastAPI()
    add_kbook_exception_handler(app)
    app.include_router(router, prefix="/api/kbook")
    return TestClient(app)


def test_get_dictionary_types_route(monkeypatch):
    expected = KBookDictionaryTypesResponse(
        items=[
            {
                "id": "dictionary_type:tag",
                "code": "tag",
                "name": "标签",
                "system": True,
                "description": "文件标签",
            }
        ]
    )
    mock_list = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_dictionary, "list_dictionary_types", mock_list)

    response = _client().get("/api/kbook/dictionary-types")

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    mock_list.assert_awaited_once_with()


def test_get_dictionary_items_route_passes_filters(monkeypatch):
    expected = KBookDictionaryItemsResponse(
        items=[
            {
                "id": "dictionary_item:blueprint",
                "type": "tag",
                "code": "BLUEPRINT",
                "name": "蓝图",
                "status": "active",
                "description": "蓝图资料",
                "sort_order": 10,
                "color": None,
            }
        ],
        total=1,
        limit=20,
        offset=5,
    )
    mock_list = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_dictionary, "list_dictionary_items", mock_list)

    response = _client().get(
        "/api/kbook/dictionary-items",
        params={
            "type": "tag",
            "active_only": "true",
            "keyword": "蓝图",
            "limit": "20",
            "offset": "5",
        },
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    mock_list.assert_awaited_once_with(
        type="tag",
        active_only=True,
        keyword="蓝图",
        limit=20,
        offset=5,
    )


def test_get_dictionary_items_route_returns_400_for_unknown_type(monkeypatch):
    mock_list = AsyncMock(side_effect=ValueError("Unknown dictionary type: bad"))
    monkeypatch.setattr(kbook_dictionary, "list_dictionary_items", mock_list)

    response = _client().get("/api/kbook/dictionary-items?type=bad")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"] == {"type": "bad"}


@pytest.mark.asyncio
async def test_list_dictionary_types_maps_rows(monkeypatch):
    mock_repo_query = AsyncMock(
        return_value=[
            {
                "id": "dictionary_type:tag",
                "code": "tag",
                "name": "标签",
                "system": True,
                "description": "文件标签",
            }
        ]
    )
    monkeypatch.setattr(dictionary_service, "repo_query", mock_repo_query)

    result = await dictionary_service.list_dictionary_types()

    assert result.items[0].id == "dictionary_type:tag"
    assert result.items[0].code == "tag"
    assert result.items[0].system is True
    query = mock_repo_query.await_args.args[0]
    assert "FROM dictionary_type" in query
    assert "ORDER BY system DESC, name ASC, code ASC" in query


@pytest.mark.asyncio
async def test_list_dictionary_items_filters_by_type_status_and_keyword(monkeypatch):
    async def fake_repo_query(query, params=None):
        if "FROM dictionary_type" in query:
            return [{"id": "dictionary_type:tag", "code": "tag", "name": "标签"}]
        if "SELECT count() AS total" in query:
            return [{"total": 1}]
        return [
            {
                "id": "dictionary_item:blueprint",
                "dictionary_type": {"id": "dictionary_type:tag", "code": "tag"},
                "code": "BLUEPRINT",
                "name": "蓝图",
                "status": "active",
                "description": "蓝图资料",
                "sort_order": 10,
                "color": None,
            }
        ]

    mock_repo_query = AsyncMock(side_effect=fake_repo_query)
    monkeypatch.setattr(dictionary_service, "repo_query", mock_repo_query)

    result = await dictionary_service.list_dictionary_items(
        type="tag",
        active_only=True,
        keyword="蓝图",
        limit=20,
        offset=5,
    )

    assert result.total == 1
    assert result.limit == 20
    assert result.offset == 5
    assert result.items[0].type == "tag"
    assert result.items[0].code == "BLUEPRINT"

    item_query = mock_repo_query.await_args_list[1].args[0]
    params = mock_repo_query.await_args_list[1].args[1]
    assert "dictionary_type = $dictionary_type" in item_query
    assert "status = 'active'" in item_query
    assert "string::lowercase(name) CONTAINS string::lowercase($keyword)" in item_query
    assert "ORDER BY sort_order ASC, name ASC, code ASC" in item_query
    assert params["keyword"] == "蓝图"
    assert params["limit"] == 20
    assert params["offset"] == 5


@pytest.mark.asyncio
async def test_list_dictionary_items_rejects_unknown_type(monkeypatch):
    mock_repo_query = AsyncMock(return_value=[])
    monkeypatch.setattr(dictionary_service, "repo_query", mock_repo_query)

    with pytest.raises(ValueError, match="Unknown dictionary type"):
        await dictionary_service.list_dictionary_items(type="bad")


@pytest.mark.asyncio
async def test_validate_dictionary_item_checks_type_and_active(monkeypatch):
    mock_repo_query = AsyncMock(
        return_value=[
            {
                "id": "dictionary_item:blueprint",
                "dictionary_type": {"id": "dictionary_type:tag", "code": "tag"},
                "code": "BLUEPRINT",
                "name": "蓝图",
                "status": "active",
            }
        ]
    )
    monkeypatch.setattr(dictionary_service, "repo_query", mock_repo_query)

    item = await dictionary_service.validate_dictionary_item(
        "dictionary_item:blueprint",
        expected_type="tag",
    )

    assert item["code"] == "BLUEPRINT"
    query = mock_repo_query.await_args.args[0]
    assert "FROM $item_id" in query
