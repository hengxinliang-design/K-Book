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


class KBookRemoveFileResponse(BaseModel):
    """Remove source from notebook response."""

    notebook_id: str
    source_id: str
    removed: bool


class KBookSourceSearchItem(BaseModel):
    """Search result for adding an existing source to a notebook."""

    source_id: str
    title: str | None = None
    original_filename: str | None = None
    tags: list[KBookFileDictionaryValue] = Field(default_factory=list)
    profile: KBookFileProfileValue = Field(default_factory=KBookFileProfileValue)
    shared_notebook_count: int = 0


class KBookSourceSearchResponse(BaseModel):
    """Paginated existing source search response."""

    items: list[KBookSourceSearchItem]
    total: int
    limit: int
    offset: int


class KBookAddExistingSourceRequest(BaseModel):
    """Add an existing source to a notebook."""

    source_id: str
    folder_id: str | None = None


class KBookAddExistingSourceResponse(BaseModel):
    """Add existing source to notebook response."""

    source_id: str
    reference_id: str | None = None
    notebook_id: str
    folder_id: str | None = None
    already_exists: bool = False


class KBookRecordSummary(BaseModel):
    """Small record summary used in K-Book notebook responses."""

    id: str
    name: str


class KBookNotebookItem(BaseModel):
    """K-Book notebook list item with business scope metadata."""

    id: str
    name: str
    description: str | None = None
    customer: KBookRecordSummary | None = None
    project: KBookRecordSummary | None = None
    ln_versions: list[KBookRecordSummary] = Field(default_factory=list)
    scope: str | None = None
    source_count: int = 0
    created: str | None = None
    updated: str | None = None


class KBookNotebooksResponse(BaseModel):
    """Paginated K-Book notebook list response."""

    items: list[KBookNotebookItem]
    total: int
    limit: int
    offset: int


class KBookNotebookUpdateRequest(BaseModel):
    """Update K-Book notebook business scope metadata."""

    name: str | None = None
    description: str | None = None
    customer_id: str | None = None
    project_id: str | None = None
    ln_version_ids: list[str] | None = None
    scope: str | None = None


class KBookSourceTitleUpdateRequest(BaseModel):
    """Update a source display title."""

    title: str


class KBookSourceTitleResponse(BaseModel):
    """Source title update response."""

    source_id: str
    title: str
    updated: str | None = None


class KBookSourceProfileUpdateRequest(BaseModel):
    """Update source business metadata."""

    module_id: str | None = None
    document_type_id: str | None = None
    business_version: str | None = None
    status_id: str | None = None


class KBookSourceProfileResponse(BaseModel):
    """Source business metadata update response."""

    source_id: str
    module_id: str | None = None
    document_type_id: str | None = None
    business_version: str | None = None
    status_id: str | None = None
    updated: str | None = None


class KBookSourceTagsUpdateRequest(BaseModel):
    """Replace source tags request."""

    tag_ids: list[str] = Field(default_factory=list)


class KBookSourceTagsResponse(BaseModel):
    """Source tags update response."""

    source_id: str
    tag_ids: list[str]
    updated: str | None = None


class KBookUploadBatchFileInput(BaseModel):
    """JSON-testable file descriptor for upload batch prevalidation."""

    filename: str
    size: int | None = None


class KBookUploadBatchItemInput(BaseModel):
    """Per-file upload batch business metadata."""

    client_file_id: str
    filename: str
    title: str
    folder_id: str | None = None
    tag_ids: list[str] = Field(default_factory=list)
    module_id: str | None = None
    document_type_id: str | None = None
    business_version: str | None = None
    status_id: str | None = None


class KBookUploadBatchCreateRequest(BaseModel):
    """JSON-testable upload batch create request."""

    notebook_id: str
    files: list[KBookUploadBatchFileInput]
    items: list[KBookUploadBatchItemInput]
    async_processing: bool = True
    embed: bool = True


class KBookUploadBatchItemResponse(BaseModel):
    """Upload batch item status response."""

    client_file_id: str
    filename: str
    status: str
    source_id: str | None = None
    reference_id: str | None = None
    error: dict | None = None


class KBookUploadBatchResponse(BaseModel):
    """Upload batch status response."""

    batch_id: str
    status: str
    total: int
    accepted: int | None = None
    rejected: int | None = None
    queued: int | None = None
    processing: int | None = None
    ready: int | None = None
    failed: int | None = None
    items: list[KBookUploadBatchItemResponse]
