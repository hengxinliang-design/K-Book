"""Pydantic models for K-Book-specific API endpoints."""

from pydantic import BaseModel, Field


class KBookUploadConfigResponse(BaseModel):
    """Upload configuration used by the K-Book upload wizard."""

    max_file_size_mb: int = Field(..., ge=1)
    max_files_per_batch: int = Field(..., ge=1)
    accept: str
    format_summary: str
    extensions: list[str]
