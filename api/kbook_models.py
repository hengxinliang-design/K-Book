"""Pydantic models for K-Book-specific API endpoints."""

from pydantic import BaseModel, Field


class KBookUploadConfigResponse(BaseModel):
    """Upload configuration used by the K-Book upload wizard."""

    max_file_size_mb: int = Field(..., ge=1)
    max_files_per_batch: int = Field(..., ge=1)
    accept: str
    format_summary: str
    extensions: list[str]


class KBookDictionaryTypeResponse(BaseModel):
    """Dictionary type exposed to K-Book management and upload UI."""

    id: str
    code: str
    name: str
    system: bool
    description: str | None = None


class KBookDictionaryTypesResponse(BaseModel):
    """List response for dictionary types."""

    items: list[KBookDictionaryTypeResponse]


class KBookDictionaryItemResponse(BaseModel):
    """Dictionary item exposed to K-Book management and upload UI."""

    id: str
    type: str
    code: str
    name: str
    status: str
    description: str | None = None
    sort_order: int = 0
    color: str | None = None


class KBookDictionaryItemsResponse(BaseModel):
    """Paginated list response for dictionary items."""

    items: list[KBookDictionaryItemResponse]
    total: int
    limit: int
    offset: int
