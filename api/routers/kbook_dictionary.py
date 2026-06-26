"""K-Book dictionary query routes."""

from fastapi import APIRouter, Query, status

from api.kbook_errors import kbook_http_error
from api.kbook_models import (
    KBookDictionaryItemCreateRequest,
    KBookDictionaryItemsResponse,
    KBookDictionaryItemResponse,
    KBookDictionaryItemUpdateRequest,
    KBookDictionaryTypesResponse,
)
from api.kbook_services.dictionary import (
    DictionaryValidationError,
    create_dictionary_item,
    list_dictionary_items,
    list_dictionary_types,
    update_dictionary_item,
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


@router.post(
    "/dictionary-items",
    response_model=KBookDictionaryItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_kbook_dictionary_item(
    request: KBookDictionaryItemCreateRequest,
) -> KBookDictionaryItemResponse:
    """Create a dictionary item for K-Book metadata management."""
    try:
        return await create_dictionary_item(
            type=request.type,
            code=request.code,
            name=request.name,
            description=request.description,
            sort_order=request.sort_order,
            color=request.color,
        )
    except DictionaryValidationError as exc:
        raise kbook_http_error(exc) from exc


@router.patch(
    "/dictionary-items/{item_id}",
    response_model=KBookDictionaryItemResponse,
)
async def update_kbook_dictionary_item(
    item_id: str,
    request: KBookDictionaryItemUpdateRequest,
) -> KBookDictionaryItemResponse:
    """Update a dictionary item for K-Book metadata management."""
    try:
        return await update_dictionary_item(
            item_id,
            code=request.code,
            name=request.name,
            description=request.description,
            status=request.status,
            sort_order=request.sort_order,
            color=request.color,
        )
    except DictionaryValidationError as exc:
        raise kbook_http_error(
            exc,
            not_found_codes={"dictionary_item_not_found"},
        ) from exc
