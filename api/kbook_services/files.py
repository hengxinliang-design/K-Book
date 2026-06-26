"""File list and file location service for K-Book."""

from dataclasses import dataclass, field
from typing import Any

from api.kbook_models import (
    KBookFileDetailResponse,
    KBookFileDictionaryValue,
    KBookFileFolderValue,
    KBookFileListItem,
    KBookFileListResponse,
    KBookFileProcessingValue,
    KBookFileProfileValue,
    KBookRemoveFileResponse,
    KBookSourceSearchItem,
    KBookSourceSearchResponse,
    KBookAddExistingSourceResponse,
)
from api.kbook_services.folders import folder_belongs_to_notebook
from open_notebook.database.repository import ensure_record_id, repo_query

FILE_SORT_FIELDS = {"updated", "title"}
FILE_SORT_ORDERS = {"asc", "desc"}


class FileValidationError(ValueError):
    """Raised when a file list or file location operation is invalid."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass
class KBookFileFilters:
    """Filters for K-Book notebook file lists."""

    folder_id: str | None = None
    tag_ids: list[str] = field(default_factory=list)
    module_id: str | None = None
    document_type_id: str | None = None
    status_id: str | None = None
    business_version: str | None = None
    keyword: str | None = None
    processing_status: str | None = None


def _record_id_or_none(record_id: str | None) -> Any:
    return ensure_record_id(record_id) if record_id else None


async def _record_exists(record_id: str) -> bool:
    rows = await repo_query(
        "SELECT id FROM $record_id LIMIT 1",
        {"record_id": ensure_record_id(record_id)},
    )
    return bool(rows)


async def _assert_notebook_exists(notebook_id: str) -> None:
    if not await _record_exists(notebook_id):
        raise FileValidationError(
            "notebook_not_found",
            "Notebook not found",
            {"notebook_id": notebook_id},
        )


async def _assert_source_exists(source_id: str) -> None:
    if not await _record_exists(source_id):
        raise FileValidationError(
            "source_not_found",
            "Source not found",
            {"source_id": source_id},
        )


def _dict_value(row: dict[str, Any] | None) -> KBookFileDictionaryValue | None:
    if not isinstance(row, dict):
        return None
    return KBookFileDictionaryValue(id=str(row.get("id", "")), name=row.get("name", ""))


def _processing_from_source(source: dict[str, Any]) -> KBookFileProcessingValue:
    embedded = bool(source.get("embedded", False))
    command = source.get("command")
    status = "ready" if embedded else "processing"
    error = None

    if isinstance(command, dict):
        command_status = command.get("status")
        if command_status:
            status = str(command_status)
        error = command.get("error_message")

    return KBookFileProcessingValue(status=status, embedded=embedded, error=error)


def _folder_path_from_rows(folder_id: str, folders: list[dict[str, Any]]) -> str:
    by_id = {str(row.get("id")): row for row in folders}
    names: list[str] = []
    current = folder_id
    seen: set[str] = set()

    while current and current in by_id and current not in seen:
        seen.add(current)
        row = by_id[current]
        names.append(row.get("name", ""))
        current = str(row["parent"]) if row.get("parent") else ""

    return "/".join(reversed([name for name in names if name]))


async def _list_folder_rows(notebook_id: str) -> list[dict[str, Any]]:
    return await repo_query(
        """
        SELECT id, parent, name
        FROM folder
        WHERE notebook = $notebook_id
        """,
        {"notebook_id": ensure_record_id(notebook_id)},
    )


async def resolve_folder_path(folder_id: str, notebook_id: str | None = None) -> str:
    """Resolve a folder path from root to folder."""
    if notebook_id:
        folders = await _list_folder_rows(notebook_id)
    else:
        folder = await repo_query(
            "SELECT notebook FROM $folder_id LIMIT 1",
            {"folder_id": ensure_record_id(folder_id)},
        )
        if not folder:
            return ""
        folders = await _list_folder_rows(str(folder[0]["notebook"]))
    return _folder_path_from_rows(folder_id, folders)


async def _list_references(notebook_id: str) -> list[dict[str, Any]]:
    return await repo_query(
        """
        SELECT id, in, out, folder, created, updated
        FROM reference
        WHERE out = $notebook_id
        ORDER BY updated DESC, id ASC
        FETCH in, folder
        """,
        {"notebook_id": ensure_record_id(notebook_id)},
    )


async def _source_reference_in_notebook(
    notebook_id: str,
    source_id: str,
) -> dict[str, Any] | None:
    rows = await repo_query(
        """
        SELECT id, folder
        FROM reference
        WHERE out = $notebook_id AND in = $source_id
        LIMIT 1
        """,
        {
            "notebook_id": ensure_record_id(notebook_id),
            "source_id": ensure_record_id(source_id),
        },
    )
    return rows[0] if rows else None


async def _get_profile(source_id: str) -> dict[str, Any] | None:
    rows = await repo_query(
        """
        SELECT source, module, document_type, business_version, status, original_filename
        FROM source_profile
        WHERE source = $source_id
        LIMIT 1
        FETCH module, document_type, status
        """,
        {"source_id": ensure_record_id(source_id)},
    )
    return rows[0] if rows else None


async def _get_tags(source_id: str) -> list[KBookFileDictionaryValue]:
    rows = await repo_query(
        """
        SELECT out
        FROM source_tag
        WHERE in = $source_id
        FETCH out
        """,
        {"source_id": ensure_record_id(source_id)},
    )
    tags = [_dict_value(row.get("out")) for row in rows]
    return [tag for tag in tags if tag is not None]


async def _is_embedded(source_id: str) -> bool:
    rows = await repo_query(
        "SELECT id FROM source_embedding WHERE source = $source_id LIMIT 1",
        {"source_id": ensure_record_id(source_id)},
    )
    return bool(rows)


async def _shared_notebook_count(source_id: str) -> int:
    rows = await repo_query(
        "SELECT count() AS total FROM reference WHERE in = $source_id GROUP ALL",
        {"source_id": ensure_record_id(source_id)},
    )
    return rows[0].get("total", 0) if rows else 0


async def _source_search_item_from_source(
    source: dict[str, Any],
) -> KBookSourceSearchItem:
    source_id = str(source.get("id", ""))
    profile = await _get_profile(source_id)
    tags = await _get_tags(source_id)

    profile_value = KBookFileProfileValue()
    original_filename = None
    if profile:
        profile_value = KBookFileProfileValue(
            module=_dict_value(profile.get("module")),
            document_type=_dict_value(profile.get("document_type")),
            business_version=profile.get("business_version"),
            status=_dict_value(profile.get("status")),
        )
        original_filename = profile.get("original_filename")

    return KBookSourceSearchItem(
        source_id=source_id,
        title=source.get("title"),
        original_filename=original_filename,
        tags=tags,
        profile=profile_value,
        shared_notebook_count=await _shared_notebook_count(source_id),
    )


def _source_from_reference(reference: dict[str, Any]) -> dict[str, Any]:
    source = reference.get("in")
    if not isinstance(source, dict):
        raise FileValidationError(
            "source_not_found",
            "Source not found for reference",
            {"reference_id": str(reference.get("id", ""))},
        )
    return source


async def _file_item_from_reference(
    reference: dict[str, Any],
    folder_paths: dict[str, str],
) -> KBookFileListItem:
    source = _source_from_reference(reference)
    source_id = str(source.get("id", ""))
    profile = await _get_profile(source_id)
    tags = await _get_tags(source_id)
    source["embedded"] = await _is_embedded(source_id)

    folder_value = None
    folder = reference.get("folder")
    if isinstance(folder, dict):
        folder_id = str(folder.get("id", ""))
        folder_value = KBookFileFolderValue(
            id=folder_id,
            path=folder_paths.get(folder_id, folder.get("name", "")),
        )

    profile_value = KBookFileProfileValue()
    original_filename = None
    if profile:
        profile_value = KBookFileProfileValue(
            module=_dict_value(profile.get("module")),
            document_type=_dict_value(profile.get("document_type")),
            business_version=profile.get("business_version"),
            status=_dict_value(profile.get("status")),
        )
        original_filename = profile.get("original_filename")

    return KBookFileListItem(
        source_id=source_id,
        reference_id=str(reference.get("id", "")),
        title=source.get("title"),
        original_filename=original_filename,
        folder=folder_value,
        tags=tags,
        profile=profile_value,
        processing=_processing_from_source(source),
        created=str(source["created"]) if source.get("created") else None,
        updated=str(source["updated"]) if source.get("updated") else None,
    )


def _matches_filters(item: KBookFileListItem, filters: KBookFileFilters) -> bool:
    if filters.folder_id == "root" and item.folder is not None:
        return False
    if filters.folder_id and filters.folder_id != "root":
        if item.folder is None or item.folder.id != filters.folder_id:
            return False
    if filters.tag_ids:
        item_tag_ids = {tag.id for tag in item.tags}
        if not item_tag_ids.intersection(filters.tag_ids):
            return False
    if filters.module_id and (
        item.profile.module is None or item.profile.module.id != filters.module_id
    ):
        return False
    if filters.document_type_id and (
        item.profile.document_type is None
        or item.profile.document_type.id != filters.document_type_id
    ):
        return False
    if filters.status_id and (
        item.profile.status is None or item.profile.status.id != filters.status_id
    ):
        return False
    if filters.business_version:
        version = item.profile.business_version or ""
        if filters.business_version.casefold() not in version.casefold():
            return False
    if filters.keyword:
        title = item.title or ""
        if filters.keyword.casefold() not in title.casefold():
            return False
    if filters.processing_status and item.processing.status != filters.processing_status:
        return False
    return True


def _sort_items(
    items: list[KBookFileListItem],
    sort_by: str,
    sort_order: str,
) -> list[KBookFileListItem]:
    if sort_by not in FILE_SORT_FIELDS:
        raise FileValidationError(
            "validation_failed",
            "Invalid sort field",
            {"sort_by": sort_by, "allowed": sorted(FILE_SORT_FIELDS)},
        )
    if sort_order not in FILE_SORT_ORDERS:
        raise FileValidationError(
            "validation_failed",
            "Invalid sort order",
            {"sort_order": sort_order, "allowed": sorted(FILE_SORT_ORDERS)},
        )

    reverse = sort_order == "desc"
    if sort_by == "title":
        return sorted(items, key=lambda item: (item.title or "").casefold(), reverse=reverse)
    return sorted(items, key=lambda item: item.updated or "", reverse=reverse)


async def list_notebook_files(
    notebook_id: str,
    filters: KBookFileFilters | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "updated",
    sort_order: str = "desc",
) -> KBookFileListResponse:
    """Return a filtered and paginated file list for a notebook."""
    filters = filters or KBookFileFilters()
    await _assert_notebook_exists(notebook_id)
    if filters.folder_id and filters.folder_id != "root":
        if not await folder_belongs_to_notebook(filters.folder_id, notebook_id):
            raise FileValidationError(
                "folder_not_found",
                "Folder not found in notebook",
                {"folder_id": filters.folder_id, "notebook_id": notebook_id},
            )

    folder_rows = await _list_folder_rows(notebook_id)
    folder_paths = {
        str(row.get("id")): _folder_path_from_rows(str(row.get("id")), folder_rows)
        for row in folder_rows
    }
    references = await _list_references(notebook_id)
    items = [
        await _file_item_from_reference(reference, folder_paths)
        for reference in references
    ]
    filtered = [item for item in items if _matches_filters(item, filters)]
    sorted_items = _sort_items(filtered, sort_by, sort_order)
    page = sorted_items[offset : offset + limit]
    return KBookFileListResponse(
        items=page,
        total=len(filtered),
        limit=limit,
        offset=offset,
    )


async def get_notebook_file_detail(
    notebook_id: str,
    source_id: str,
) -> KBookFileDetailResponse:
    """Return file detail for a source in a notebook."""
    await _assert_notebook_exists(notebook_id)
    references = await repo_query(
        """
        SELECT id, in, out, folder, created, updated
        FROM reference
        WHERE out = $notebook_id AND in = $source_id
        LIMIT 1
        FETCH in, folder
        """,
        {
            "notebook_id": ensure_record_id(notebook_id),
            "source_id": ensure_record_id(source_id),
        },
    )
    if not references:
        raise FileValidationError(
            "source_not_found",
            "Source is not linked to notebook",
            {"notebook_id": notebook_id, "source_id": source_id},
        )

    folder_rows = await _list_folder_rows(notebook_id)
    folder_paths = {
        str(row.get("id")): _folder_path_from_rows(str(row.get("id")), folder_rows)
        for row in folder_rows
    }
    item = await _file_item_from_reference(references[0], folder_paths)
    source = _source_from_reference(references[0])
    shared_count = await _shared_notebook_count(source_id)
    return KBookFileDetailResponse(
        **item.model_dump(),
        shared_notebook_count=shared_count,
        global_metadata_warning=shared_count > 1,
        full_text_available=bool(source.get("full_text")),
    )


async def move_file_to_folder(
    notebook_id: str,
    source_id: str,
    folder_id: str | None,
) -> KBookFileDetailResponse:
    """Move a file to another folder inside the current notebook."""
    await _assert_notebook_exists(notebook_id)
    if folder_id and not await folder_belongs_to_notebook(folder_id, notebook_id):
        raise FileValidationError(
            "folder_not_found",
            "Folder not found in notebook",
            {"folder_id": folder_id, "notebook_id": notebook_id},
        )

    references = await repo_query(
        """
        SELECT id FROM reference
        WHERE out = $notebook_id AND in = $source_id
        LIMIT 1
        """,
        {
            "notebook_id": ensure_record_id(notebook_id),
            "source_id": ensure_record_id(source_id),
        },
    )
    if not references:
        raise FileValidationError(
            "source_not_found",
            "Source is not linked to notebook",
            {"notebook_id": notebook_id, "source_id": source_id},
        )

    await repo_query(
        """
        UPDATE $reference_id SET
            folder = $folder_id,
            updated = time::now()
        """,
        {
            "reference_id": ensure_record_id(str(references[0]["id"])),
            "folder_id": _record_id_or_none(folder_id),
        },
    )
    return await get_notebook_file_detail(notebook_id, source_id)


async def remove_file_from_notebook(
    notebook_id: str,
    source_id: str,
) -> KBookRemoveFileResponse:
    """Remove a source reference from a notebook without deleting the source."""
    await _assert_notebook_exists(notebook_id)
    reference = await _source_reference_in_notebook(notebook_id, source_id)
    if not reference:
        raise FileValidationError(
            "source_not_found",
            "Source is not linked to notebook",
            {"notebook_id": notebook_id, "source_id": source_id},
        )

    await repo_query(
        "DELETE $reference_id",
        {"reference_id": ensure_record_id(str(reference["id"]))},
    )
    return KBookRemoveFileResponse(
        notebook_id=notebook_id,
        source_id=source_id,
        removed=True,
    )


async def search_existing_sources(
    keyword: str | None = None,
    exclude_notebook_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> KBookSourceSearchResponse:
    """Search existing sources that can be added to a notebook."""
    normalized_keyword = keyword.strip() if keyword else None
    if exclude_notebook_id:
        await _assert_notebook_exists(exclude_notebook_id)

    where_sql = ""
    params: dict[str, Any] = {"keyword": normalized_keyword}
    if normalized_keyword:
        where_sql = """
        WHERE string::lowercase(title) CONTAINS string::lowercase($keyword)
        """

    rows = await repo_query(
        f"""
        SELECT id, title, created, updated
        FROM source
        {where_sql}
        ORDER BY updated DESC, title ASC
        """,
        params,
    )
    items = []
    for row in rows:
        source_id = str(row.get("id", ""))
        if exclude_notebook_id and await _source_reference_in_notebook(
            exclude_notebook_id,
            source_id,
        ):
            continue
        items.append(await _source_search_item_from_source(row))

    total = len(items)
    page = items[offset : offset + limit]
    return KBookSourceSearchResponse(
        items=page,
        total=total,
        limit=limit,
        offset=offset,
    )


async def add_existing_source_to_notebook(
    notebook_id: str,
    source_id: str,
    folder_id: str | None = None,
) -> KBookAddExistingSourceResponse:
    """Add an existing source to a notebook with optional folder placement."""
    await _assert_notebook_exists(notebook_id)
    await _assert_source_exists(source_id)
    if folder_id and not await folder_belongs_to_notebook(folder_id, notebook_id):
        raise FileValidationError(
            "folder_not_found",
            "Folder not found in notebook",
            {"folder_id": folder_id, "notebook_id": notebook_id},
        )

    reference = await _source_reference_in_notebook(notebook_id, source_id)
    if reference:
        folder = reference.get("folder")
        return KBookAddExistingSourceResponse(
            source_id=source_id,
            reference_id=str(reference.get("id", "")),
            notebook_id=notebook_id,
            folder_id=str(folder) if folder else None,
            already_exists=True,
        )

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
            "folder_id": _record_id_or_none(folder_id),
        },
    )
    reference_id = str(rows[0].get("id", "")) if rows else None
    return KBookAddExistingSourceResponse(
        source_id=source_id,
        reference_id=reference_id,
        notebook_id=notebook_id,
        folder_id=folder_id,
        already_exists=False,
    )
