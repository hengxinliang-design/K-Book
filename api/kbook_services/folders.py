"""Folder service for K-Book notebook file organization."""

import unicodedata
from typing import Any

from api.kbook_models import (
    KBookFolderNode,
    KBookFolderResponse,
    KBookFolderTreeResponse,
)
from open_notebook.database.repository import ensure_record_id, repo_query

MAX_FOLDER_DEPTH = 20


class FolderValidationError(ValueError):
    """Raised when a folder operation violates a K-Book business rule."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def normalize_folder_name(name: str) -> str:
    """Normalize folder names for sibling uniqueness checks."""
    return unicodedata.normalize("NFKC", name.strip()).casefold()


def _clean_folder_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise FolderValidationError(
            "validation_failed",
            "Folder name cannot be empty",
            {"field": "name"},
        )
    return cleaned


def _folder_response_from_row(row: dict[str, Any]) -> KBookFolderResponse:
    return KBookFolderResponse(
        id=str(row.get("id", "")),
        notebook_id=str(row.get("notebook", "")),
        parent=str(row["parent"]) if row.get("parent") else None,
        name=row.get("name", ""),
        description=row.get("description"),
        sort_order=row.get("sort_order", 0) or 0,
        created=str(row["created"]) if row.get("created") else None,
        updated=str(row["updated"]) if row.get("updated") else None,
    )


def build_folder_tree(
    flat_rows: list[dict[str, Any]],
    source_counts: dict[str, int] | None = None,
) -> list[KBookFolderNode]:
    """Build a folder tree from flat folder rows."""
    source_counts = source_counts or {}
    nodes: dict[str, KBookFolderNode] = {}
    roots: list[KBookFolderNode] = []

    for row in flat_rows:
        folder_id = str(row.get("id", ""))
        nodes[folder_id] = KBookFolderNode(
            id=folder_id,
            name=row.get("name", ""),
            description=row.get("description"),
            parent=str(row["parent"]) if row.get("parent") else None,
            sort_order=row.get("sort_order", 0) or 0,
            source_count=source_counts.get(folder_id, 0),
        )

    for node in nodes.values():
        if node.parent and node.parent in nodes:
            nodes[node.parent].children.append(node)
        else:
            roots.append(node)

    def sort_nodes(items: list[KBookFolderNode]) -> None:
        items.sort(key=lambda item: (item.sort_order, item.name.casefold(), item.id))
        for item in items:
            sort_nodes(item.children)

    sort_nodes(roots)
    return roots


async def _record_exists(record_id: str) -> bool:
    rows = await repo_query(
        "SELECT id FROM $record_id LIMIT 1",
        {"record_id": ensure_record_id(record_id)},
    )
    return bool(rows)


async def _get_folder(folder_id: str) -> dict[str, Any]:
    rows = await repo_query(
        """
        SELECT id, notebook, parent, name, normalized_name, description,
               sort_order, created, updated
        FROM $folder_id
        LIMIT 1
        """,
        {"folder_id": ensure_record_id(folder_id)},
    )
    if not rows:
        raise FolderValidationError(
            "folder_not_found",
            "Folder not found",
            {"folder_id": folder_id},
        )
    return rows[0]


async def folder_belongs_to_notebook(folder_id: str, notebook_id: str) -> bool:
    """Return whether a folder belongs to a notebook."""
    rows = await repo_query(
        """
        SELECT id FROM $folder_id
        WHERE notebook = $notebook_id
        LIMIT 1
        """,
        {
            "folder_id": ensure_record_id(folder_id),
            "notebook_id": ensure_record_id(notebook_id),
        },
    )
    return bool(rows)


async def _assert_notebook_exists(notebook_id: str) -> None:
    if not await _record_exists(notebook_id):
        raise FolderValidationError(
            "notebook_not_found",
            "Notebook not found",
            {"notebook_id": notebook_id},
        )


async def _assert_parent_belongs_to_notebook(
    parent: str | None,
    notebook_id: str,
) -> None:
    if parent is None:
        return
    if not await folder_belongs_to_notebook(parent, notebook_id):
        raise FolderValidationError(
            "folder_not_found",
            "Parent folder not found in notebook",
            {"folder_id": parent, "notebook_id": notebook_id},
        )


async def _assert_unique_sibling_name(
    notebook_id: str,
    parent: str | None,
    normalized_name: str,
    exclude_folder_id: str | None = None,
) -> None:
    params = {
        "notebook_id": ensure_record_id(notebook_id),
        "parent": ensure_record_id(parent) if parent else None,
        "normalized_name": normalized_name,
        "exclude_folder_id": ensure_record_id(exclude_folder_id)
        if exclude_folder_id
        else None,
    }
    exclude_sql = "AND id != $exclude_folder_id" if exclude_folder_id else ""
    rows = await repo_query(
        f"""
        SELECT id FROM folder
        WHERE notebook = $notebook_id
          AND parent = $parent
          AND normalized_name = $normalized_name
          {exclude_sql}
        LIMIT 1
        """,
        params,
    )
    if rows:
        raise FolderValidationError(
            "validation_failed",
            "Folder name already exists under the same parent",
            {"normalized_name": normalized_name, "parent": parent},
        )


async def _list_notebook_folders(notebook_id: str) -> list[dict[str, Any]]:
    return await repo_query(
        """
        SELECT id, notebook, parent, name, normalized_name, description,
               sort_order, created, updated
        FROM folder
        WHERE notebook = $notebook_id
        ORDER BY sort_order ASC, name ASC, id ASC
        """,
        {"notebook_id": ensure_record_id(notebook_id)},
    )


def _source_count_map(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        folder_id = row.get("folder")
        if folder_id is not None:
            counts[str(folder_id)] = row.get("total", 0) or 0
    return counts


async def list_folder_tree(notebook_id: str) -> KBookFolderTreeResponse:
    """Return the folder tree for a notebook."""
    await _assert_notebook_exists(notebook_id)
    folders = await _list_notebook_folders(notebook_id)
    count_rows = await repo_query(
        """
        SELECT folder, count() AS total
        FROM reference
        WHERE out = $notebook_id AND folder != NONE
        GROUP BY folder
        """,
        {"notebook_id": ensure_record_id(notebook_id)},
    )
    return KBookFolderTreeResponse(
        notebook_id=notebook_id,
        items=build_folder_tree(folders, _source_count_map(count_rows)),
    )


async def create_folder(
    notebook_id: str,
    parent: str | None,
    name: str,
    description: str | None = None,
    sort_order: int = 0,
) -> KBookFolderResponse:
    """Create a folder in a notebook."""
    await _assert_notebook_exists(notebook_id)
    await _assert_parent_belongs_to_notebook(parent, notebook_id)
    cleaned_name = _clean_folder_name(name)
    normalized_name = normalize_folder_name(cleaned_name)
    await _assert_unique_sibling_name(notebook_id, parent, normalized_name)

    rows = await repo_query(
        """
        CREATE folder SET
            notebook = $notebook_id,
            parent = $parent,
            name = $name,
            normalized_name = $normalized_name,
            description = $description,
            sort_order = $sort_order
        RETURN AFTER
        """,
        {
            "notebook_id": ensure_record_id(notebook_id),
            "parent": ensure_record_id(parent) if parent else None,
            "name": cleaned_name,
            "normalized_name": normalized_name,
            "description": description,
            "sort_order": sort_order,
        },
    )
    return _folder_response_from_row(rows[0])


async def update_folder(
    notebook_id: str,
    folder_id: str,
    name: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
) -> KBookFolderResponse:
    """Update folder display fields."""
    await _assert_notebook_exists(notebook_id)
    folder = await _get_folder(folder_id)
    if str(folder.get("notebook")) != notebook_id:
        raise FolderValidationError(
            "folder_not_found",
            "Folder not found in notebook",
            {"folder_id": folder_id, "notebook_id": notebook_id},
        )

    updates: dict[str, Any] = {}
    if name is not None:
        cleaned_name = _clean_folder_name(name)
        normalized_name = normalize_folder_name(cleaned_name)
        await _assert_unique_sibling_name(
            notebook_id,
            str(folder["parent"]) if folder.get("parent") else None,
            normalized_name,
            exclude_folder_id=folder_id,
        )
        updates["name"] = cleaned_name
        updates["normalized_name"] = normalized_name
    if description is not None:
        updates["description"] = description
    if sort_order is not None:
        updates["sort_order"] = sort_order

    if not updates:
        return _folder_response_from_row(folder)

    set_clauses = [f"{field} = ${field}" for field in updates]
    query = f"""
        UPDATE $folder_id SET {", ".join(set_clauses)}, updated = time::now()
        RETURN AFTER
    """
    rows = await repo_query(
        query,
        {"folder_id": ensure_record_id(folder_id), **updates},
    )
    return _folder_response_from_row(rows[0])


def _assert_no_folder_cycle_from_rows(
    folder_id: str,
    new_parent: str | None,
    folders: list[dict[str, Any]],
) -> None:
    if new_parent is None:
        return
    if new_parent == folder_id:
        raise FolderValidationError(
            "folder_cycle",
            "Folder cannot be moved under itself",
            {"folder_id": folder_id, "parent": new_parent},
        )

    parent_by_id = {
        str(row.get("id")): str(row["parent"]) if row.get("parent") else None
        for row in folders
    }
    current = new_parent
    depth = 0
    while current is not None:
        if current == folder_id:
            raise FolderValidationError(
                "folder_cycle",
                "Folder cannot be moved under its descendant",
                {"folder_id": folder_id, "parent": new_parent},
            )
        depth += 1
        if depth > MAX_FOLDER_DEPTH:
            raise FolderValidationError(
                "validation_failed",
                "Folder depth exceeds the maximum allowed depth",
                {"max_depth": MAX_FOLDER_DEPTH},
            )
        current = parent_by_id.get(current)


async def move_folder(
    notebook_id: str,
    folder_id: str,
    parent: str | None,
    sort_order: int | None = None,
) -> KBookFolderResponse:
    """Move a folder to a new parent within the same notebook."""
    await _assert_notebook_exists(notebook_id)
    folder = await _get_folder(folder_id)
    if str(folder.get("notebook")) != notebook_id:
        raise FolderValidationError(
            "folder_not_found",
            "Folder not found in notebook",
            {"folder_id": folder_id, "notebook_id": notebook_id},
        )
    await _assert_parent_belongs_to_notebook(parent, notebook_id)
    folders = await _list_notebook_folders(notebook_id)
    _assert_no_folder_cycle_from_rows(folder_id, parent, folders)
    await _assert_unique_sibling_name(
        notebook_id,
        parent,
        folder.get("normalized_name", normalize_folder_name(folder.get("name", ""))),
        exclude_folder_id=folder_id,
    )

    updates: dict[str, Any] = {
        "parent": ensure_record_id(parent) if parent else None,
    }
    if sort_order is not None:
        updates["sort_order"] = sort_order

    set_clauses = [f"{field} = ${field}" for field in updates]
    rows = await repo_query(
        f"""
        UPDATE $folder_id SET {", ".join(set_clauses)}, updated = time::now()
        RETURN AFTER
        """,
        {"folder_id": ensure_record_id(folder_id), **updates},
    )
    return _folder_response_from_row(rows[0])


async def delete_empty_folder(notebook_id: str, folder_id: str) -> None:
    """Delete a folder only if it has no child folders and no direct files."""
    await _assert_notebook_exists(notebook_id)
    folder = await _get_folder(folder_id)
    if str(folder.get("notebook")) != notebook_id:
        raise FolderValidationError(
            "folder_not_found",
            "Folder not found in notebook",
            {"folder_id": folder_id, "notebook_id": notebook_id},
        )

    child_rows = await repo_query(
        "SELECT id FROM folder WHERE parent = $folder_id LIMIT 1",
        {"folder_id": ensure_record_id(folder_id)},
    )
    file_rows = await repo_query(
        "SELECT id FROM reference WHERE folder = $folder_id LIMIT 1",
        {"folder_id": ensure_record_id(folder_id)},
    )
    if child_rows or file_rows:
        raise FolderValidationError(
            "folder_not_empty",
            "Folder is not empty",
            {"folder_id": folder_id},
        )

    await repo_query("DELETE $folder_id", {"folder_id": ensure_record_id(folder_id)})
