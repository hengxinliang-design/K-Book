"""K-Book notebook metadata service."""

from typing import Any

from api.kbook_models import (
    KBookNotebookItem,
    KBookNotebooksResponse,
    KBookRecordSummary,
)
from api.kbook_services.dictionary import validate_dictionary_item
from open_notebook.database.repository import ensure_record_id, repo_query


class NotebookMetadataValidationError(ValueError):
    """Raised when a K-Book notebook metadata operation is invalid."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _record_summary(row: Any) -> KBookRecordSummary | None:
    if not isinstance(row, dict):
        return None
    return KBookRecordSummary(id=str(row.get("id", "")), name=row.get("name", ""))


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


async def _record_exists(record_id: str) -> bool:
    rows = await repo_query(
        "SELECT id FROM $record_id LIMIT 1",
        {"record_id": ensure_record_id(record_id)},
    )
    return bool(rows)


async def _assert_notebook_exists(notebook_id: str) -> None:
    if not await _record_exists(notebook_id):
        raise NotebookMetadataValidationError(
            "notebook_not_found",
            "Notebook not found",
            {"notebook_id": notebook_id},
        )


async def _get_customer(customer_id: str | None) -> dict[str, Any] | None:
    if not customer_id:
        return None
    rows = await repo_query(
        "SELECT id, name FROM $customer_id LIMIT 1",
        {"customer_id": ensure_record_id(customer_id)},
    )
    if not rows:
        raise NotebookMetadataValidationError(
            "customer_not_found",
            "Customer not found",
            {"customer_id": customer_id},
        )
    return rows[0]


async def _get_project(project_id: str | None) -> dict[str, Any] | None:
    if not project_id:
        return None
    rows = await repo_query(
        """
        SELECT id, name, customer
        FROM $project_id
        LIMIT 1
        FETCH customer
        """,
        {"project_id": ensure_record_id(project_id)},
    )
    if not rows:
        raise NotebookMetadataValidationError(
            "project_not_found",
            "Project not found",
            {"project_id": project_id},
        )
    return rows[0]


def _assert_project_customer(
    project: dict[str, Any] | None,
    customer_id: str | None,
) -> None:
    if not project or not customer_id:
        return
    customer = project.get("customer")
    project_customer_id = str(customer.get("id")) if isinstance(customer, dict) else str(customer)
    if project_customer_id != customer_id:
        raise NotebookMetadataValidationError(
            "validation_failed",
            "Project does not belong to customer",
            {"project_id": str(project.get("id")), "customer_id": customer_id},
        )


async def _validate_ln_versions(ln_version_ids: list[str]) -> list[Any]:
    records = []
    for ln_version_id in list(dict.fromkeys(ln_version_ids)):
        try:
            await validate_dictionary_item(
                ln_version_id,
                expected_type="ln_version",
                require_active=True,
            )
        except ValueError as exc:
            message = str(exc)
            code = "validation_failed"
            if "inactive" in message:
                code = "dictionary_item_inactive"
            elif "expected" in message:
                code = "dictionary_type_mismatch"
            raise NotebookMetadataValidationError(
                code,
                message,
                {"item_id": ln_version_id, "expected_type": "ln_version"},
            ) from exc
        records.append(ensure_record_id(ln_version_id))
    return records


async def _ln_versions_for_notebook(notebook_id: str) -> list[KBookRecordSummary]:
    rows = await repo_query(
        """
        SELECT out
        FROM notebook_ln_version
        WHERE in = $notebook_id
        FETCH out
        """,
        {"notebook_id": ensure_record_id(notebook_id)},
    )
    versions = [_record_summary(row.get("out")) for row in rows]
    return [version for version in versions if version is not None]


async def _source_count(notebook_id: str) -> int:
    rows = await repo_query(
        "SELECT count() AS total FROM reference WHERE out = $notebook_id GROUP ALL",
        {"notebook_id": ensure_record_id(notebook_id)},
    )
    return rows[0].get("total", 0) if rows else 0


async def _notebook_item_from_row(row: dict[str, Any]) -> KBookNotebookItem:
    notebook_id = str(row.get("id", ""))
    return KBookNotebookItem(
        id=notebook_id,
        name=row.get("name", ""),
        description=row.get("description"),
        customer=_record_summary(row.get("customer")),
        project=_record_summary(row.get("project")),
        ln_versions=await _ln_versions_for_notebook(notebook_id),
        scope=row.get("scope"),
        source_count=await _source_count(notebook_id),
        created=str(row["created"]) if row.get("created") else None,
        updated=str(row["updated"]) if row.get("updated") else None,
    )


async def list_kbook_notebooks(
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> KBookNotebooksResponse:
    """List K-Book notebooks with business scope metadata."""
    normalized_keyword = _clean_optional_text(keyword)
    where_sql = ""
    params: dict[str, Any] = {
        "keyword": normalized_keyword,
        "limit": limit,
        "offset": offset,
    }
    if normalized_keyword:
        where_sql = """
        WHERE string::lowercase(name) CONTAINS string::lowercase($keyword)
            OR string::lowercase(description) CONTAINS string::lowercase($keyword)
        """

    rows = await repo_query(
        f"""
        SELECT id, name, description, customer, project, scope, created, updated
        FROM notebook
        {where_sql}
        ORDER BY updated DESC, name ASC
        LIMIT $limit START $offset
        FETCH customer, project
        """,
        params,
    )
    count_rows = await repo_query(
        f"""
        SELECT count() AS total
        FROM notebook
        {where_sql}
        GROUP ALL
        """,
        params,
    )
    return KBookNotebooksResponse(
        items=[await _notebook_item_from_row(row) for row in rows],
        total=count_rows[0].get("total", 0) if count_rows else 0,
        limit=limit,
        offset=offset,
    )


async def update_kbook_notebook(
    notebook_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    customer_id: str | None = None,
    project_id: str | None = None,
    ln_version_ids: list[str] | None = None,
    scope: str | None = None,
) -> KBookNotebookItem:
    """Update K-Book notebook metadata and replace LN versions when provided."""
    await _assert_notebook_exists(notebook_id)
    customer = await _get_customer(customer_id)
    project = await _get_project(project_id)
    _assert_project_customer(project, customer_id)
    ln_version_records = (
        await _validate_ln_versions(ln_version_ids)
        if ln_version_ids is not None
        else None
    )

    patch: dict[str, Any] = {}
    if name is not None:
        cleaned_name = _clean_optional_text(name)
        if not cleaned_name:
            raise NotebookMetadataValidationError(
                "validation_failed",
                "Notebook name cannot be empty",
                {"field": "name"},
            )
        patch["name"] = cleaned_name
    if description is not None:
        patch["description"] = description
    if customer_id is not None:
        patch["customer"] = ensure_record_id(customer_id) if customer else None
    if project_id is not None:
        patch["project"] = ensure_record_id(project_id) if project else None
    if scope is not None:
        patch["scope"] = scope

    if patch:
        rows = await repo_query(
            """
            UPDATE $notebook_id MERGE $patch
            FETCH customer, project
            """,
            {
                "notebook_id": ensure_record_id(notebook_id),
                "patch": patch,
            },
        )
        notebook_row = rows[0]
    else:
        rows = await repo_query(
            """
            SELECT id, name, description, customer, project, scope, created, updated
            FROM $notebook_id
            FETCH customer, project
            """,
            {"notebook_id": ensure_record_id(notebook_id)},
        )
        notebook_row = rows[0]

    if ln_version_records is not None:
        await repo_query(
            "DELETE notebook_ln_version WHERE in = $notebook_id",
            {"notebook_id": ensure_record_id(notebook_id)},
        )
        for ln_version_record in ln_version_records:
            await repo_query(
                """
                RELATE $notebook_id->notebook_ln_version->$ln_version_id
                CONTENT { created: time::now() }
                """,
                {
                    "notebook_id": ensure_record_id(notebook_id),
                    "ln_version_id": ln_version_record,
                },
            )

    return await _notebook_item_from_row(notebook_row)
