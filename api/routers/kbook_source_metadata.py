"""K-Book source title, profile, and tag editing routes."""

from fastapi import APIRouter

from api.kbook_errors import kbook_http_error
from api.kbook_models import (
    KBookSourceProfileResponse,
    KBookSourceProfileUpdateRequest,
    KBookSourceTagsResponse,
    KBookSourceTagsUpdateRequest,
    KBookSourceTitleResponse,
    KBookSourceTitleUpdateRequest,
)
from api.kbook_services.source_metadata import (
    SourceMetadataValidationError,
    replace_source_tags,
    update_source_profile,
    update_source_title,
)

router = APIRouter()


def _source_metadata_error(exc: SourceMetadataValidationError):
    return kbook_http_error(
        exc,
        not_found_codes={"source_not_found"},
    )


@router.patch(
    "/sources/{source_id}/title",
    response_model=KBookSourceTitleResponse,
)
async def update_kbook_source_title(
    source_id: str,
    request: KBookSourceTitleUpdateRequest,
) -> KBookSourceTitleResponse:
    """Update a source display title without relearning."""
    try:
        return await update_source_title(source_id, request.title)
    except SourceMetadataValidationError as exc:
        raise _source_metadata_error(exc) from exc


@router.put(
    "/sources/{source_id}/profile",
    response_model=KBookSourceProfileResponse,
)
async def update_kbook_source_profile(
    source_id: str,
    request: KBookSourceProfileUpdateRequest,
) -> KBookSourceProfileResponse:
    """Update source business metadata without relearning."""
    try:
        return await update_source_profile(
            source_id,
            module_id=request.module_id,
            document_type_id=request.document_type_id,
            business_version=request.business_version,
            status_id=request.status_id,
        )
    except SourceMetadataValidationError as exc:
        raise _source_metadata_error(exc) from exc


@router.put(
    "/sources/{source_id}/tags",
    response_model=KBookSourceTagsResponse,
)
async def update_kbook_source_tags(
    source_id: str,
    request: KBookSourceTagsUpdateRequest,
) -> KBookSourceTagsResponse:
    """Replace source tags without relearning."""
    try:
        return await replace_source_tags(source_id, request.tag_ids)
    except SourceMetadataValidationError as exc:
        raise _source_metadata_error(exc) from exc
