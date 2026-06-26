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


class KBookDictionaryItemCreateRequest(BaseModel):
    """Create dictionary item request."""

    type: str
    code: str
    name: str
    description: str | None = None
    sort_order: int = 0
    color: str | None = None


class KBookDictionaryItemUpdateRequest(BaseModel):
    """Update dictionary item request."""

    code: str | None = None
    name: str | None = None
    description: str | None = None
    status: str | None = None
    sort_order: int | None = None
    color: str | None = None


class KBookFolderNode(BaseModel):
    """Folder node for the K-Book notebook folder tree."""

    id: str
    name: str
    description: str | None = None
    parent: str | None = None
    sort_order: int = 0
    source_count: int = 0
    children: list["KBookFolderNode"] = Field(default_factory=list)


class KBookFolderTreeResponse(BaseModel):
    """Folder tree response for a notebook."""

    notebook_id: str
    items: list[KBookFolderNode]


class KBookFolderCreateRequest(BaseModel):
    """Create folder request."""

    parent: str | None = None
    name: str
    description: str | None = None
    sort_order: int = 0


class KBookFolderUpdateRequest(BaseModel):
    """Update folder request."""

    name: str | None = None
    description: str | None = None
    sort_order: int | None = None


class KBookFolderMoveRequest(BaseModel):
    """Move folder request."""

    parent: str | None = None
    sort_order: int | None = None


class KBookFolderResponse(BaseModel):
    """Folder write response."""

    id: str
    notebook_id: str
    parent: str | None = None
    name: str
    description: str | None = None
    sort_order: int = 0
    created: str | None = None
    updated: str | None = None


class KBookFileDictionaryValue(BaseModel):
    """Small dictionary value embedded in file list responses."""

    id: str
    name: str


class KBookFileFolderValue(BaseModel):
    """Folder location embedded in file list responses."""

    id: str
    path: str


class KBookFileProfileValue(BaseModel):
    """Source profile embedded in file list responses."""

    module: KBookFileDictionaryValue | None = None
    document_type: KBookFileDictionaryValue | None = None
    business_version: str | None = None
    status: KBookFileDictionaryValue | None = None


class KBookFileProcessingValue(BaseModel):
    """Processing state embedded in file list responses."""

    status: str
    embedded: bool = False
    error: str | None = None


class KBookFileListItem(BaseModel):
    """File row for a K-Book notebook file list."""

    source_id: str
    reference_id: str
    title: str | None = None
    original_filename: str | None = None
    folder: KBookFileFolderValue | None = None
    tags: list[KBookFileDictionaryValue] = Field(default_factory=list)
    profile: KBookFileProfileValue = Field(default_factory=KBookFileProfileValue)
    processing: KBookFileProcessingValue
    created: str | None = None
    updated: str | None = None


class KBookFileListResponse(BaseModel):
    """Paginated K-Book file list response."""

    items: list[KBookFileListItem]
    total: int
    limit: int
    offset: int


class KBookFileDetailResponse(KBookFileListItem):
    """K-Book file detail response."""

    shared_notebook_count: int = 0
    global_metadata_warning: bool = False
    full_text_available: bool = False


class KBookMoveFileRequest(BaseModel):
    """Move a file to another folder in the current notebook."""

    folder_id: str | None = None
