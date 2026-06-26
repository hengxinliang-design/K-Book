"""Upload batch prevalidation and queue skeleton for K-Book."""

import json
from typing import Any

from api.kbook_models import (
    KBookUploadBatchFileInput,
    KBookUploadBatchItemInput,
    KBookUploadBatchResponse,
    KBookUploadBatchItemResponse,
)
from api.kbook_services.dictionary import validate_dictionary_item
from api.kbook_services.folders import folder_belongs_to_notebook
from api.kbook_services.upload_config import (
    KBOOK_MAX_FILES_PER_BATCH,
    is_supported_upload_extension,
)
from open_notebook.database.repository import ensure_record_id, repo_query


class UploadBatchValidationError(ValueError):
    """Raised when upload batch prevalidation fails."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


async def _record_exists(record_id: str) -> bool:
    rows = await repo_query(
        "SELECT id FROM $record_id LIMIT 1",
        {"record_id": ensure_record_id(record_id)},
    )
    return bool(rows)


async def _assert_notebook_exists(notebook_id: str) -> None:
    if not await _record_exists(notebook_id):
        raise UploadBatchValidationError(
            "notebook_not_found",
            "Notebook not found",
            {"notebook_id": notebook_id},
        )


def _clean_title(title: str, client_file_id: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise UploadBatchValidationError(
            "validation_failed",
            "Upload item title cannot be empty",
            {"client_file_id": client_file_id, "field": "title"},
        )
    return cleaned


async def _validate_dictionary_item(
    item_id: str | None,
    expected_type: str,
) -> None:
    if not item_id:
        return
    try:
        await validate_dictionary_item(
            item_id,
            expected_type=expected_type,
            require_active=True,
        )
    except ValueError as exc:
        message = str(exc)
        code = "validation_failed"
        if "inactive" in message:
            code = "dictionary_item_inactive"
        elif "expected" in message:
            code = "dictionary_type_mismatch"
        raise UploadBatchValidationError(
            code,
            message,
            {"item_id": item_id, "expected_type": expected_type},
        ) from exc


def parse_upload_items(items: str | list[dict[str, Any]]) -> list[KBookUploadBatchItemInput]:
    """Parse upload item metadata from form JSON or already decoded JSON."""
    raw_items = json.loads(items) if isinstance(items, str) else items
    if not isinstance(raw_items, list):
        raise UploadBatchValidationError(
            "validation_failed",
            "Upload items must be a JSON array",
            {"field": "items"},
        )
    return [KBookUploadBatchItemInput(**item) for item in raw_items]


async def validate_upload_batch(
    notebook_id: str,
    files: list[KBookUploadBatchFileInput],
    items: list[KBookUploadBatchItemInput],
) -> None:
    """Validate upload batch request without creating sources or embeddings."""
    await _assert_notebook_exists(notebook_id)
    if not files:
        raise UploadBatchValidationError(
            "validation_failed",
            "Upload batch must contain at least one file",
            {"field": "files"},
        )
    if len(files) > KBOOK_MAX_FILES_PER_BATCH:
        raise UploadBatchValidationError(
            "validation_failed",
            "Upload batch exceeds max files per batch",
            {"max_files_per_batch": KBOOK_MAX_FILES_PER_BATCH},
        )
    if len(files) != len(items):
        raise UploadBatchValidationError(
            "validation_failed",
            "Upload items length must match files length",
            {"files": len(files), "items": len(items)},
        )

    filenames = [file.filename for file in files]
    filename_set = set(filenames)
    if len(filename_set) != len(filenames):
        raise UploadBatchValidationError(
            "validation_failed",
            "Upload filenames must be unique within a batch",
            {"field": "files"},
        )

    for file in files:
        if not is_supported_upload_extension(file.filename):
            raise UploadBatchValidationError(
                "unsupported_file_type",
                "File type is not supported",
                {"filename": file.filename},
            )

    for item in items:
        if item.filename not in filename_set:
            raise UploadBatchValidationError(
                "validation_failed",
                "Upload item filename does not match uploaded files",
                {"filename": item.filename},
            )
        _clean_title(item.title, item.client_file_id)
        if item.folder_id and not await folder_belongs_to_notebook(
            item.folder_id,
            notebook_id,
        ):
            raise UploadBatchValidationError(
                "folder_not_found",
                "Folder not found in notebook",
                {"folder_id": item.folder_id, "notebook_id": notebook_id},
            )
        for tag_id in item.tag_ids:
            await _validate_dictionary_item(tag_id, "tag")
        await _validate_dictionary_item(item.module_id, "module")
        await _validate_dictionary_item(item.document_type_id, "document_type")
        await _validate_dictionary_item(item.status_id, "document_status")


def _batch_item_response_from_row(row: dict[str, Any]) -> KBookUploadBatchItemResponse:
    return KBookUploadBatchItemResponse(
        client_file_id=row.get("client_file_id", ""),
        filename=row.get("filename", ""),
        status=row.get("status", ""),
        source_id=str(row["source"]) if row.get("source") else None,
        reference_id=str(row["reference"]) if row.get("reference") else None,
        error=row.get("error"),
    )


def _batch_status_from_items(items: list[KBookUploadBatchItemResponse]) -> str:
    if not items:
        return "failed"
    statuses = [item.status for item in items]
    if all(status == "ready" for status in statuses):
        return "completed"
    if all(status == "failed" for status in statuses):
        return "failed"
    if any(status == "failed" for status in statuses):
        return "completed_with_errors"
    if any(status in {"uploading", "uploaded", "processing"} for status in statuses):
        return "processing"
    return "queued"


async def create_upload_batch(
    notebook_id: str,
    files: list[KBookUploadBatchFileInput],
    items: list[KBookUploadBatchItemInput],
    async_processing: bool = True,
    embed: bool = True,
) -> KBookUploadBatchResponse:
    """Create a queued upload batch after prevalidation.

    This skeleton intentionally does not save files, create Source records,
    or start embedding tasks.
    """
    await validate_upload_batch(notebook_id, files, items)
    batch_rows = await repo_query(
        """
        CREATE upload_batch CONTENT $content
        """,
        {
            "content": {
                "notebook": ensure_record_id(notebook_id),
                "status": "queued",
                "total": len(items),
                "accepted": len(items),
                "rejected": 0,
                "async_processing": async_processing,
                "embed": embed,
            }
        },
    )
    batch_id = str(batch_rows[0]["id"])
    response_items = []
    for item in items:
        rows = await repo_query(
            """
            CREATE upload_batch_item CONTENT $content
            """,
            {
                "content": {
                    "batch": ensure_record_id(batch_id),
                    "client_file_id": item.client_file_id,
                    "filename": item.filename,
                    "title": _clean_title(item.title, item.client_file_id),
                    "status": "queued",
                    "source": None,
                    "reference": None,
                    "error": None,
                }
            },
        )
        response_items.append(_batch_item_response_from_row(rows[0]))

    return KBookUploadBatchResponse(
        batch_id=batch_id,
        status="queued",
        total=len(response_items),
        accepted=len(response_items),
        rejected=0,
        items=response_items,
    )


async def get_upload_batch(batch_id: str) -> KBookUploadBatchResponse:
    """Return upload batch status and per-file item status."""
    batch_rows = await repo_query(
        """
        SELECT id, status, total, accepted, rejected
        FROM $batch_id
        LIMIT 1
        """,
        {"batch_id": ensure_record_id(batch_id)},
    )
    if not batch_rows:
        raise UploadBatchValidationError(
            "upload_batch_not_found",
            "Upload batch not found",
            {"batch_id": batch_id},
        )
    item_rows = await repo_query(
        """
        SELECT client_file_id, filename, status, source, reference, error, created
        FROM upload_batch_item
        WHERE batch = $batch_id
        ORDER BY created ASC, client_file_id ASC
        """,
        {"batch_id": ensure_record_id(batch_id)},
    )
    items = [_batch_item_response_from_row(row) for row in item_rows]
    status = _batch_status_from_items(items)
    counts = {name: 0 for name in ["queued", "processing", "ready", "failed"]}
    for item in items:
        if item.status in counts:
            counts[item.status] += 1
        elif item.status in {"uploading", "uploaded"}:
            counts["processing"] += 1

    batch = batch_rows[0]
    return KBookUploadBatchResponse(
        batch_id=str(batch.get("id", batch_id)),
        status=status,
        total=batch.get("total", len(items)),
        accepted=batch.get("accepted"),
        rejected=batch.get("rejected"),
        queued=counts["queued"],
        processing=counts["processing"],
        ready=counts["ready"],
        failed=counts["failed"],
        items=items,
    )
