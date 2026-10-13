"""Discover, validate, and apply forward-only SQL Server migrations."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_MIGRATIONS_PATH = Path(__file__).with_name("sql_migrations")
_MIGRATION_NAME = re.compile(r"^(?P<id>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$")
_GO_LINE = re.compile(r"^\s*GO\s*(?:--.*)?$", re.IGNORECASE)


class MigrationError(RuntimeError):
    """Base error raised for an invalid or failed database migration."""


class MigrationChecksumError(MigrationError):
    """Raised when an applied migration no longer matches its source file."""


class MigrationHistoryError(MigrationError):
    """Raised when database migration history is incomplete or inconsistent."""


class UnsupportedSchemaVersionError(MigrationError):
    """Raised when the database schema is newer than this application supports."""


@dataclass(frozen=True)
class Migration:
    """One immutable, ordered SQL migration."""

    migration_id: int
    name: str
    script: str
    checksum: str
    path: Path


@dataclass(frozen=True)
class AppliedMigration:
    """Migration identity already recorded by SQL Server."""

    migration_id: int
    name: str
    checksum: str


@dataclass(frozen=True)
class MigrationResult:
    """Summary of one migration-runner invocation."""

    applied_ids: tuple[int, ...]
    current_version: int


def discover_migrations(path: Path = DEFAULT_MIGRATIONS_PATH) -> tuple[Migration, ...]:
    """Load and checksum ordered migration files from *path*."""

    if not path.is_dir():
        raise MigrationHistoryError(f"Migration directory does not exist: {path}")

    migrations: list[Migration] = []
    for migration_path in sorted(path.glob("*.sql")):
        match = _MIGRATION_NAME.fullmatch(migration_path.name)
        if match is None:
            raise MigrationHistoryError(
                "Migration filenames must use NNNN_lowercase_name.sql: "
                f"{migration_path.name}"
            )
        script = migration_path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                migration_id=int(match.group("id")),
                name=match.group("name"),
                script=script,
                checksum=hashlib.sha256(script.encode("utf-8")).hexdigest(),
                path=migration_path,
            )
        )

    if not migrations:
        raise MigrationHistoryError(f"No SQL migrations were found in {path}")

    actual_ids = [migration.migration_id for migration in migrations]
    expected_ids = list(range(1, len(migrations) + 1))
    if actual_ids != expected_ids:
        raise MigrationHistoryError(
            "Migration IDs must be unique and contiguous starting at 0001; "
            f"found {actual_ids}"
        )
    return tuple(migrations)


def split_sql_batches(script: str) -> tuple[str, ...]:
    """Split a SQL Server script on standalone ``GO`` batch separators."""

    batches: list[str] = []
    current_lines: list[str] = []
    for line in script.splitlines():
        if _GO_LINE.fullmatch(line):
            batch = "\n".join(current_lines).strip()
            if batch:
                batches.append(batch)
            current_lines = []
        else:
            current_lines.append(line)
    final_batch = "\n".join(current_lines).strip()
    if final_batch:
        batches.append(final_batch)
    return tuple(batches)


class MigrationRunner:
    """Apply validated migrations using a DB-API-compatible connection."""

    def __init__(
        self,
        connection: Any,
        migrations: Iterable[Migration],
        application_version: str,
    ) -> None:
        self._connection = connection
        self._migrations = tuple(migrations)
        self._application_version = application_version
        if not self._migrations:
            raise MigrationHistoryError("At least one migration is required")

    def pending_migrations(self) -> tuple[Migration, ...]:
        """Validate history and return migrations not yet applied."""

        applied = self._read_applied_migrations()
        available = {
            migration.migration_id: migration for migration in self._migrations
        }
        newest_supported = max(available)

        unknown_ids = sorted(set(applied) - set(available))
        if unknown_ids:
            if max(unknown_ids) > newest_supported:
                raise UnsupportedSchemaVersionError(
                    "Database schema version "
                    f"{max(unknown_ids)} is newer than supported version "
                    f"{newest_supported}"
                )
            raise MigrationHistoryError(
                f"Database records unknown migration IDs: {unknown_ids}"
            )

        applied_ids = sorted(applied)
        if applied_ids and applied_ids != list(range(1, max(applied_ids) + 1)):
            raise MigrationHistoryError(
                f"Database migration history has gaps: {applied_ids}"
            )

        for migration_id, recorded in applied.items():
            expected = available[migration_id]
            if recorded.name != expected.name:
                raise MigrationHistoryError(
                    f"Migration {migration_id:04d} name changed from "
                    f"{recorded.name!r} to {expected.name!r}"
                )
            if recorded.checksum.lower() != expected.checksum.lower():
                raise MigrationChecksumError(
                    f"Migration {migration_id:04d}_{expected.name}.sql was modified "
                    "after it was applied"
                )

        return tuple(
            migration
            for migration in self._migrations
            if migration.migration_id not in applied
        )

    def apply(self) -> MigrationResult:
        """Apply all pending migrations, committing each migration atomically."""

        pending = self.pending_migrations()
        applied_ids: list[int] = []
        for migration in pending:
            cursor = self._connection.cursor()
            try:
                for batch in split_sql_batches(migration.script):
                    cursor.execute(batch)
                cursor.execute(
                    """
                    INSERT INTO dbo.SCHEMA_MIGRATIONS (
                        migration_id,
                        migration_name,
                        script_checksum,
                        application_version
                    ) VALUES (?, ?, ?, ?)
                    """,
                    migration.migration_id,
                    migration.name,
                    migration.checksum,
                    self._application_version,
                )
                self._connection.commit()
                applied_ids.append(migration.migration_id)
            except Exception as exc:
                self._connection.rollback()
                raise MigrationError(
                    f"Failed to apply migration {migration.path.name}: {exc}"
                ) from exc
            finally:
                cursor.close()

        return MigrationResult(
            applied_ids=tuple(applied_ids),
            current_version=max(migration.migration_id for migration in self._migrations),
        )

    def _read_applied_migrations(self) -> dict[int, AppliedMigration]:
        cursor = self._connection.cursor()
        try:
            exists = cursor.execute(
                "SELECT OBJECT_ID(N'dbo.SCHEMA_MIGRATIONS', N'U')"
            ).fetchone()[0]
            if exists is None:
                return {}
            rows = cursor.execute(
                """
                SELECT migration_id, migration_name, script_checksum
                FROM dbo.SCHEMA_MIGRATIONS
                ORDER BY migration_id
                """
            ).fetchall()
            return {
                int(row[0]): AppliedMigration(
                    migration_id=int(row[0]),
                    name=str(row[1]),
                    checksum=str(row[2]),
                )
                for row in rows
            }
        finally:
            cursor.close()
