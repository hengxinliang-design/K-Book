"""K-Book upload batch routes."""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Request, UploadFile, status
from pydantic import ValidationError

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
    process_upload_batch,
)
from open_notebook.config import UPLOADS_FOLDER

router = APIRouter()


def _upload_batch_error(exc: UploadBatchValidationError):
    return kbook_http_error(
        exc,
        not_found_codes={"notebook_not_found", "folder_not_found", "upload_batch_not_found"},
    )


def _safe_upload_filename(filename: str) -> str:
    suffix = Path(filename).suffix
    stem = Path(filename).stem or "upload"
    safe_stem = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in stem
    ).strip("-") or "upload"
    return f"{safe_stem}-{uuid4().hex}{suffix}"


async def _save_upload_file(upload_file: UploadFile) -> str:
    if not upload_file.filename:
        raise UploadBatchValidationError(
            "validation_failed",
            "Uploaded file must have a filename",
            {"field": "files"},
        )
    Path(UPLOADS_FOLDER).mkdir(parents=True, exist_ok=True)
    target = Path(UPLOADS_FOLDER) / _safe_upload_filename(upload_file.filename)
    target_resolved = target.resolve()
    upload_root = Path(UPLOADS_FOLDER).resolve()
    if not str(target_resolved).startswith(str(upload_root)):
        raise UploadBatchValidationError(
            "validation_failed",
            "Invalid uploaded file path",
            {"filename": upload_file.filename},
        )
    content = await upload_file.read()
    target.write_bytes(content)
    return str(target)


async def _request_to_batch_create(
    request: Request,
) -> tuple[KBookUploadBatchCreateRequest, dict[str, str] | None]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload_files = form.getlist("files")
        files = [
            KBookUploadBatchFileInput(filename=file.filename or "")
            for file in upload_files
        ]
        batch = KBookUploadBatchCreateRequest(
            notebook_id=str(form.get("notebook_id", "")),
            files=files,
            items=parse_upload_items(str(form.get("items", "[]"))),
            async_processing=str(form.get("async_processing", "true")).lower() != "false",
            embed=str(form.get("embed", "true")).lower() != "false",
        )
        saved_files = {}
        for upload_file in upload_files:
            if not isinstance(upload_file, UploadFile) and not hasattr(
                upload_file, "read"
            ):
                continue
            saved_files[upload_file.filename or ""] = await _save_upload_file(
                upload_file
            )
        return batch, saved_files
    payload = await request.json()
    return KBookUploadBatchCreateRequest(**payload), None


@router.post(
    "/upload-batches",
    response_model=KBookUploadBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_kbook_upload_batch(
    request: Request,
    background_tasks: BackgroundTasks,
) -> KBookUploadBatchResponse:
    """Create a queued upload batch after prevalidation."""
    try:
        batch, saved_files = await _request_to_batch_create(request)
        response = await create_upload_batch(
            notebook_id=batch.notebook_id,
            files=batch.files,
            items=batch.items,
            async_processing=batch.async_processing,
            embed=batch.embed,
            saved_files=saved_files,
        )
        if saved_files:
            background_tasks.add_task(process_upload_batch, response.batch_id)
        return response
    except UploadBatchValidationError as exc:
        raise _upload_batch_error(exc) from exc
    except ValidationError as exc:
        raise _upload_batch_error(
            UploadBatchValidationError(
                "invalid_upload_batch_request",
                "Invalid upload batch request",
                {"validation_error": str(exc)},
            )
        ) from exc


@router.get("/upload-batches/{batch_id}", response_model=KBookUploadBatchResponse)
async def get_kbook_upload_batch(batch_id: str) -> KBookUploadBatchResponse:
    """Return upload batch status."""
    try:
        return await get_upload_batch(batch_id)
    except UploadBatchValidationError as exc:
        raise _upload_batch_error(exc) from exc
