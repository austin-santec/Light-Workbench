"""Composition root for the SQL-primary production-run workflow."""

from __future__ import annotations

from application.database_diagnostics import DatabaseDiagnosticsService
from application.database_primary_workflow import DatabasePrimaryRunWorkflow
from config.app_config import DEFAULT_PATHS
from infrastructure.database.connection import DatabaseConnectionFactory
from infrastructure.database.settings_repository import DatabaseSettingsRepository
from infrastructure.database.sql_repositories import SqlRepositories


def build_database_primary_workflow(support_logger=None):
    """Build the production workflow without opening a connection eagerly."""
    settings = DatabaseSettingsRepository(DEFAULT_PATHS.database_config_path).load()
    factory = DatabaseConnectionFactory(settings)
    repositories = SqlRepositories(factory)
    diagnostics = DatabaseDiagnosticsService(support_logger)
    return DatabasePrimaryRunWorkflow(
        repositories,
        readiness_check=lambda: diagnostics.check(settings),
    )


__all__ = ["build_database_primary_workflow"]
