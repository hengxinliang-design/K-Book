"""Tests for K-Book migration 16 registration and preflight checks."""

import asyncio
from pathlib import Path

import pytest

from open_notebook.database import async_migrate
from open_notebook.database.async_migrate import (
    AsyncMigrationManager,
    validate_migration_16_preconditions,
)


def test_migration_16_is_registered():
    manager = AsyncMigrationManager()

    assert len(manager.up_migrations) == 18
    assert len(manager.down_migrations) == 18
    assert "dictionary_type" in manager.up_migrations[15].sql
    assert "folder" in manager.up_migrations[15].sql
    assert "idx_reference_source_notebook" in manager.up_migrations[15].sql
    assert "REMOVE TABLE IF EXISTS folder" in manager.down_migrations[15].sql
    assert "upload_batch" in manager.up_migrations[16].sql
    assert "upload_batch" in manager.down_migrations[16].sql
    assert "file_path" in manager.up_migrations[17].sql
    assert "file_path" in manager.down_migrations[17].sql


def test_migration_17_sql_contains_upload_batch_schema():
    sql = Path("open_notebook/database/migrations/17.surrealql").read_text()

    assert "DEFINE TABLE IF NOT EXISTS upload_batch SCHEMAFULL" in sql
    assert "DEFINE TABLE IF NOT EXISTS upload_batch_item SCHEMAFULL" in sql
    assert "idx_upload_batch_item_batch_client_file" in sql


def test_migration_17_down_sql_removes_upload_batch_schema():
    sql = Path("open_notebook/database/migrations/17_down.surrealql").read_text()

    assert "REMOVE TABLE IF EXISTS upload_batch_item" in sql
    assert "REMOVE TABLE IF EXISTS upload_batch" in sql


def test_migration_18_sql_contains_upload_batch_processing_metadata():
    sql = Path("open_notebook/database/migrations/18.surrealql").read_text()

    assert "DEFINE FIELD IF NOT EXISTS file_path ON TABLE upload_batch_item" in sql
    assert "DEFINE FIELD IF NOT EXISTS command ON TABLE upload_batch_item" in sql
    assert "idx_upload_batch_item_command" in sql


def test_migration_18_down_sql_removes_upload_batch_processing_metadata():
    sql = Path("open_notebook/database/migrations/18_down.surrealql").read_text()

    assert "REMOVE FIELD IF EXISTS command ON TABLE upload_batch_item" in sql
    assert "REMOVE FIELD IF EXISTS file_path ON TABLE upload_batch_item" in sql


def test_migration_16_sql_contains_expected_kbook_schema():
    sql = Path("open_notebook/database/migrations/16.surrealql").read_text()

    expected_fragments = [
        "DEFINE TABLE IF NOT EXISTS customer SCHEMAFULL",
        "DEFINE TABLE IF NOT EXISTS project SCHEMAFULL",
        "DEFINE TABLE IF NOT EXISTS folder SCHEMAFULL",
        "DEFINE FIELD IF NOT EXISTS folder ON TABLE reference",
        "DEFINE TABLE IF NOT EXISTS dictionary_type SCHEMAFULL",
        "DEFINE TABLE IF NOT EXISTS dictionary_item SCHEMAFULL",
        "DEFINE TABLE IF NOT EXISTS source_profile SCHEMAFULL",
        "DEFINE TABLE IF NOT EXISTS source_tag TYPE RELATION FROM source TO dictionary_item SCHEMAFULL",
        "DEFINE TABLE IF NOT EXISTS notebook_ln_version TYPE RELATION FROM notebook TO dictionary_item SCHEMAFULL",
        "UPSERT dictionary_type:tag",
        "DEFINE EVENT IF NOT EXISTS kbook_source_cleanup",
        "DEFINE EVENT IF NOT EXISTS kbook_notebook_cleanup",
    ]

    for fragment in expected_fragments:
        assert fragment in sql

    assert "source_revision" not in sql
    assert "permission" not in sql


def test_migration_16_down_sql_removes_kbook_schema_after_dependents():
    sql = Path("open_notebook/database/migrations/16_down.surrealql").read_text()

    assert sql.index("REMOVE TABLE IF EXISTS notebook_ln_version") < sql.index(
        "REMOVE TABLE IF EXISTS dictionary_item"
    )
    assert sql.index("REMOVE TABLE IF EXISTS source_tag") < sql.index(
        "REMOVE TABLE IF EXISTS dictionary_item"
    )
    assert "REMOVE FIELD IF EXISTS folder ON TABLE reference" in sql
    assert "REMOVE TABLE IF EXISTS customer" in sql


def test_migration_16_preflight_rejects_duplicate_references(monkeypatch):
    async def fake_repo_query(query, params=None):
        assert query == "SELECT id, in, out FROM reference;"
        return [
            {"id": "reference:1", "in": "source:1", "out": "notebook:1"},
            {"id": "reference:2", "in": "source:1", "out": "notebook:1"},
        ]

    monkeypatch.setattr(async_migrate, "repo_query", fake_repo_query)

    with pytest.raises(RuntimeError, match="duplicate reference"):
        asyncio.run(validate_migration_16_preconditions())


def test_migration_16_preflight_rejects_dangling_references(monkeypatch):
    async def fake_repo_query(query, params=None):
        if query == "SELECT id, in, out FROM reference;":
            return [
                {"id": "reference:1", "in": "source:1", "out": "notebook:1"},
                {"id": "reference:2", "in": "source:missing", "out": "notebook:1"},
            ]

        record_id = str(params["record_id"])
        if record_id in {"source:1", "notebook:1"}:
            return [{"id": record_id}]
        return []

    monkeypatch.setattr(async_migrate, "repo_query", fake_repo_query)

    with pytest.raises(RuntimeError, match="dangling reference"):
        asyncio.run(validate_migration_16_preconditions())


def test_migration_16_preflight_passes_clean_references(monkeypatch):
    async def fake_repo_query(query, params=None):
        if query == "SELECT id, in, out FROM reference;":
            return [
                {"id": "reference:1", "in": "source:1", "out": "notebook:1"},
                {"id": "reference:2", "in": "source:2", "out": "notebook:1"},
            ]

        return [{"id": str(params["record_id"])}]

    monkeypatch.setattr(async_migrate, "repo_query", fake_repo_query)

    asyncio.run(validate_migration_16_preconditions())
