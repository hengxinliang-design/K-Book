"""K-Book folder management routes."""

from fastapi import APIRouter, HTTPException, status

from api.kbook_models import (
    KBookFolderCreateRequest,
    KBookFolderMoveRequest,
    KBookFolderResponse,
    KBookFolderTreeResponse,
    KBookFolderUpdateRequest,
)
from api.kbook_services.folders import (
    FolderValidationError,
    create_folder,
    delete_empty_folder,
    list_folder_tree,
    move_folder,
    update_folder,
)

router = APIRouter()


def _folder_error(exc: FolderValidationError) -> HTTPException:
    status_code = 400
    if exc.code in {"folder_not_found", "notebook_not_found"}:
        status_code = 404
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "code": exc.code,
                "message": str(exc),
                "details": exc.details,
            }
        },
    )


@router.get(
    "/notebooks/{notebook_id}/folders",
    response_model=KBookFolderTreeResponse,
)
async def get_kbook_folder_tree(notebook_id: str) -> KBookFolderTreeResponse:
    """Return a notebook's folder tree."""
    try:
        return await list_folder_tree(notebook_id)
    except FolderValidationError as exc:
        raise _folder_error(exc) from exc


@router.post(
    "/notebooks/{notebook_id}/folders",
    response_model=KBookFolderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_kbook_folder(
    notebook_id: str,
    request: KBookFolderCreateRequest,
) -> KBookFolderResponse:
    """Create a folder in a notebook."""
    try:
        return await create_folder(
            notebook_id=notebook_id,
            parent=request.parent,
            name=request.name,
            description=request.description,
            sort_order=request.sort_order,
        )
    except FolderValidationError as exc:
        raise _folder_error(exc) from exc


@router.patch(
    "/notebooks/{notebook_id}/folders/{folder_id}",
    response_model=KBookFolderResponse,
)
async def update_kbook_folder(
    notebook_id: str,
    folder_id: str,
    request: KBookFolderUpdateRequest,
) -> KBookFolderResponse:
    """Update folder display fields."""
    try:
        return await update_folder(
            notebook_id=notebook_id,
            folder_id=folder_id,
            name=request.name,
            description=request.description,
            sort_order=request.sort_order,
        )
    except FolderValidationError as exc:
        raise _folder_error(exc) from exc


@router.post(
    "/notebooks/{notebook_id}/folders/{folder_id}/move",
    response_model=KBookFolderResponse,
)
async def move_kbook_folder(
    notebook_id: str,
    folder_id: str,
    request: KBookFolderMoveRequest,
) -> KBookFolderResponse:
    """Move a folder within a notebook."""
    try:
        return await move_folder(
            notebook_id=notebook_id,
            folder_id=folder_id,
            parent=request.parent,
            sort_order=request.sort_order,
        )
    except FolderValidationError as exc:
        raise _folder_error(exc) from exc


@router.delete(
    "/notebooks/{notebook_id}/folders/{folder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_kbook_folder(notebook_id: str, folder_id: str) -> None:
    """Delete an empty folder."""
    try:
        await delete_empty_folder(notebook_id, folder_id)
    except FolderValidationError as exc:
        raise _folder_error(exc) from exc
