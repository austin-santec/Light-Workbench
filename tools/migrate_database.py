"""Apply Light Workbench SQL Server migrations to an explicit database."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from config.app_info import APP_VERSION
from infrastructure.database import (
    MigrationRunner,
    build_windows_connection_string,
    discover_migrations,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply forward-only Light Workbench SQL Server migrations."
    )
    parser.add_argument(
        "--server",
        default=os.environ.get("LWB_DB_SERVER"),
        help="SQL Server instance (or set LWB_DB_SERVER)",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("LWB_DB_NAME"),
        help="Target database (or set LWB_DB_NAME)",
    )
    parser.add_argument(
        "--driver",
        default=os.environ.get("LWB_DB_DRIVER", "ODBC Driver 18 for SQL Server"),
        help="Installed SQL Server ODBC driver",
    )
    parser.add_argument(
        "--trust-server-certificate",
        action="store_true",
        help="Trust the server certificate (appropriate for local development)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate migration history and show pending migrations without applying",
    )
    parser.add_argument(
        "--migrations",
        type=Path,
        default=None,
        help="Override the bundled migration directory (primarily for tests)",
    )
    args = parser.parse_args(argv)
    if not args.server or not args.database:
        parser.error("--server and --database are required unless set by environment")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        import pyodbc

        connection_string = build_windows_connection_string(
            server=args.server,
            database=args.database,
            driver=args.driver,
            trust_server_certificate=args.trust_server_certificate,
        )
        migrations = (
            discover_migrations(args.migrations)
            if args.migrations is not None
            else discover_migrations()
        )
        with pyodbc.connect(connection_string, timeout=10) as connection:
            runner = MigrationRunner(connection, migrations, APP_VERSION)
            if args.check:
                pending = runner.pending_migrations()
                if pending:
                    print("Pending migrations:")
                    for migration in pending:
                        print(f"  {migration.path.name}")
                else:
                    print("Database schema is current.")
                return 0
            result = runner.apply()
    except (ImportError, ValueError, RuntimeError) as exc:
        print(f"Database migration failed: {exc}", file=sys.stderr)
        return 1

    if result.applied_ids:
        formatted = ", ".join(f"{value:04d}" for value in result.applied_ids)
        print(f"Applied migrations: {formatted}")
    else:
        print("Database schema is already current.")
    print(f"Schema version: {result.current_version:04d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
