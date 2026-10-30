"""Composition root for the SQL-primary production-run workflow."""

from __future__ import annotations

from pathlib import Path

from application.database_diagnostics import DatabaseDiagnosticsService
from application.database_primary_workflow import DatabasePrimaryRunWorkflow
from config.app_config import DEFAULT_PATHS
from domain.support_events import SupportEventCategory, SupportLogLevel
from infrastructure.database.connection import (
    DatabaseConfigurationError,
    DatabaseConnectionFactory,
)
from infrastructure.database.settings_repository import DatabaseSettingsRepository
from infrastructure.database.sql_repositories import SqlRepositories


def build_database_primary_workflow(
    support_logger=None,
    database_config_path: Path | None = None,
):
    """Build the production workflow without opening a connection eagerly."""
    settings_path = database_config_path or DEFAULT_PATHS.database_config_path
    repository = DatabaseSettingsRepository(settings_path)
    try:
        created = repository.ensure_exists()
        settings = repository.load()
    except DatabaseConfigurationError as error:
        if support_logger is not None:
            support_logger.record(
                SupportEventCategory.CONNECTION,
                "database.configuration_failed",
                level=SupportLogLevel.ERROR,
                configuration_path=str(settings_path),
                status="invalid",
                details=error.technical_detail or str(error),
            )
        raise
    if support_logger is not None:
        support_logger.record(
            SupportEventCategory.CONNECTION,
            "database.configuration_%s" % ("created" if created else "loaded"),
            status="created" if created else "loaded",
            configuration_path=str(settings_path),
            database_server=settings.server,
            database_name=settings.database,
            database_driver=settings.driver,
            database_authentication=settings.authentication,
            details="Per-user database.ini is active.",
        )
    factory = DatabaseConnectionFactory(settings)
    repositories = SqlRepositories(factory)
    diagnostics = DatabaseDiagnosticsService(support_logger, factory=factory)
    return DatabasePrimaryRunWorkflow(
        repositories,
        readiness_check=lambda: diagnostics.check(settings),
        support_logger=support_logger,
    )


__all__ = ["build_database_primary_workflow"]
