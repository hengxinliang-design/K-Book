"""Upload batch prevalidation, persistence, and processing for K-Book."""

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
    saved_files: dict[str, str] | None = None,
) -> KBookUploadBatchResponse:
    """Create an upload batch after prevalidation.

    JSON callers can omit saved_files to create a queued prevalidation batch.
    Multipart callers pass saved file paths to create Source/reference records
    immediately and allow the background processor to parse and embed content.
    """
    await validate_upload_batch(notebook_id, files, items)
    real_upload = saved_files is not None
    saved_files = saved_files or {}
    batch_rows = await repo_query(
        """
        CREATE upload_batch CONTENT $content
        """,
        {
            "content": {
                "notebook": ensure_record_id(notebook_id),
                "status": "processing" if real_upload else "queued",
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
        item_status = "processing" if real_upload else "queued"
        source_id: str | None = None
        reference_id: str | None = None
        saved_file_path = saved_files.get(item.filename)

        if real_upload:
            if not saved_file_path:
                raise UploadBatchValidationError(
                    "uploaded_file_missing",
                    "Uploaded file content is missing",
                    {"filename": item.filename},
                )
            source_id = await _create_source_for_upload(
                _clean_title(item.title, item.client_file_id),
                saved_file_path,
            )
            reference_id = await _relate_source_to_notebook(
                source_id,
                notebook_id,
                item.folder_id,
            )
            await _upsert_source_profile(source_id, item, item.filename)
            await _replace_source_tags(source_id, item.tag_ids)

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
                    "status": item_status,
                    "source": ensure_record_id(source_id) if source_id else None,
                    "reference": (
                        ensure_record_id(reference_id) if reference_id else None
                    ),
                    "file_path": saved_file_path,
                    "command": None,
                    "error": None,
                }
            },
        )
        response_items.append(_batch_item_response_from_row(rows[0]))

    return KBookUploadBatchResponse(
        batch_id=batch_id,
        status="processing" if real_upload else "queued",
        total=len(response_items),
        accepted=len(response_items),
        rejected=0,
        items=response_items,
    )


async def _create_source_for_upload(title: str, file_path: str) -> str:
    from open_notebook.domain.notebook import Asset, Source

    source = Source(
        title=title,
        topics=[],
        asset=Asset(file_path=file_path),
    )
    await source.save()
    return str(source.id)


async def _relate_source_to_notebook(
    source_id: str,
    notebook_id: str,
    folder_id: str | None,
) -> str | None:
    rows = await repo_query(
        """
        RELATE $source_id->reference->$notebook_id SET
            folder = $folder_id,
            created = time::now(),
            updated = time::now()
        """,
        {
            "source_id": ensure_record_id(source_id),
            "notebook_id": ensure_record_id(notebook_id),
            "folder_id": ensure_record_id(folder_id) if folder_id else None,
        },
    )
    return str(rows[0]["id"]) if rows else None


async def _upsert_source_profile(
    source_id: str,
    item: KBookUploadBatchItemInput,
    original_filename: str,
) -> None:
    content = {
        "source": ensure_record_id(source_id),
        "module": ensure_record_id(item.module_id) if item.module_id else None,
        "document_type": (
            ensure_record_id(item.document_type_id) if item.document_type_id else None
        ),
        "business_version": item.business_version,
        "status": ensure_record_id(item.status_id) if item.status_id else None,
        "original_filename": original_filename,
    }
    rows = await repo_query(
        "SELECT id FROM source_profile WHERE source = $source_id LIMIT 1",
        {"source_id": ensure_record_id(source_id)},
    )
    if rows:
        await repo_query(
            "UPDATE $profile_id MERGE $content",
            {
                "profile_id": ensure_record_id(str(rows[0]["id"])),
                "content": content,
            },
        )
    else:
        await repo_query("CREATE source_profile CONTENT $content", {"content": content})


async def _replace_source_tags(source_id: str, tag_ids: list[str]) -> None:
    await repo_query(
        "DELETE source_tag WHERE in = $source_id",
        {"source_id": ensure_record_id(source_id)},
    )
    for tag_id in dict.fromkeys(tag_ids):
        await repo_query(
            """
            RELATE $source_id->source_tag->$tag_id
            CONTENT { created: time::now() }
            """,
            {
                "source_id": ensure_record_id(source_id),
                "tag_id": ensure_record_id(tag_id),
            },
        )


