"""K-Book upload batch routes."""

from fastapi import APIRouter, Request, status

from api.kbook_errors import kbook_http_error
from api.kbook_models import (
    KBookUploadBatchCreateRequest,
    KBookUploadBatchFileInput,
    KBookUploadBatchResponse,
)
from api.kbook_services.upload_batches import (
    UploadBatchValidationError,
    create_upload_batch,
    get_upload_batch,
    parse_upload_items,
)

router = APIRouter()


def _upload_batch_error(exc: UploadBatchValidationError):
    return kbook_http_error(
        exc,
        not_found_codes={"notebook_not_found", "folder_not_found", "upload_batch_not_found"},
    )


async def _request_to_batch_create(request: Request) -> KBookUploadBatchCreateRequest:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload_files = form.getlist("files")
        files = [
            KBookUploadBatchFileInput(filename=file.filename or "")
            for file in upload_files
        ]
        return KBookUploadBatchCreateRequest(
            notebook_id=str(form.get("notebook_id", "")),
            files=files,
            items=parse_upload_items(str(form.get("items", "[]"))),
            async_processing=str(form.get("async_processing", "true")).lower() != "false",
            embed=str(form.get("embed", "true")).lower() != "false",
        )
    payload = await request.json()
    return KBookUploadBatchCreateRequest(**payload)


@router.post(
    "/upload-batches",
    response_model=KBookUploadBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_kbook_upload_batch(request: Request) -> KBookUploadBatchResponse:
    """Create a queued upload batch after prevalidation."""
    try:
        batch = await _request_to_batch_create(request)
        return await create_upload_batch(
            notebook_id=batch.notebook_id,
            files=batch.files,
            items=batch.items,
            async_processing=batch.async_processing,
            embed=batch.embed,
        )
    except UploadBatchValidationError as exc:
        raise _upload_batch_error(exc) from exc


@router.get("/upload-batches/{batch_id}", response_model=KBookUploadBatchResponse)
async def get_kbook_upload_batch(batch_id: str) -> KBookUploadBatchResponse:
    """Return upload batch status."""
    try:
        return await get_upload_batch(batch_id)
    except UploadBatchValidationError as exc:
        raise _upload_batch_error(exc) from exc
