"""Verify backup and restore for the disposable SQL integration database."""

from __future__ import annotations

import argparse
import os
import sys

from infrastructure.database import (
    INTEGRATION_DATABASE_NAME,
    build_windows_connection_string,
    delete_temporary_backup,
    temporary_backup_path,
    verify_backup_restore,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up, restore, and validate the SQL integration database."
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
        "--confirm-database",
        required=True,
        help="Repeat the integration database name to authorize verification",
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
    parser.add_argument(
        "--keep-backup",
        action="store_true",
        help="Keep the verified .bak file instead of deleting it afterward",
    )
    args = parser.parse_args(argv)
    if not args.server:
        parser.error("--server is required unless LWB_DB_SERVER is set")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    backup_path = None
    try:
        import pyodbc

        connection_string = build_windows_connection_string(
            args.server,
            "master",
            args.driver,
            args.trust_server_certificate,
        )
        with pyodbc.connect(
            connection_string, timeout=10, autocommit=True
        ) as connection:
            backup_path = temporary_backup_path(connection, args.database)
            result = verify_backup_restore(
                connection,
                args.database,
                args.confirm_database,
                backup_path,
            )
            if not args.keep_backup:
                delete_temporary_backup(connection, backup_path)
    except Exception as exc:
        print(f"Backup/restore verification failed: {exc}", file=sys.stderr)
        return 1

    print(f"Backup restored and passed DBCC CHECKDB: {result.backup_path}")
    print(
        "Restored schema: "
        f"{result.migration_count} migration(s), "
        f"{result.table_count} tables, {result.view_count} views"
    )
    if args.keep_backup:
        print("Verified backup retained.")
    else:
        print("Temporary verified backup deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