async def process_upload_batch(batch_id: str) -> None:
    """Process saved upload batch files inside the API process.

    This local background path avoids depending on a separate surreal-commands
    worker for the initial K-Book upload experience.
    """
    batch_rows = await repo_query(
        "SELECT id, notebook, embed FROM $batch_id LIMIT 1",
        {"batch_id": ensure_record_id(batch_id)},
    )
    if not batch_rows:
        return
    batch = batch_rows[0]
    notebook_id = str(batch["notebook"])
    embed = bool(batch.get("embed", True))
    item_rows = await repo_query(
        """
        SELECT id, source, file_path, created, client_file_id
        FROM upload_batch_item
        WHERE batch = $batch_id AND status = 'processing'
        ORDER BY created ASC, client_file_id ASC
        """,
        {"batch_id": ensure_record_id(batch_id)},
    )
    await repo_query(
        "UPDATE $batch_id SET status = 'processing', updated = time::now()",
        {"batch_id": ensure_record_id(batch_id)},
    )

    for row in item_rows:
        await _process_upload_batch_item(
            batch_id=batch_id,
            item_id=str(row["id"]),
            source_id=str(row["source"]),
            file_path=row.get("file_path"),
            notebook_id=notebook_id,
            embed=embed,
        )

    await _refresh_batch_status(batch_id)


async def _process_upload_batch_item(
    *,
    batch_id: str,
    item_id: str,
    source_id: str,
    file_path: str | None,
    notebook_id: str,
    embed: bool,
) -> None:
    try:
        if not file_path:
            raise ValueError("Saved file path is missing")
        await repo_query(
            "UPDATE $item_id SET status = 'processing', error = NONE, updated = time::now()",
            {"item_id": ensure_record_id(item_id)},
        )
        await _run_source_graph(
            {
                "content_state": {
                    "file_path": file_path,
                    "delete_source": False,
                },
                "notebook_ids": [notebook_id],
                "apply_transformations": [],
                "embed": False,
                "source_id": source_id,
            }
        )
        if embed:
            embed_result = await _embed_source(source_id)
            if not embed_result.success:
                raise ValueError(embed_result.error_message or "Embedding failed")
        await repo_query(
            "UPDATE $item_id SET status = 'ready', error = NONE, updated = time::now()",
            {"item_id": ensure_record_id(item_id)},
        )
    except Exception as exc:
        await repo_query(
            """
            UPDATE $item_id SET
                status = 'failed',
                error = $error,
                updated = time::now()
            """,
            {
                "item_id": ensure_record_id(item_id),
                "error": {
                    "code": "processing_failed",
                    "message": str(exc),
                },
            },
        )
    finally:
        await _refresh_batch_status(batch_id)


async def _run_source_graph(payload: dict[str, Any]) -> Any:
    from open_notebook.graphs.source import source_graph

    return await source_graph.ainvoke(payload)


async def _embed_source(source_id: str) -> Any:
    from commands.embedding_commands import EmbedSourceInput, embed_source_command

    return await embed_source_command(EmbedSourceInput(source_id=source_id))


async def _refresh_batch_status(batch_id: str) -> None:
    rows = await repo_query(
        """
        SELECT status
        FROM upload_batch_item
        WHERE batch = $batch_id
        """,
        {"batch_id": ensure_record_id(batch_id)},
    )
    statuses = [row.get("status", "") for row in rows]
    if not statuses:
        status = "failed"
    elif all(item_status == "ready" for item_status in statuses):
        status = "completed"
    elif all(item_status == "failed" for item_status in statuses):
        status = "failed"
    elif any(item_status == "failed" for item_status in statuses):
        status = "completed_with_errors"
    elif any(item_status == "processing" for item_status in statuses):
        status = "processing"
    else:
        status = "queued"
    await repo_query(
        "UPDATE $batch_id SET status = $status, updated = time::now()",
        {"batch_id": ensure_record_id(batch_id), "status": status},
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
