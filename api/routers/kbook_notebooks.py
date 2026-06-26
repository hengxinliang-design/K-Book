"""K-Book notebook metadata routes."""

from fastapi import APIRouter, Query

from api.kbook_errors import kbook_http_error
from api.kbook_models import (
    KBookNotebookItem,
    KBookNotebooksResponse,
    KBookNotebookUpdateRequest,
)
from api.kbook_services.notebooks import (
    NotebookMetadataValidationError,
    list_kbook_notebooks,
    update_kbook_notebook,
)

router = APIRouter()


def _notebook_error(exc: NotebookMetadataValidationError):
    return kbook_http_error(
        exc,
        not_found_codes={
            "notebook_not_found",
            "customer_not_found",
            "project_not_found",
        },
    )


@router.get("/notebooks", response_model=KBookNotebooksResponse)
async def get_kbook_notebooks(
    keyword: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> KBookNotebooksResponse:
    """List K-Book notebooks with business metadata."""
    try:
        return await list_kbook_notebooks(keyword=keyword, limit=limit, offset=offset)
    except NotebookMetadataValidationError as exc:
        raise _notebook_error(exc) from exc


@router.patch("/notebooks/{notebook_id}", response_model=KBookNotebookItem)
async def patch_kbook_notebook(
    notebook_id: str,
    request: KBookNotebookUpdateRequest,
) -> KBookNotebookItem:
    """Update K-Book notebook business metadata."""
    try:
        return await update_kbook_notebook(
            notebook_id,
            name=request.name,
            description=request.description,
            customer_id=request.customer_id,
            project_id=request.project_id,
            ln_version_ids=request.ln_version_ids,
            scope=request.scope,
        )
    except NotebookMetadataValidationError as exc:
        raise _notebook_error(exc) from exc
