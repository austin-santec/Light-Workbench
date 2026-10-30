"""Compact, theme-aware database availability indicator."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QToolButton

from application.database_health_monitor import (
    DatabaseHealthSnapshot,
    DatabaseHealthState,
)


_STATE_TEXT = {
    DatabaseHealthState.DISABLED: "Database: Disabled",
    DatabaseHealthState.CHECKING: "Database: Checking\u2026",
    DatabaseHealthState.READY: "Database: Ready",
    DatabaseHealthState.UNAVAILABLE: "Database: Unavailable",
}

_LIGHT_COLORS = {
    DatabaseHealthState.DISABLED: ("#5f6368", "#f1f3f4", "#c4c7c5"),
    DatabaseHealthState.CHECKING: ("#6f4800", "#fff1c2", "#d89b00"),
    DatabaseHealthState.READY: ("#1f653f", "#dff4e7", "#2e8b57"),
    DatabaseHealthState.UNAVAILABLE: ("#8f2f25", "#fde5e2", "#c5493d"),
}

_DARK_COLORS = {
    DatabaseHealthState.DISABLED: ("#c0c6ce", "#34373c", "#626872"),
    DatabaseHealthState.CHECKING: ("#ffd166", "#3e3520", "#a87918"),
    DatabaseHealthState.READY: ("#72d19a", "#253a2e", "#3b8f5e"),
    DatabaseHealthState.UNAVAILABLE: ("#ff8f86", "#43292a", "#b9564f"),
}


class DatabaseStatusIndicator(QToolButton):
    """Render the latest verified database health without implying permanence."""

    def __init__(self, server: str = "", database: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("database_status_indicator")
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoRaise(False)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setAccessibleName("Database status")
        self.setMinimumWidth(142)
        self._server = str(server or "").strip()
        self._database = str(database or "").strip()
        self._snapshot = DatabaseHealthSnapshot(DatabaseHealthState.DISABLED)
        self._dark_mode = False
        self.set_snapshot(self._snapshot)

    @property
    def snapshot(self) -> DatabaseHealthSnapshot:
        return self._snapshot

    def set_snapshot(self, snapshot: DatabaseHealthSnapshot) -> None:
        self._snapshot = snapshot
        self.setText(_STATE_TEXT[snapshot.state])
        self.setAccessibleDescription(self._tooltip(snapshot))
        self.setToolTip(self._tooltip(snapshot))
        self.apply_theme(self._dark_mode)

    def apply_theme(self, dark_mode: bool) -> None:
        self._dark_mode = bool(dark_mode)
        colors = _DARK_COLORS if self._dark_mode else _LIGHT_COLORS
        foreground, background, border = colors[self._snapshot.state]
        self.setStyleSheet(
            "QToolButton#database_status_indicator {"
            "color: %s; background: %s; border: 1px solid %s; "
            "border-radius: 10px; padding: 4px 9px; font-weight: 700;"
            "} QToolButton#database_status_indicator:hover {"
            "border-width: 2px; padding: 3px 8px;"
            "}" % (foreground, background, border)
        )

    def _tooltip(self, snapshot: DatabaseHealthSnapshot) -> str:
        lines = ["Database availability: %s" % snapshot.state.value.title()]
        if self._server:
            lines.append("Server: %s" % self._server[:160])
        if self._database:
            lines.append("Database: %s" % self._database[:160])
        if snapshot.checked_at_utc is not None:
            lines.append("Last checked: %s" % self._timestamp(snapshot.checked_at_utc))
        if snapshot.last_success_at_utc is not None:
            lines.append(
                "Last successful check: %s"
                % self._timestamp(snapshot.last_success_at_utc)
            )
        if snapshot.elapsed_ms is not None:
            lines.append("Check duration: %d ms" % snapshot.elapsed_ms)
        if snapshot.expected_schema_version is not None:
            current = (
                str(snapshot.current_schema_version)
                if snapshot.current_schema_version is not None
                else "unknown"
            )
            lines.append(
                "Schema: %s (expected %d)"
                % (current, snapshot.expected_schema_version)
            )
        if snapshot.error_category:
            lines.append("Category: %s" % snapshot.error_category[:80])
        if snapshot.message:
            lines.append("Status: %s" % snapshot.message[:300])
        lines.append("Click to check again. No permanent connection is held.")
        return "\n".join(lines)

    @staticmethod
    def _timestamp(value) -> str:
        return value.isoformat(timespec="seconds").replace("+00:00", "Z")


__all__ = ["DatabaseStatusIndicator"]
