"""Tests for K-Book source metadata editing API."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.kbook_errors import add_kbook_exception_handler
from api.kbook_models import (
    KBookSourceProfileResponse,
    KBookSourceTagsResponse,
    KBookSourceTitleResponse,
)
from api.kbook_services import source_metadata as source_metadata_service
from api.kbook_services.source_metadata import SourceMetadataValidationError
from api.routers import kbook_source_metadata
from api.routers.kbook_source_metadata import router


def _record_text(value) -> str:
    return str(value).replace("⟨", "").replace("⟩", "")


def _client() -> TestClient:
    app = FastAPI()
    add_kbook_exception_handler(app)
    app.include_router(router, prefix="/api/kbook")
    return TestClient(app)


def test_update_source_title_route(monkeypatch):
    expected = KBookSourceTitleResponse(
        source_id="source:1",
        title="采购订单蓝图设计",
        updated="2026-06-26T12:00:00Z",
    )
    mock_update = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_source_metadata, "update_source_title", mock_update)

    response = _client().patch(
        "/api/kbook/sources/source:1/title",
        json={"title": " 采购订单蓝图设计 "},
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    mock_update.assert_awaited_once_with("source:1", " 采购订单蓝图设计 ")


def test_update_source_profile_route_maps_validation_error(monkeypatch):
    mock_update = AsyncMock(
        side_effect=SourceMetadataValidationError(
            "dictionary_type_mismatch",
            "Dictionary item has wrong type",
            {"item_id": "dictionary_item:bad"},
        )
    )
    monkeypatch.setattr(kbook_source_metadata, "update_source_profile", mock_update)

    response = _client().put(
        "/api/kbook/sources/source:1/profile",
        json={"module_id": "dictionary_item:bad"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "dictionary_type_mismatch"


def test_replace_source_tags_route(monkeypatch):
    expected = KBookSourceTagsResponse(
        source_id="source:1",
        tag_ids=["dictionary_item:blueprint"],
    )
    mock_replace = AsyncMock(return_value=expected)
    monkeypatch.setattr(kbook_source_metadata, "replace_source_tags", mock_replace)

    response = _client().put(
        "/api/kbook/sources/source:1/tags",
        json={"tag_ids": ["dictionary_item:blueprint"]},
    )

    assert response.status_code == 200
    assert response.json() == expected.model_dump()
    mock_replace.assert_awaited_once_with(
        "source:1",
        ["dictionary_item:blueprint"],
    )


@pytest.mark.asyncio
async def test_update_source_title_only_updates_source_title(monkeypatch):
    calls = []

    async def fake_repo_query(query, params=None):
        calls.append((query, params))
        if "SELECT id FROM $source_id" in query:
            return [{"id": "source:1"}]
        if query.strip().startswith("UPDATE $source_id"):
            return [
                {
                    "id": "source:1",
                    "title": params["title"],
                    "updated": "2026-06-26T12:00:00Z",
                }
            ]
        return []

    monkeypatch.setattr(
        source_metadata_service,
        "repo_query",
        AsyncMock(side_effect=fake_repo_query),
    )

    result = await source_metadata_service.update_source_title(
        "source:1",
        " 采购订单蓝图设计 ",
    )

    assert result.title == "采购订单蓝图设计"
    update_call = [call for call in calls if call[0].strip().startswith("UPDATE $source_id")][0]
    assert "title = $title" in update_call[0]
    assert "source_embedding" not in update_call[0]
    assert "source_profile" not in update_call[0]


@pytest.mark.asyncio
async def test_update_source_profile_creates_profile_without_relearning(monkeypatch):
    calls = []

    async def fake_repo_query(query, params=None):
        calls.append((query, params))
        if "SELECT id FROM $source_id" in query:
            return [{"id": "source:1"}]
        if "FROM source_profile" in query:
            return []
        if "CREATE source_profile" in query:
            content = params["content"]
            return [
                {
                    "id": "source_profile:1",
                    "source": content["source"],
                    "module": content["module"],
                    "document_type": content["document_type"],
                    "business_version": content["business_version"],
                    "status": content["status"],
                    "updated": "2026-06-26T12:00:00Z",
                }
            ]
        return []

    async def fake_validate(item_id, expected_type, require_active=True):
        return {"id": item_id, "dictionary_type": {"code": expected_type}, "status": "active"}

    monkeypatch.setattr(
        source_metadata_service,
        "repo_query",
        AsyncMock(side_effect=fake_repo_query),
    )
    monkeypatch.setattr(source_metadata_service, "validate_dictionary_item", fake_validate)

    result = await source_metadata_service.update_source_profile(
        "source:1",
        module_id="dictionary_item:module",
        document_type_id="dictionary_item:doc_type",
        business_version="v1.0",
        status_id="dictionary_item:effective",
    )

    assert result.source_id == "source:1"
    create_call = [call for call in calls if "CREATE source_profile" in call[0]][0]
    assert _record_text(create_call[1]["content"]["module"]) == "dictionary_item:module"
    assert "source_embedding" not in create_call[0]
    assert "command" not in create_call[0]


@pytest.mark.asyncio
async def test_replace_source_tags_validates_all_then_replaces(monkeypatch):
    calls = []

    async def fake_repo_query(query, params=None):
        calls.append((query, params))
        if "SELECT id FROM $source_id" in query:
            return [{"id": "source:1"}]
        return []

    validated = []

    async def fake_validate(item_id, expected_type, require_active=True):
        validated.append((item_id, expected_type, require_active))
        return {"id": item_id, "dictionary_type": {"code": expected_type}, "status": "active"}

    monkeypatch.setattr(
        source_metadata_service,
        "repo_query",
        AsyncMock(side_effect=fake_repo_query),
    )
    monkeypatch.setattr(source_metadata_service, "validate_dictionary_item", fake_validate)

    result = await source_metadata_service.replace_source_tags(
        "source:1",
        ["dictionary_item:blueprint", "dictionary_item:blueprint", "dictionary_item:proc"],
    )

    assert result.tag_ids == ["dictionary_item:blueprint", "dictionary_item:proc"]
    assert validated == [
        ("dictionary_item:blueprint", "tag", True),
        ("dictionary_item:proc", "tag", True),
    ]
    delete_index = next(i for i, call in enumerate(calls) if call[0].strip().startswith("DELETE"))
    relate_indexes = [
        i for i, call in enumerate(calls) if call[0].strip().startswith("RELATE")
    ]
    assert all(delete_index < index for index in relate_indexes)


@pytest.mark.asyncio
async def test_replace_source_tags_does_not_delete_when_validation_fails(monkeypatch):
    calls = []

    async def fake_repo_query(query, params=None):
        calls.append((query, params))
        if "SELECT id FROM $source_id" in query:
            return [{"id": "source:1"}]
        return []

    async def fake_validate(item_id, expected_type, require_active=True):
        raise ValueError("Dictionary item is inactive: dictionary_item:old")

    monkeypatch.setattr(
        source_metadata_service,
        "repo_query",
        AsyncMock(side_effect=fake_repo_query),
    )
    monkeypatch.setattr(source_metadata_service, "validate_dictionary_item", fake_validate)

    with pytest.raises(SourceMetadataValidationError) as exc:
        await source_metadata_service.replace_source_tags(
            "source:1",
            ["dictionary_item:old"],
        )

    assert exc.value.code == "dictionary_item_inactive"
    assert not any(call[0].strip().startswith("DELETE") for call in calls)
