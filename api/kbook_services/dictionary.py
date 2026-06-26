"""Dictionary query service for K-Book."""

import unicodedata
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
DICTIONARY_ITEM_STATUSES = {"active", "inactive"}


class DictionaryValidationError(ValueError):
    """Raised when a dictionary write operation is invalid."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _normalize_keyword(keyword: str | None) -> str | None:
    if keyword is None:
        return None
    normalized = keyword.strip()
    return normalized or None


def normalize_dictionary_name(name: str) -> str:
    """Normalize a dictionary item name for uniqueness checks."""
    return unicodedata.normalize("NFKC", name).strip().casefold()


def _clean_required_text(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise DictionaryValidationError(
            "validation_failed",
            f"Dictionary item {field} cannot be empty",
            {"field": field},
        )
    return cleaned


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


async def _get_dictionary_item(item_id: str) -> dict[str, Any] | None:
    rows = await repo_query(
        """
        SELECT id, dictionary_type, code, name, normalized_name, status,
            description, sort_order, color
        FROM $item_id
        FETCH dictionary_type
        """,
        {"item_id": ensure_record_id(item_id)},
    )
    return rows[0] if rows else None


async def _assert_dictionary_type_exists(type_code: str) -> dict[str, Any]:
    dictionary_type = await get_dictionary_type_by_code(type_code)
    if dictionary_type is None:
        raise DictionaryValidationError(
            "validation_failed",
            f"Unknown dictionary type: {type_code}",
            {"type": type_code},
        )
    return dictionary_type


async def _assert_dictionary_item_unique(
    dictionary_type_id: Any,
    *,
    code: str | None = None,
    normalized_name: str | None = None,
    exclude_item_id: str | None = None,
) -> None:
    params = {
        "dictionary_type": dictionary_type_id,
        "code": code,
        "normalized_name": normalized_name,
        "exclude_item_id": ensure_record_id(exclude_item_id) if exclude_item_id else None,
    }
    exclude_sql = "AND id != $exclude_item_id" if exclude_item_id else ""

    if code is not None:
        rows = await repo_query(
            f"""
            SELECT id FROM dictionary_item
            WHERE dictionary_type = $dictionary_type AND code = $code
            {exclude_sql}
            LIMIT 1
            """,
            params,
        )
        if rows:
            raise DictionaryValidationError(
                "validation_failed",
                "Dictionary item code already exists in this type",
                {"field": "code", "code": code},
            )

    if normalized_name is not None:
        rows = await repo_query(
            f"""
            SELECT id FROM dictionary_item
            WHERE dictionary_type = $dictionary_type
                AND normalized_name = $normalized_name
            {exclude_sql}
            LIMIT 1
            """,
            params,
        )
        if rows:
            raise DictionaryValidationError(
                "validation_failed",
                "Dictionary item name already exists in this type",
                {"field": "name", "normalized_name": normalized_name},
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


async def create_dictionary_item(
    type: str,
    code: str,
    name: str,
    description: str | None = None,
    sort_order: int = 0,
    color: str | None = None,
) -> KBookDictionaryItemResponse:
    """Create an active dictionary item under a dictionary type."""
    dictionary_type = await _assert_dictionary_type_exists(type)
    dictionary_type_id = ensure_record_id(dictionary_type["id"])
    cleaned_code = _clean_required_text(code, "code")
    cleaned_name = _clean_required_text(name, "name")
    normalized_name = normalize_dictionary_name(cleaned_name)

    await _assert_dictionary_item_unique(
        dictionary_type_id,
        code=cleaned_code,
        normalized_name=normalized_name,
    )

    rows = await repo_query(
        """
        CREATE dictionary_item CONTENT $content
        FETCH dictionary_type
        """,
        {
            "content": {
                "dictionary_type": dictionary_type_id,
                "code": cleaned_code,
                "name": cleaned_name,
                "normalized_name": normalized_name,
                "description": description,
                "status": "active",
                "sort_order": sort_order,
                "color": color,
            }
        },
    )
    return _dictionary_item_from_row(rows[0])


async def update_dictionary_item(
    item_id: str,
    *,
    code: str | None = None,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    sort_order: int | None = None,
    color: str | None = None,
) -> KBookDictionaryItemResponse:
    """Update mutable dictionary item fields."""
    item = await _get_dictionary_item(item_id)
    if item is None:
        raise DictionaryValidationError(
            "dictionary_item_not_found",
            "Dictionary item not found",
            {"item_id": item_id},
        )

    dictionary_type = item.get("dictionary_type")
    if not isinstance(dictionary_type, dict):
        raise DictionaryValidationError(
            "validation_failed",
            "Dictionary item has invalid dictionary type",
            {"item_id": item_id},
        )
    dictionary_type_id = ensure_record_id(str(dictionary_type["id"]))

    patch: dict[str, Any] = {}
    if code is not None:
        if dictionary_type.get("system"):
            raise DictionaryValidationError(
                "validation_failed",
                "Code cannot be changed for system dictionary items",
                {"field": "code", "item_id": item_id},
            )
        cleaned_code = _clean_required_text(code, "code")
        await _assert_dictionary_item_unique(
            dictionary_type_id,
            code=cleaned_code,
            exclude_item_id=item_id,
        )
        patch["code"] = cleaned_code

    if name is not None:
        cleaned_name = _clean_required_text(name, "name")
        normalized_name = normalize_dictionary_name(cleaned_name)
        await _assert_dictionary_item_unique(
            dictionary_type_id,
            normalized_name=normalized_name,
            exclude_item_id=item_id,
        )
        patch["name"] = cleaned_name
        patch["normalized_name"] = normalized_name

    if status is not None:
        if status not in DICTIONARY_ITEM_STATUSES:
            raise DictionaryValidationError(
                "validation_failed",
                "Dictionary item status must be active or inactive",
                {"field": "status", "allowed": sorted(DICTIONARY_ITEM_STATUSES)},
            )
        patch["status"] = status

    if description is not None:
        patch["description"] = description
    if sort_order is not None:
        patch["sort_order"] = sort_order
    if color is not None:
        patch["color"] = color

    if not patch:
        return _dictionary_item_from_row(item)

    rows = await repo_query(
        """
        UPDATE $item_id MERGE $patch
        FETCH dictionary_type
        """,
        {
            "item_id": ensure_record_id(item_id),
            "patch": patch,
        },
    )
    return _dictionary_item_from_row(rows[0])
