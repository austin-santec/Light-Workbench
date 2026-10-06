"""Read-only accepted-reading history dialog."""

import csv
import json
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QDialog,
)

from domain.measurement_attempts import MeasurementAttempt


HISTORY_HEADERS = (
    "Channel",
    "Attempt",
    "Status",
    "1310 nm IL (dB)",
    "1550 nm IL (dB)",
    "Physical Port",
    "Written At (UTC)",
    "Operator",
    "Context",
)


def history_rows(
    attempts: list[MeasurementAttempt],
    *,
    status_source: list[MeasurementAttempt] | None = None,
) -> list[list[str]]:
    """Return chronological display rows without reading visible widgets."""
    latest = {}
    for attempt in status_source if status_source is not None else attempts:
        current = latest.get(attempt.channel)
        if current is None or attempt.attempt_number > current.attempt_number:
            latest[attempt.channel] = attempt
    rows = []
    for attempt in sorted(
        attempts,
        key=lambda item: (item.channel, item.attempt_number, item.accepted_at_utc),
    ):
        status = "Current" if latest.get(attempt.channel) is attempt else "Superseded"
        rows.append(
            [
                str(attempt.channel),
                str(attempt.attempt_number),
                status,
                "%.4f" % attempt.loss_1310_db,
                "%.4f" % attempt.loss_1550_db,
                "" if attempt.physical_port is None else str(attempt.physical_port),
                attempt.accepted_at_utc or "Unknown",
                attempt.operator_initials or "Unknown",
                attempt.write_context or "initial",
            ]
        )
    return rows


def history_tsv(
    attempts: list[MeasurementAttempt],
    *,
    status_source: list[MeasurementAttempt] | None = None,
) -> str:
    """Format all accepted attempts as Excel-compatible tab-separated text."""
    rows = [
        list(HISTORY_HEADERS),
        *history_rows(attempts, status_source=status_source),
    ]
    return "\n".join("\t".join(row) for row in rows)


class ReadingHistoryDialog(QDialog):
    """Display accepted readings and retests for one loaded run."""

    def __init__(self, attempts, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reading History")
        self.resize(980, 520)
        self._attempts = list(attempts or [])

        layout = QVBoxLayout(self)
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Channel:"))
        self.channel_filter = QComboBox()
        self.channel_filter.addItem("All channels", None)
        for channel in sorted({attempt.channel for attempt in self._attempts}):
            self.channel_filter.addItem(str(channel), channel)
        self.channel_filter.currentIndexChanged.connect(self.refresh_rows)
        filter_layout.addWidget(self.channel_filter)
        filter_layout.addWidget(QLabel("Show:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("All attempts", "all")
        self.status_filter.addItem("Current only", "current")
        self.status_filter.addItem("Superseded only", "superseded")
        self.status_filter.currentIndexChanged.connect(self.refresh_rows)
        filter_layout.addWidget(self.status_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.history_table = QTableWidget(0, len(HISTORY_HEADERS))
        self.history_table.setHorizontalHeaderLabels(HISTORY_HEADERS)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setSortingEnabled(True)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.history_table, 1)

        buttons = QHBoxLayout()
        copy_button = QPushButton("Copy History")
        copy_button.clicked.connect(self.copy_history)
        export_button = QPushButton("Export History...")
        export_button.clicked.connect(self.export_history)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(copy_button)
        buttons.addWidget(export_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self.refresh_rows()

    def _filtered_attempts(self):
        channel = self.channel_filter.currentData()
        status = self.status_filter.currentData()
        latest = {}
        for attempt in self._attempts:
            current = latest.get(attempt.channel)
            if current is None or attempt.attempt_number > current.attempt_number:
                latest[attempt.channel] = attempt
        filtered = []
        for attempt in self._attempts:
            if channel is not None and attempt.channel != channel:
                continue
            is_current = latest.get(attempt.channel) is attempt
            if status == "current" and not is_current:
                continue
            if status == "superseded" and is_current:
                continue
            filtered.append(attempt)
        return filtered

    def refresh_rows(self):
        rows = history_rows(
            self._filtered_attempts(),
            status_source=self._attempts,
        )
        self.history_table.setSortingEnabled(False)
        self.history_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                self.history_table.setItem(
                    row_index, column_index, QTableWidgetItem(value)
                )
        self.history_table.resizeColumnsToContents()
        self.history_table.setSortingEnabled(True)

    def copy_history(self):
        attempts = self._filtered_attempts()
        text = history_tsv(attempts, status_source=self._attempts)
        if not attempts:
            QMessageBox.information(self, "Reading History", "There is no history to copy.")
            return
        from PyQt5.QtWidgets import QApplication

        QApplication.clipboard().setText(text)
        self.parent().statusBar().showMessage("Reading history copied to clipboard.", 5000)

    def export_history(self):
        attempts = self._filtered_attempts()
        if not attempts:
            QMessageBox.information(self, "Reading History", "There is no history to export.")
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Reading History",
            "reading-history.csv",
            "CSV files (*.csv);;JSON files (*.json)",
        )
        if not selected:
            return
        path = Path(selected)
        try:
            if path.suffix.lower() == ".json":
                path.write_text(
                    json.dumps([attempt.as_dict() for attempt in attempts], indent=2)
                    + "\n",
                    encoding="utf-8",
                )
            else:
                with path.open("w", newline="", encoding="utf-8") as output:
                    writer = csv.writer(output)
                    writer.writerow(HISTORY_HEADERS)
                    writer.writerows(
                        history_rows(attempts, status_source=self._attempts)
                    )
        except OSError as error:
            QMessageBox.critical(self, "Could not export history", str(error))
            return
        self.parent().statusBar().showMessage(
            "Reading history exported to %s." % path.name, 5000
        )


__all__ = ["HISTORY_HEADERS", "ReadingHistoryDialog", "history_rows", "history_tsv"]
