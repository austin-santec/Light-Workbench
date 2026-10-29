"""Safely recreate and migrate the disposable SQL integration database."""

from __future__ import annotations

import argparse
import os
import sys

from config.app_info import APP_VERSION
from infrastructure.database import (
    INTEGRATION_DATABASE_NAME,
    MigrationRunner,
    build_windows_connection_string,
    discover_migrations,
    reset_integration_database,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recreate and migrate only the Light Workbench integration DB."
    )
    parser.add_argument(
        "--server",
        default=os.environ.get("LWB_DB_SERVER"),
        help="SQL Server instance (or set LWB_DB_SERVER)",
    )
    parser.add_argument(
        "--database",
        default=INTEGRATION_DATABASE_NAME,
        help=f"Must be exactly {INTEGRATION_DATABASE_NAME}",
    )
    parser.add_argument(
        "--confirm-reset",
        required=True,
        help="Repeat the integration database name to authorize reset",
    )
    parser.add_argument(
        "--driver",
        default=os.environ.get("LWB_DB_DRIVER", "ODBC Driver 18 for SQL Server"),
    )
    parser.add_argument(
        "--trust-server-certificate",
        action="store_true",
        help="Trust the server certificate (appropriate for local development)",
    )
    args = parser.parse_args(argv)
    if not args.server:
        parser.error("--server is required unless LWB_DB_SERVER is set")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        import pyodbc

        master_connection_string = build_windows_connection_string(
            args.server,
            "master",
            args.driver,
            args.trust_server_certificate,
        )
        with pyodbc.connect(
            master_connection_string, timeout=10, autocommit=True
        ) as master_connection:
            reset_integration_database(
                master_connection,
                args.database,
                args.confirm_reset,
            )

        database_connection_string = build_windows_connection_string(
            args.server,
            args.database,
            args.driver,
            args.trust_server_certificate,
        )
        with pyodbc.connect(database_connection_string, timeout=10) as connection:
            result = MigrationRunner(
                connection,
                discover_migrations(),
                APP_VERSION,
            ).apply()
    except Exception as exc:
        print(f"Integration database reset failed: {exc}", file=sys.stderr)
        return 1

    formatted = ", ".join(f"{value:04d}" for value in result.applied_ids)
    print(f"Reset and migrated {args.database}.")
    print(f"Applied migrations: {formatted or 'none'}")
    print(f"Schema version: {result.current_version:04d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
