"""Discover and verify immutable runtime resources used by release tooling."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Sequence


class ReleaseResourceError(RuntimeError):
    """Raised when required release resources are missing or inconsistent."""


def discover_sql_migrations(source_directory: Path) -> tuple[Path, ...]:
    """Return all source SQL migrations in deterministic filename order."""

    source_directory = Path(source_directory)
    if not source_directory.is_dir():
        raise ReleaseResourceError(
            f"SQL migration source directory does not exist: {source_directory}"
        )

    migrations = tuple(
        sorted(source_directory.glob("*.sql"), key=lambda path: path.name)
    )
    if not migrations:
        raise ReleaseResourceError(
            f"No SQL migration files were found in: {source_directory}"
        )
    return migrations


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest for *path* without loading it all at once."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_packaged_sql_migrations(
    source_directory: Path,
    packaged_directory: Path,
) -> tuple[Path, ...]:
    """Require packaged migrations to exactly match the source SQL resources."""

    source_migrations = discover_sql_migrations(source_directory)
    packaged_directory = Path(packaged_directory)
    if not packaged_directory.is_dir():
        raise ReleaseResourceError(
            "Packaged SQL migration directory does not exist: "
            f"{packaged_directory}"
        )

    packaged_migrations = tuple(
        sorted(packaged_directory.glob("*.sql"), key=lambda path: path.name)
    )
    packaged_by_name = {path.name: path for path in packaged_migrations}

    for source_path in source_migrations:
        packaged_path = packaged_by_name.get(source_path.name)
        if packaged_path is None:
            raise ReleaseResourceError(
                f"Packaged SQL migration is missing: {source_path.name}"
            )
        if sha256_file(source_path) != sha256_file(packaged_path):
            raise ReleaseResourceError(
                f"Packaged SQL migration hash does not match source: "
                f"{source_path.name}"
            )

    source_names = {path.name for path in source_migrations}
    unexpected_names = sorted(
        path.name for path in packaged_migrations if path.name not in source_names
    )
    if unexpected_names:
        raise ReleaseResourceError(
            "Packaged SQL migration directory contains unexpected file(s): "
            + ", ".join(unexpected_names)
        )

    return source_migrations


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify packaged SQL migrations against their source files."
    )
    parser.add_argument("--source-directory", required=True, type=Path)
    parser.add_argument("--packaged-directory", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the SQL migration release-resource verifier."""

    args = _argument_parser().parse_args(argv)
    try:
        migrations = verify_packaged_sql_migrations(
            args.source_directory,
            args.packaged_directory,
        )
    except ReleaseResourceError as exc:
        print(f"SQL migration verification failed: {exc}", file=sys.stderr)
        return 1

    print(f"SQL migrations verified: {len(migrations)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
