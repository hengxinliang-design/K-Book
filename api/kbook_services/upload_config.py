"""Upload configuration for the K-Book upload wizard."""

from api.kbook_models import KBookUploadConfigResponse

KBOOK_SUPPORTED_UPLOAD_EXTENSIONS = [
    "pdf",
    "doc",
    "docx",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "txt",
    "md",
    "epub",
    "html",
    "mp4",
    "avi",
    "mov",
    "wmv",
    "mp3",
    "wav",
    "m4a",
    "aac",
    "jpg",
    "jpeg",
    "png",
    "tiff",
    "zip",
    "tar",
    "gz",
]

KBOOK_UPLOAD_FORMAT_SUMMARY = (
    "PDF、Word、PPT、Excel、文本、Markdown、网页、图片、音视频、压缩包等"
)
KBOOK_MAX_FILE_SIZE_MB = 100
KBOOK_MAX_FILES_PER_BATCH = 50


def get_upload_accept() -> str:
    """Return the HTML file input accept string for supported upload extensions."""
    return ",".join(f".{extension}" for extension in KBOOK_SUPPORTED_UPLOAD_EXTENSIONS)


def get_upload_config() -> KBookUploadConfigResponse:
    """Return the upload wizard configuration from a single backend source."""
    return KBookUploadConfigResponse(
        max_file_size_mb=KBOOK_MAX_FILE_SIZE_MB,
        max_files_per_batch=KBOOK_MAX_FILES_PER_BATCH,
        accept=get_upload_accept(),
        format_summary=KBOOK_UPLOAD_FORMAT_SUMMARY,
        extensions=KBOOK_SUPPORTED_UPLOAD_EXTENSIONS,
    )


def is_supported_upload_extension(filename: str) -> bool:
    """Return whether a filename has an extension supported by K-Book uploads."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return extension in KBOOK_SUPPORTED_UPLOAD_EXTENSIONS
