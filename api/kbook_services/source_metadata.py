"""Source title, profile, and tag editing service for K-Book."""

from typing import Any

from api.kbook_models import (
    KBookSourceProfileResponse,
    KBookSourceTagsResponse,
    KBookSourceTitleResponse,
)
from api.kbook_services.dictionary import validate_dictionary_item
from open_notebook.database.repository import ensure_record_id, repo_query


class SourceMetadataValidationError(ValueError):
    """Raised when a K-Book source metadata operation is invalid."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


async def _source_exists(source_id: str) -> bool:
    rows = await repo_query(
        "SELECT id FROM $source_id LIMIT 1",
        {"source_id": ensure_record_id(source_id)},
    )
    return bool(rows)


async def _assert_source_exists(source_id: str) -> None:
    if not await _source_exists(source_id):
        raise SourceMetadataValidationError(
            "source_not_found",
            "Source not found",
            {"source_id": source_id},
        )


async def _validate_dictionary_item(
    item_id: str | None,
    expected_type: str,
) -> Any:
    if not item_id:
        return None
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
        elif "not found" in message:
            code = "dictionary_item_not_found"
        raise SourceMetadataValidationError(
            code,
            message,
            {"item_id": item_id, "expected_type": expected_type},
        ) from exc
    return ensure_record_id(item_id)


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        raise SourceMetadataValidationError(
            "validation_failed",
            "Source title cannot be empty",
            {"field": "title"},
        )
    return cleaned


async def update_source_title(
    source_id: str,
    title: str,
) -> KBookSourceTitleResponse:
    """Update source display title without changing file content or embeddings."""
    await _assert_source_exists(source_id)
    cleaned_title = _clean_title(title)
    rows = await repo_query(
        """
        UPDATE $source_id SET
            title = $title,
            updated = time::now()
        """,
        {
            "source_id": ensure_record_id(source_id),
            "title": cleaned_title,
        },
    )
    row = rows[0] if rows else {}
    return KBookSourceTitleResponse(
        source_id=source_id,
        title=row.get("title", cleaned_title),
        updated=str(row["updated"]) if row.get("updated") else None,
    )


async def update_source_profile(
    source_id: str,
    *,
    module_id: str | None = None,
    document_type_id: str | None = None,
    business_version: str | None = None,
    status_id: str | None = None,
) -> KBookSourceProfileResponse:
    """Create or update SourceProfile without triggering relearning."""
    await _assert_source_exists(source_id)
    module_record = await _validate_dictionary_item(module_id, "module")
    document_type_record = await _validate_dictionary_item(
        document_type_id,
        "document_type",
    )
    status_record = await _validate_dictionary_item(status_id, "document_status")

    rows = await repo_query(
        """
        SELECT id FROM source_profile
        WHERE source = $source_id
        LIMIT 1
        """,
        {"source_id": ensure_record_id(source_id)},
    )
    content = {
        "source": ensure_record_id(source_id),
        "module": module_record,
        "document_type": document_type_record,
        "business_version": business_version,
        "status": status_record,
    }
    if rows:
        result = await repo_query(
            """
            UPDATE $profile_id MERGE $content
            """,
            {
                "profile_id": ensure_record_id(str(rows[0]["id"])),
                "content": content,
            },
        )
    else:
        result = await repo_query(
            """
            CREATE source_profile CONTENT $content
            """,
            {"content": content},
        )

    row = result[0] if result else {}
    return KBookSourceProfileResponse(
        source_id=source_id,
        module_id=str(row["module"]) if row.get("module") else module_id,
        document_type_id=(
            str(row["document_type"]) if row.get("document_type") else document_type_id
        ),
        business_version=row.get("business_version", business_version),
        status_id=str(row["status"]) if row.get("status") else status_id,
        updated=str(row["updated"]) if row.get("updated") else None,
    )


async def replace_source_tags(
    source_id: str,
    tag_ids: list[str],
) -> KBookSourceTagsResponse:
    """Replace SourceTag rows for a source after full validation."""
    await _assert_source_exists(source_id)
    unique_tag_ids = list(dict.fromkeys(tag_ids))
    tag_records = [
        await _validate_dictionary_item(tag_id, "tag")
        for tag_id in unique_tag_ids
    ]

    await repo_query(
        "DELETE source_tag WHERE in = $source_id",
        {"source_id": ensure_record_id(source_id)},
    )
    for tag_record in tag_records:
        await repo_query(
            """
            RELATE $source_id->source_tag->$tag_id
            CONTENT { created: time::now() }
            """,
            {
                "source_id": ensure_record_id(source_id),
                "tag_id": tag_record,
            },
        )

    return KBookSourceTagsResponse(
        source_id=source_id,
        tag_ids=unique_tag_ids,
    )
