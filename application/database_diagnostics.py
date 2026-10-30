"""Application-facing database readiness diagnostics and support events."""

from __future__ import annotations

from config.database_config import DatabaseSettings
from domain.support_events import SupportEventCategory, SupportLogLevel
from infrastructure.database.connection import DatabaseConnectionFactory
from infrastructure.database.preflight import (
    DatabasePreflightResult,
    check_database_preflight,
)


class DatabaseDiagnosticsService:
    """Run a safe preflight and record credential-free diagnostic context."""

    def __init__(
        self,
        support_logger=None,
        factory_type=DatabaseConnectionFactory,
        factory: DatabaseConnectionFactory | None = None,
    ):
        self._support_logger = support_logger
        self._factory_type = factory_type
        self._factory = factory

    def check(
        self,
        settings: DatabaseSettings,
        *,
        record_event: bool = True,
    ) -> DatabasePreflightResult:
        result = check_database_preflight(
            self._factory if self._factory is not None else self._factory_type(settings)
        )
        if record_event and self._support_logger is not None:
            self._support_logger.record(
                SupportEventCategory.CONNECTION,
                "database.preflight_completed",
                level=(
                    SupportLogLevel.INFO if result.ready else SupportLogLevel.ERROR
                ),
                status="ready" if result.ready else "failed",
                database_server=settings.server,
                database_name=settings.database,
                database_driver=settings.driver,
                database_error_category=(
                    result.category.value if result.category is not None else ""
                ),
                database_schema_version=result.current_schema_version,
                database_expected_schema_version=result.expected_schema_version,
                elapsed_ms=result.elapsed_ms,
                details=result.technical_detail,
            )
        return result


__all__ = ["DatabaseDiagnosticsService"]
