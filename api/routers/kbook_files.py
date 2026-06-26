"""K-Book file list and file location routes."""

from typing import Annotated

from fastapi import APIRouter, Query

from api.kbook_errors import KBookHTTPException, kbook_http_error
from api.kbook_models import (
    KBookFileDetailResponse,
    KBookFileListResponse,
    KBookAddExistingSourceRequest,
    KBookAddExistingSourceResponse,
    KBookMoveFileRequest,
    KBookRemoveFileResponse,
    KBookSourceSearchResponse,
)
from api.kbook_services.files import (
    FileValidationError,
    KBookFileFilters,
    add_existing_source_to_notebook,
    get_notebook_file_detail,
    list_notebook_files,
    move_file_to_folder,
    remove_file_from_notebook,
    search_existing_sources,
)

router = APIRouter()


def _file_error(exc: FileValidationError) -> KBookHTTPException:
    return kbook_http_error(
        exc,
        not_found_codes={"notebook_not_found", "source_not_found", "folder_not_found"},
    )


@router.get("/notebooks/{notebook_id}/files", response_model=KBookFileListResponse)
async def get_kbook_files(
    notebook_id: str,
    folder_id: str | None = Query(None),
    tag_ids: Annotated[list[str] | None, Query()] = None,
    module_id: str | None = Query(None),
    document_type_id: str | None = Query(None),
    status_id: str | None = Query(None),
    business_version: str | None = Query(None),
    keyword: str | None = Query(None),
    processing_status: str | None = Query(None),
    sort_by: str = Query("updated"),
    sort_order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> KBookFileListResponse:
    """Return files linked to a notebook."""
    try:
        return await list_notebook_files(
            notebook_id=notebook_id,
            filters=KBookFileFilters(
                folder_id=folder_id,
                tag_ids=tag_ids or [],
                module_id=module_id,
                document_type_id=document_type_id,
                status_id=status_id,
                business_version=business_version,
                keyword=keyword,
                processing_status=processing_status,
            ),
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except FileValidationError as exc:
        raise _file_error(exc) from exc


@router.get("/sources/search", response_model=KBookSourceSearchResponse)
async def search_kbook_sources(
    keyword: str | None = Query(None),
    exclude_notebook_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> KBookSourceSearchResponse:
    """Search existing sources that can be added to a notebook."""
    try:
        return await search_existing_sources(
            keyword=keyword,
            exclude_notebook_id=exclude_notebook_id,
            limit=limit,
            offset=offset,
        )
    except FileValidationError as exc:
        raise _file_error(exc) from exc


@router.get(
    "/notebooks/{notebook_id}/files/{source_id}",
    response_model=KBookFileDetailResponse,
)
async def get_kbook_file_detail(
    notebook_id: str,
    source_id: str,
) -> KBookFileDetailResponse:
    """Return a file detail row inside a notebook."""
    try:
        return await get_notebook_file_detail(notebook_id, source_id)
    except FileValidationError as exc:
        raise _file_error(exc) from exc


@router.patch(
    "/notebooks/{notebook_id}/files/{source_id}/folder",
    response_model=KBookFileDetailResponse,
)
async def move_kbook_file_to_folder(
    notebook_id: str,
    source_id: str,
    request: KBookMoveFileRequest,
) -> KBookFileDetailResponse:
    """Move a file to a folder in the current notebook."""
    try:
        return await move_file_to_folder(
            notebook_id=notebook_id,
            source_id=source_id,
            folder_id=request.folder_id,
        )
    except FileValidationError as exc:
        raise _file_error(exc) from exc


@router.delete(
    "/notebooks/{notebook_id}/files/{source_id}",
    response_model=KBookRemoveFileResponse,
)
async def remove_kbook_file_from_notebook(
    notebook_id: str,
    source_id: str,
) -> KBookRemoveFileResponse:
    """Remove a source from a notebook without deleting the source."""
    try:
        return await remove_file_from_notebook(notebook_id, source_id)
    except FileValidationError as exc:
        raise _file_error(exc) from exc


@router.post(
    "/notebooks/{notebook_id}/files",
    response_model=KBookAddExistingSourceResponse,
)
async def add_kbook_existing_source_to_notebook(
    notebook_id: str,
    request: KBookAddExistingSourceRequest,
) -> KBookAddExistingSourceResponse:
    """Add an existing source to a notebook."""
    try:
        return await add_existing_source_to_notebook(
            notebook_id=notebook_id,
            source_id=request.source_id,
            folder_id=request.folder_id,
        )
    except FileValidationError as exc:
        raise _file_error(exc) from exc
