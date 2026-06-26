"""K-Book dictionary query routes."""

from fastapi import APIRouter, Query

from api.kbook_errors import kbook_http_error
from api.kbook_models import (
    KBookDictionaryItemsResponse,
    KBookDictionaryTypesResponse,
)
from api.kbook_services.dictionary import (
    list_dictionary_items,
    list_dictionary_types,
)

router = APIRouter()


@router.get("/dictionary-types", response_model=KBookDictionaryTypesResponse)
async def get_kbook_dictionary_types() -> KBookDictionaryTypesResponse:
    """Return available K-Book dictionary types."""
    return await list_dictionary_types()


@router.get("/dictionary-items", response_model=KBookDictionaryItemsResponse)
async def get_kbook_dictionary_items(
    type: str | None = Query(None, description="Dictionary type code"),
    active_only: bool = Query(True),
    keyword: str | None = Query(None),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> KBookDictionaryItemsResponse:
    """Return dictionary items with optional type, status, and keyword filters."""
    try:
        return await list_dictionary_items(
            type=type,
            active_only=active_only,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise kbook_http_error(exc, details={"type": type}) from exc
