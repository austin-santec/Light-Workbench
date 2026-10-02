"""Themed dialogs for support-log status and support-bundle date selection."""

from datetime import date, timedelta

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)


class LoggingStatusDialog(QDialog):
    """Present a read-only snapshot of the support logging subsystem."""

    def __init__(self, status, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Support Logging Status")
        self.setMinimumSize(620, 430)
        layout = QVBoxLayout(self)
        heading = QLabel("Healthy" if status.healthy else "Degraded")
        heading.setStyleSheet(
            "font-size: 18px; font-weight: 800; color: %s;"
            % ("#2e8b57" if status.healthy else "#e60013")
        )
        layout.addWidget(heading)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(
            "\n".join(
                (
                    "Active folder: %s" % status.active_folder,
                    "Active filename: %s" % status.active_filename,
                    "Application instance: %s" % status.app_instance_id,
                    "Log schema version: %s" % status.schema_version,
                    "Queue depth: %s" % status.queue_depth,
                    "Dropped events: %s" % status.dropped_event_count,
                    "In-memory buffered events: %s" % status.memory_event_count,
                    "Retention: %s days" % status.retention_days,
                    "Per-file limit: %.1f MB" % (status.max_file_bytes / 1024 / 1024),
                    "Total limit: %.1f MB" % (status.max_total_bytes / 1024 / 1024),
                    "Fallback directory active: %s"
                    % ("Yes" if status.fallback_active else "No"),
                    "Last writer error: %s"
                    % (status.last_writer_error or "None"),
                )
            )
        )
        layout.addWidget(details, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class SupportBundleDialog(QDialog):
    """Collect an inclusive local-date range for an explicit bundle export."""

    def __init__(self, parent=None, today: date | None = None):
        super().__init__(parent)
        self.setWindowTitle("Export Support Bundle")
        current = today or date.today()
        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Choose the local dates to include. The bundle contains support logs, "
            "a dependency report, sanitized configuration, and a manifest. It does "
            "not include run files or COC workbooks."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        form = QFormLayout()
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        start = current - timedelta(days=2)
        self.start_date_edit.setDate(QDate(start.year, start.month, start.day))
        form.addRow("Start date:", self.start_date_edit)
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setDate(QDate(current.year, current.month, current.day))
        form.addRow("End date:", self.end_date_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def start_date(self) -> date:
        selected = self.start_date_edit.date()
        return date(selected.year(), selected.month(), selected.day())

    @property
    def end_date(self) -> date:
        selected = self.end_date_edit.date()
        return date(selected.year(), selected.month(), selected.day())

    def _validate_and_accept(self):
        if self.end_date < self.start_date:
            self.start_date_edit.setFocus(Qt.OtherFocusReason)
            return
        self.accept()


__all__ = ["LoggingStatusDialog", "SupportBundleDialog"]
