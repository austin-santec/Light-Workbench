"""Explicit read-only SQL Server connectivity and schema diagnostic."""

from __future__ import annotations

import argparse

from application.database_diagnostics import DatabaseDiagnosticsService
from config.app_config import DEFAULT_PATHS
from infrastructure.database.settings_repository import DatabaseSettingsRepository


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the configured Light Workbench SQL Server database."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_PATHS.database_config_path),
        help="Path to the non-secret database INI file.",
    )
    args = parser.parse_args(argv)
    try:
        settings = DatabaseSettingsRepository(args.config).load()
        result = DatabaseDiagnosticsService().check(settings)
    except (OSError, ValueError) as exc:
        print(f"Database configuration is invalid: {exc}")
        return 2
    print(result.operator_message)
    print(
        "Target: %s / %s | schema: %s (expected %s)"
        % (
            settings.server,
            settings.database,
            result.current_schema_version if result.current_schema_version is not None else "unknown",
            result.expected_schema_version,
        )
    )
    if result.technical_detail:
        print("Technical detail: " + result.technical_detail)
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
