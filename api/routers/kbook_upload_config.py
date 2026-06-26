"""K-Book upload configuration routes."""

from fastapi import APIRouter

from api.kbook_models import KBookUploadConfigResponse
from api.kbook_services.upload_config import get_upload_config

router = APIRouter()


@router.get("/upload/config", response_model=KBookUploadConfigResponse)
async def get_kbook_upload_config() -> KBookUploadConfigResponse:
    """Return supported file formats and upload limits for the K-Book wizard."""
    return get_upload_config()
