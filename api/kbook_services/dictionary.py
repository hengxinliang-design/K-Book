"""Dictionary query service for K-Book."""

from typing import Any

from api.kbook_models import (
    KBookDictionaryItemResponse,
    KBookDictionaryItemsResponse,
    KBookDictionaryTypeResponse,
    KBookDictionaryTypesResponse,
)
from open_notebook.database.repository import ensure_record_id, repo_query

SYSTEM_DICTIONARY_TYPES = {
    "tag",
    "module",
    "document_type",
    "document_status",
    "ln_version",
}


def _normalize_keyword(keyword: str | None) -> str | None:
    if keyword is None:
        return None
    normalized = keyword.strip()
    return normalized or None


def _dictionary_type_from_row(row: dict[str, Any]) -> KBookDictionaryTypeResponse:
    return KBookDictionaryTypeResponse(
        id=str(row.get("id", "")),
        code=row.get("code", ""),
        name=row.get("name", ""),
        system=bool(row.get("system", False)),
        description=row.get("description"),
    )


def _dictionary_item_from_row(row: dict[str, Any]) -> KBookDictionaryItemResponse:
    dictionary_type = row.get("dictionary_type")
    type_code = ""
    if isinstance(dictionary_type, dict):
        type_code = dictionary_type.get("code", "")

    return KBookDictionaryItemResponse(
        id=str(row.get("id", "")),
        type=type_code,
        code=row.get("code", ""),
        name=row.get("name", ""),
        status=row.get("status", ""),
        description=row.get("description"),
        sort_order=row.get("sort_order", 0) or 0,
        color=row.get("color"),
    )


async def list_dictionary_types() -> KBookDictionaryTypesResponse:
    """Return dictionary types ordered by system type and display name."""
    rows = await repo_query(
        """
        SELECT id, code, name, system, description
        FROM dictionary_type
        ORDER BY system DESC, name ASC, code ASC
        """
    )
    return KBookDictionaryTypesResponse(
        items=[_dictionary_type_from_row(row) for row in rows]
    )


async def get_dictionary_type_by_code(code: str) -> dict[str, Any] | None:
    """Return a dictionary type row by stable code."""
    rows = await repo_query(
        """
        SELECT id, code, name, system, description
        FROM dictionary_type
        WHERE code = $code
        LIMIT 1
        """,
        {"code": code},
    )
    return rows[0] if rows else None


async def list_dictionary_items(
    type: str | None = None,
    active_only: bool = True,
    keyword: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> KBookDictionaryItemsResponse:
    """Return dictionary items with optional type, status, and keyword filters."""
    dictionary_type_id = None
    if type is not None:
        dictionary_type = await get_dictionary_type_by_code(type)
        if dictionary_type is None:
            raise ValueError(f"Unknown dictionary type: {type}")
        dictionary_type_id = ensure_record_id(dictionary_type["id"])

    normalized_keyword = _normalize_keyword(keyword)
    params = {
        "dictionary_type": dictionary_type_id,
        "active_only": active_only,
        "keyword": normalized_keyword,
        "limit": limit,
        "offset": offset,
    }

    where_clauses = []
    if dictionary_type_id is not None:
        where_clauses.append("dictionary_type = $dictionary_type")
    if active_only:
        where_clauses.append("status = 'active'")
    if normalized_keyword is not None:
        where_clauses.append(
            "(string::lowercase(name) CONTAINS string::lowercase($keyword) "
            "OR string::lowercase(code) CONTAINS string::lowercase($keyword) "
            "OR string::lowercase(normalized_name) CONTAINS string::lowercase($keyword))"
        )

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    query = f"""
        SELECT id, dictionary_type, code, name, status, description, sort_order, color
        FROM dictionary_item
        {where_sql}
        ORDER BY sort_order ASC, name ASC, code ASC
        LIMIT $limit START $offset
        FETCH dictionary_type
    """
    count_query = f"""
        SELECT count() AS total
        FROM dictionary_item
        {where_sql}
        GROUP ALL
    """

    rows = await repo_query(query, params)
    count_rows = await repo_query(count_query, params)
    total = count_rows[0].get("total", 0) if count_rows else 0

    return KBookDictionaryItemsResponse(
        items=[_dictionary_item_from_row(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


async def validate_dictionary_item(
    item_id: str,
    expected_type: str,
    require_active: bool = True,
) -> dict[str, Any]:
    """Validate a dictionary item exists, has the expected type, and is active."""
    if expected_type not in SYSTEM_DICTIONARY_TYPES:
        raise ValueError(f"Unknown dictionary type: {expected_type}")

    rows = await repo_query(
        """
        SELECT id, dictionary_type, code, name, status
        FROM $item_id
        FETCH dictionary_type
        """,
        {"item_id": ensure_record_id(item_id)},
    )
    if not rows:
        raise ValueError(f"Dictionary item not found: {item_id}")

    item = rows[0]
    dictionary_type = item.get("dictionary_type")
    type_code = dictionary_type.get("code") if isinstance(dictionary_type, dict) else None
    if type_code != expected_type:
        raise ValueError(
            f"Dictionary item {item_id} has type {type_code}, expected {expected_type}"
        )
    if require_active and item.get("status") != "active":
        raise ValueError(f"Dictionary item is inactive: {item_id}")

    return item
