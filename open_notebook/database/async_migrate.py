"""
Async migration system for SurrealDB using the official Python client.
Based on patterns from sblpy migration system.
"""

from collections import Counter
from typing import Any, List

from loguru import logger

from .repository import db_connection, ensure_record_id, repo_query


class AsyncMigration:
    """
    Handles individual migration operations with async support.
    """

    def __init__(self, sql: str) -> None:
        """Initialize migration with SQL content."""
        self.sql = sql

    @classmethod
    def from_file(cls, file_path: str) -> "AsyncMigration":
        """Create migration from SQL file."""
        with open(file_path, "r", encoding="utf-8") as file:
            raw_content = file.read()
            # Clean up SQL content
            lines = []
            for line in raw_content.split("\n"):
                line = line.strip()
                if line and not line.startswith("--"):
                    lines.append(line)
            sql = " ".join(lines)
            return cls(sql)

    async def run(self, bump: bool = True) -> None:
        """Run the migration."""
        try:
            async with db_connection() as connection:
                await connection.query(self.sql)

            if bump:
                await bump_version()
            else:
                await lower_version()

        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            raise


class AsyncMigrationRunner:
    """
    Handles running multiple migrations in sequence.
    """

    def __init__(
        self,
        up_migrations: List[AsyncMigration],
        down_migrations: List[AsyncMigration],
    ) -> None:
        """Initialize runner with migration lists."""
        self.up_migrations = up_migrations
        self.down_migrations = down_migrations

    async def run_all(self) -> None:
        """Run all pending up migrations."""
        current_version = await get_latest_version()

        for i in range(current_version, len(self.up_migrations)):
            logger.info(f"Running migration {i + 1}")
            if i + 1 == 16:
                await validate_migration_16_preconditions()
            await self.up_migrations[i].run(bump=True)

    async def run_one_up(self) -> None:
        """Run one up migration."""
        current_version = await get_latest_version()

        if current_version < len(self.up_migrations):
            logger.info(f"Running migration {current_version + 1}")
            if current_version + 1 == 16:
                await validate_migration_16_preconditions()
            await self.up_migrations[current_version].run(bump=True)

    async def run_one_down(self) -> None:
        """Run one down migration."""
        current_version = await get_latest_version()

        if current_version > 0:
            logger.info(f"Rolling back migration {current_version}")
            await self.down_migrations[current_version - 1].run(bump=False)


class AsyncMigrationManager:
    """
    Main migration manager with async support.
    """

    def __init__(self):
        """Initialize migration manager."""
        self.up_migrations = [
            AsyncMigration.from_file("open_notebook/database/migrations/1.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/2.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/3.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/4.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/5.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/6.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/7.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/8.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/9.surrealql"),
            AsyncMigration.from_file("open_notebook/database/migrations/10.surrealql"),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/11.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/12.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/13.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/14.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/15.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/16.surrealql"
            ),
        ]
        self.down_migrations = [
            AsyncMigration.from_file(
                "open_notebook/database/migrations/1_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/2_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/3_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/4_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/5_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/6_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/7_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/8_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/9_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/10_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/11_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/12_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/13_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/14_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/15_down.surrealql"
            ),
            AsyncMigration.from_file(
                "open_notebook/database/migrations/16_down.surrealql"
            ),
        ]
        self.runner = AsyncMigrationRunner(
            up_migrations=self.up_migrations,
            down_migrations=self.down_migrations,
        )

    async def get_current_version(self) -> int:
        """Get current database version."""
        return await get_latest_version()

    async def needs_migration(self) -> bool:
        """Check if migration is needed."""
        current_version = await self.get_current_version()
        return current_version < len(self.up_migrations)

    async def run_migration_up(self):
        """Run all pending migrations."""
        current_version = await self.get_current_version()
        logger.info(f"Current version before migration: {current_version}")

        if await self.needs_migration():
            try:
                await self.runner.run_all()
                new_version = await self.get_current_version()
                logger.info(f"Migration successful. New version: {new_version}")
            except Exception as e:
                logger.error(f"Migration failed: {str(e)}")
                raise
        else:
            logger.info("Database is already at the latest version")


# Database version management functions
async def get_latest_version() -> int:
    """Get the latest version from the migrations table."""
    try:
        versions = await get_all_versions()
        if not versions:
            return 0
        return max(version["version"] for version in versions)
    except Exception:
        # If migrations table doesn't exist, we're at version 0
        return 0


async def get_all_versions() -> List[dict]:
    """Get all versions from the migrations table."""
    try:
        result = await repo_query("SELECT * FROM _sbl_migrations ORDER BY version;")
        return result
    except Exception:
        # If table doesn't exist, return empty list
        return []


def _stringify_record_id(value: Any) -> str:
    """Convert SurrealDB record IDs to a stable string for diagnostics."""
    return str(value)


async def _record_exists(record_id: Any) -> bool:
    """Return whether a SurrealDB record exists."""
    try:
        normalized_record_id = ensure_record_id(record_id)
    except Exception:
        return False

    result = await repo_query(
        "SELECT * FROM $record_id;", {"record_id": normalized_record_id}
    )
    return bool(result)


async def validate_migration_16_preconditions() -> None:
    """
    Validate existing reference rows before adding the K-Book unique index.

    Migration 16 adds a unique index on reference(in, out). Existing duplicate or
    dangling reference rows need explicit cleanup instead of silent guessing.
    """
    references = await repo_query("SELECT id, in, out FROM reference;")
    if not references:
        return

    reference_pairs = [
        (_stringify_record_id(row.get("in")), _stringify_record_id(row.get("out")))
        for row in references
    ]
    duplicate_pairs = {
        pair: total for pair, total in Counter(reference_pairs).items() if total > 1
    }
    if duplicate_pairs:
        details = "; ".join(
            f"source={source_id}, notebook={notebook_id}, total={total}"
            for (source_id, notebook_id), total in sorted(duplicate_pairs.items())
        )
        raise RuntimeError(
            "Migration 16 preflight failed: duplicate reference(in, out) rows "
            f"must be cleaned before adding the unique index. {details}"
        )

    dangling_references = []
    for row in references:
        source_id = row.get("in")
        notebook_id = row.get("out")
        source_exists = await _record_exists(source_id)
        notebook_exists = await _record_exists(notebook_id)
        if not source_exists or not notebook_exists:
            dangling_references.append(
                {
                    "reference": _stringify_record_id(row.get("id")),
                    "source": _stringify_record_id(source_id),
                    "source_exists": source_exists,
                    "notebook": _stringify_record_id(notebook_id),
                    "notebook_exists": notebook_exists,
                }
            )

    if dangling_references:
        details = "; ".join(
            (
                f"reference={item['reference']}, source={item['source']} "
                f"(exists={item['source_exists']}), notebook={item['notebook']} "
                f"(exists={item['notebook_exists']})"
            )
            for item in dangling_references
        )
        raise RuntimeError(
            "Migration 16 preflight failed: dangling reference rows must be "
            f"cleaned before migration. {details}"
        )


async def bump_version() -> None:
    """Bump the version by adding a new entry to migrations table."""
    current_version = await get_latest_version()
    new_version = current_version + 1

    await repo_query(
        "CREATE type::thing('_sbl_migrations', $version) SET version = $version, applied_at = time::now();",
        {"version": new_version},
    )


async def lower_version() -> None:
    """Lower the version by removing the latest entry from migrations table."""
    current_version = await get_latest_version()
    if current_version > 0:
        await repo_query(
            "DELETE type::thing('_sbl_migrations', $version);",
            {"version": current_version},
        )
