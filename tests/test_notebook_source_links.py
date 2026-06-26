"""Regression tests for notebook/source reference edge direction and idempotency."""

from unittest.mock import AsyncMock, patch

import pytest

from api.routers.notebooks import (
    add_source_to_notebook,
    remove_source_from_notebook,
)


@pytest.mark.asyncio
@patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
@patch("api.routers.notebooks.Source.get", new_callable=AsyncMock)
@patch("api.routers.notebooks.Notebook.get", new_callable=AsyncMock)
async def test_add_source_uses_source_in_notebook_out_and_is_idempotent(
    mock_notebook_get,
    mock_source_get,
    mock_repo_query,
):
    mock_repo_query.return_value = [{"id": "reference:existing"}]

    result = await add_source_to_notebook("notebook:1", "source:1")

    assert result == {"message": "Source linked to notebook successfully"}
    mock_notebook_get.assert_awaited_once_with("notebook:1")
    mock_source_get.assert_awaited_once_with("source:1")
    mock_repo_query.assert_awaited_once()

    query = mock_repo_query.await_args.args[0]
    assert "in = $source_id" in query
    assert "out = $notebook_id" in query
    assert "out = $source_id" not in query


@pytest.mark.asyncio
@patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
@patch("api.routers.notebooks.Source.get", new_callable=AsyncMock)
@patch("api.routers.notebooks.Notebook.get", new_callable=AsyncMock)
async def test_add_source_creates_reference_only_when_missing(
    mock_notebook_get,
    mock_source_get,
    mock_repo_query,
):
    mock_repo_query.side_effect = [[], [{"id": "reference:new"}]]

    result = await add_source_to_notebook("notebook:1", "source:1")

    assert result == {"message": "Source linked to notebook successfully"}
    assert mock_repo_query.await_count == 2
    create_query = mock_repo_query.await_args_list[1].args[0]
    assert "RELATE $source_id->reference->$notebook_id" in create_query


@pytest.mark.asyncio
@patch("api.routers.notebooks.repo_query", new_callable=AsyncMock)
@patch("api.routers.notebooks.Notebook.get", new_callable=AsyncMock)
async def test_remove_source_uses_source_in_notebook_out(
    mock_notebook_get,
    mock_repo_query,
):
    result = await remove_source_from_notebook("notebook:1", "source:1")

    assert result == {"message": "Source removed from notebook successfully"}
    mock_notebook_get.assert_awaited_once_with("notebook:1")
    mock_repo_query.assert_awaited_once()

    query = mock_repo_query.await_args.args[0]
    assert "out = $notebook_id" in query
    assert "in = $source_id" in query
