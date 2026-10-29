"""Read-only SQL-backed production and troubleshooting reports."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSpinBox,
)

from domain.database_reporting import ReportFilters, format_report_csv


RUN_HEADERS = (
    "Unit Serial",
    "Part Number",
    "Switch Serial",
    "Model",
    "Run",
    "Started (UTC)",
    "Operator",
    "Station",
    "Mode",
    "Completion",
    "Purpose",
    "Analysis",
    "Voided At (UTC)",
    "Voided By",
    "Void Reason",
    "Result",
    "Channels",
    "Attempts",
    "Retests",
    "Replacements",
    "Replacement Analysis",
    "Recommendations Used",
)
ASSIGNMENT_HEADERS = (
    "Unit Serial",
    "Part Number",
    "Switch Serial",
    "Model",
    "Installed (UTC)",
    "Installed By",
    "Removed (UTC)",
    "Removed By",
    "Removal Reason",
    "Runs",
)
CHANNEL_HEADERS = (
    "Unit Serial",
    "Run",
    "Channel",
    "Physical Port",
    "Attempt",
    "Status",
    "Wavelength 1 (nm)",
    "IL 1 (dB)",
    "Wavelength 2 (nm)",
    "IL 2 (dB)",
    "Written (UTC)",
    "Operator",
)
REPLACEMENT_HEADERS = (
    "Unit Serial",
    "Switch Serial",
    "Model",
    "Logical Channel",
    "Previous Port",
    "Replacement Port",
    "Reason",
    "Replaced By",
    "Replaced (UTC)",
    "Related Run",
    "Notes",
    "Outcome",
)


REPORT_LIGHT_STYLESHEET = """
QDialog#database_reports_dialog {
    background: #eceff1;
    color: #202124;
}
QDialog#database_reports_dialog QLabel,
QDialog#database_reports_dialog QCheckBox {
    color: #202124;
}
QDialog#database_reports_dialog QLineEdit,
QDialog#database_reports_dialog QComboBox,
QDialog#database_reports_dialog QSpinBox {
    background: #ffffff;
    color: #202124;
    border: 1px solid #c7cdd1;
}
QTabWidget#database_report_tabs::pane {
    background: #f7f8f9;
    border: 1px solid #c7cdd1;
}
QTabBar#database_report_tab_bar::tab {
    background: #e1e5e8;
    color: #3f464d;
    border: 1px solid #c7cdd1;
    padding: 6px 12px;
}
QTabBar#database_report_tab_bar::tab:selected {
    background: #ffffff;
    color: #202124;
}
QTableWidget#database_report_table {
    background: #ffffff;
    alternate-background-color: #f3f5f6;
    color: #202124;
    border: 1px solid #c7cdd1;
    gridline-color: #dbe1e4;
    selection-background-color: #ffd9dd;
    selection-color: #202124;
}
QTableWidget#database_report_table QHeaderView::section {
    background: #e4eeee;
    color: #202124;
    border: 1px solid #c7cdd1;
    padding: 6px;
    font-weight: 600;
}
"""

REPORT_DARK_STYLESHEET = """
QDialog#database_reports_dialog {
    background: #202124;
    color: #e8eaed;
}
QDialog#database_reports_dialog QLabel,
QDialog#database_reports_dialog QCheckBox {
    color: #e8eaed;
}
QDialog#database_reports_dialog QLineEdit,
QDialog#database_reports_dialog QComboBox,
QDialog#database_reports_dialog QSpinBox {
    background: #373a40;
    color: #e8eaed;
    border: 1px solid #5a6069;
    selection-background-color: #e60013;
    selection-color: #ffffff;
}
QTabWidget#database_report_tabs::pane {
    background: #25272b;
    border: 1px solid #4a4f57;
}
QTabBar#database_report_tab_bar::tab {
    background: #2b2e33;
    color: #b3bbc5;
    border: 1px solid #4a4f57;
    padding: 6px 12px;
}
QTabBar#database_report_tab_bar::tab:selected {
    background: #3a3e45;
    color: #ffffff;
}
QTableWidget#database_report_table {
    background: #25272b;
    alternate-background-color: #2b2e33;
    color: #e8eaed;
    border: 1px solid #4a4f57;
    gridline-color: #454a52;
    selection-background-color: #8b000b;
    selection-color: #ffffff;
}
QTableWidget#database_report_table QHeaderView::section {
    background: #3a3e45;
    color: #f0f2f4;
    border: 1px solid #4a4f57;
    padding: 6px;
    font-weight: 600;
}
"""


def _timestamp(value) -> str:
    if value is None:
        return ""
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def run_report_rows(report) -> list[list[str]]:
    return [
        [
            row.main_board_serial,
            row.part_number,
            row.switch_serial,
            row.switch_model,
            str(row.run_number),
            _timestamp(row.started_at_utc),
            row.tested_by,
            "" if row.station_number is None else str(row.station_number),
            row.wavelength_mode,
            row.completion_status,
            row.run_purpose,
            "Voided" if row.analysis_status == "excluded" else row.analysis_status.title(),
            _timestamp(row.voided_at_utc),
            row.voided_by,
            row.void_reason,
            row.result_label,
            str(row.current_channel_count),
            str(row.attempt_count),
            str(row.retest_attempt_count),
            str(row.replacement_count),
            row.replacement_analysis_status.replace("_", " ").title(),
            "%d/%d"
            % (
                row.replacement_recommendations_used,
                row.replacement_recommendation_count,
            ),
        ]
        for row in report.runs
    ]


def assignment_report_rows(report) -> list[list[str]]:
    return [
        [
            row.main_board_serial,
            row.part_number,
            row.switch_serial,
            row.switch_model,
            _timestamp(row.installed_at_utc),
            row.installed_by,
            _timestamp(row.removed_at_utc),
            row.removed_by,
            row.removal_reason,
            str(row.run_count),
        ]
        for row in report.assignments
    ]


def channel_report_rows(rows) -> list[list[str]]:
    return [
        [
            row.main_board_serial,
            str(row.run_number),
            str(row.logical_channel),
            "" if row.physical_port is None else str(row.physical_port),
            str(row.attempt_number),
            "Current" if row.is_current else "Superseded",
            str(row.wavelength_1_nm),
            f"{row.wavelength_1_il_db:.4f}",
            str(row.wavelength_2_nm),
            f"{row.wavelength_2_il_db:.4f}",
            row.written_at_utc,
            row.written_by,
        ]
        for row in rows
    ]


def replacement_report_rows(report) -> list[list[str]]:
    return [
        [
            row.main_board_serial,
            row.switch_serial,
            row.switch_model,
            str(row.logical_channel),
            str(row.previous_physical_port),
            str(row.replacement_physical_port),
            row.reason,
            row.replaced_by,
            _timestamp(row.replaced_at_utc),
            "" if row.related_run_number is None else str(row.related_run_number),
            row.notes,
            row.outcome,
        ]
        for row in report.replacements
    ]


class DatabaseReportsDialog(QDialog):
    """Search database history and export the exact read-only result set."""

    def __init__(self, reporting_service, parent=None):
        super().__init__(parent)
        self._service = reporting_service
        self._report = None
        self._channel_rows = ()
        self.setObjectName("database_reports_dialog")
        self.setWindowTitle("Database Reports")
        self.resize(1380, 760)

        layout = QVBoxLayout(self)
        filters = QGridLayout()
        self.unit_edit = QLineEdit()
        self.switch_edit = QLineEdit()
        self.operator_edit = QLineEdit()
        self.station_spin = QSpinBox()
        self.station_spin.setRange(0, 9999)
        self.station_spin.setSpecialValueText("Any station")
        self.from_edit = QLineEdit()
        self.from_edit.setPlaceholderText("YYYY-MM-DD")
        self.to_edit = QLineEdit()
        self.to_edit.setPlaceholderText("YYYY-MM-DD")
        self.model_combo = self._combo(
            ("All models", ""),
            ("OSX-100", "OSX-100"),
            ("OSX-150", "OSX-150"),
        )
        self.mode_combo = self._combo(("All modes", ""), ("SM", "SM"), ("MM", "MM"))
        self.completion_combo = self._combo(
            ("All completion states", ""),
            ("In progress", "in_progress"),
            ("Complete", "complete"),
            ("Stopped", "stopped"),
            ("Failed", "failed"),
        )
        self.purpose_combo = self._combo(
            ("All purposes", ""),
            ("Production", "production"),
            ("Engineering", "engineering"),
            ("Training", "training"),
            ("Calibration", "calibration"),
        )
        self.analysis_combo = self._combo(
            ("All analysis states", ""),
            ("Pending", "pending"),
            ("Included", "included"),
            ("Excluded", "excluded"),
            ("Superseded", "superseded"),
        )
        fields = (
            ("Unit serial:", self.unit_edit),
            ("Switch serial:", self.switch_edit),
            ("Model:", self.model_combo),
            ("Mode:", self.mode_combo),
            ("Operator:", self.operator_edit),
            ("Station:", self.station_spin),
            ("Completion:", self.completion_combo),
            ("Purpose:", self.purpose_combo),
            ("Analysis:", self.analysis_combo),
            ("From date (UTC):", self.from_edit),
            ("Through date (UTC):", self.to_edit),
        )
        for index, (label, widget) in enumerate(fields):
            pair = index % 5
            column = 0 if index < 5 else 2
            filters.addWidget(QLabel(label), pair, column)
            filters.addWidget(widget, pair, column + 1)
        layout.addLayout(filters)

        controls = QHBoxLayout()
        self.production_only_check = QCheckBox(
            "Production metrics only (included production runs)"
        )
        self.production_only_check.setChecked(True)
        self.production_only_check.setToolTip(
            "Uncheck to include pending, excluded, superseded, engineering, "
            "training, and calibration runs for troubleshooting."
        )
        controls.addWidget(self.production_only_check)
        controls.addStretch()
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.refresh_report)
        controls.addWidget(self.search_button)
        self.export_button = QPushButton("Export Current Report...")
        self.export_button.clicked.connect(self.export_current_report)
        controls.addWidget(self.export_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        controls.addWidget(close_button)
        layout.addLayout(controls)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("database_report_tabs")
        self.tabs.tabBar().setObjectName("database_report_tab_bar")
        self.run_table = self._table(RUN_HEADERS)
        self.assignment_table = self._table(ASSIGNMENT_HEADERS)
        self.channel_table = self._table(CHANNEL_HEADERS)
        self.replacement_table = self._table(REPLACEMENT_HEADERS)
        self.tabs.addTab(self.run_table, "Runs")
        self.tabs.addTab(self.assignment_table, "Assignments")
        self.tabs.addTab(self.channel_table, "Channel / Retest History")
        self.tabs.addTab(self.replacement_table, "Replacement Outcomes")
        layout.addWidget(self.tabs, 1)
        self.run_table.itemSelectionChanged.connect(self._load_selected_run_channels)
        self.apply_theme(bool(getattr(parent, "dark_mode_enabled", False)))
        self.refresh_report()

    def apply_theme(self, dark_mode: bool):
        """Apply report-specific colors because this dialog is independently themed."""
        self.setStyleSheet(
            REPORT_DARK_STYLESHEET if dark_mode else REPORT_LIGHT_STYLESHEET
        )

    @staticmethod
    def _combo(*items):
        combo = QComboBox()
        for label, value in items:
            combo.addItem(label, value)
        return combo

    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers))
        table.setObjectName("database_report_table")
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @staticmethod
    def _date_value(text, *, through=False):
        value = str(text or "").strip()
        if not value:
            return None
        parsed = date.fromisoformat(value)
        clock = time.max if through else time.min
        return datetime.combine(parsed, clock, tzinfo=timezone.utc)

    def _filters(self):
        return ReportFilters(
            main_board_serial=self.unit_edit.text().strip(),
            switch_serial=self.switch_edit.text().strip(),
            switch_model=self.model_combo.currentData(),
            wavelength_mode=self.mode_combo.currentData(),
            tested_by=self.operator_edit.text().strip(),
            station_number=(
                self.station_spin.value() if self.station_spin.value() > 0 else None
            ),
            started_from_utc=self._date_value(self.from_edit.text()),
            started_to_utc=self._date_value(self.to_edit.text(), through=True),
            completion_status=self.completion_combo.currentData(),
            run_purpose=self.purpose_combo.currentData(),
            analysis_status=self.analysis_combo.currentData(),
            include_all_records=not self.production_only_check.isChecked(),
        )

    def refresh_report(self):
        try:
            report = self._service.search(self._filters())
        except ValueError as error:
            QMessageBox.warning(self, "Invalid report filter", str(error))
            return
        except Exception as error:
            QMessageBox.critical(self, "Database report unavailable", str(error))
            return
        self._report = report
        self._populate(
            self.run_table,
            RUN_HEADERS,
            run_report_rows(report),
            report.runs,
        )
        self._populate(
            self.assignment_table,
            ASSIGNMENT_HEADERS,
            assignment_report_rows(report),
        )
        self._populate(
            self.replacement_table,
            REPLACEMENT_HEADERS,
            replacement_report_rows(report),
        )
        summary = report.summary
        scope = (
            "included production data"
            if self.production_only_check.isChecked()
            else "all matching troubleshooting data"
        )
        self.summary_label.setText(
            f"Scope: {scope}  |  Runs: {summary.run_count}  |  "
            f"Current channels: {summary.current_channel_count}  |  "
            f"Accepted attempts: {summary.attempt_count}  |  "
            f"Retests: {summary.retest_attempt_count} "
            f"({summary.retest_rate_percent:.1f}%)  |  "
            f"Replacement records: {summary.replacement_count}"
        )
        self._channel_rows = ()
        self._populate(self.channel_table, CHANNEL_HEADERS, [])
        if self.run_table.rowCount():
            self.run_table.selectRow(0)
        self.export_button.setEnabled(
            bool(report.runs or report.assignments or report.replacements)
        )

    @staticmethod
    def _populate(table, headers, rows, records=()):
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                if column_index == 0 and row_index < len(records):
                    item.setData(Qt.UserRole, records[row_index].run_id)
                table.setItem(row_index, column_index, item)
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)

    def _load_selected_run_channels(self):
        selected = self.run_table.selectedItems()
        if not selected:
            return
        first = self.run_table.item(selected[0].row(), 0)
        run_id = first.data(Qt.UserRole) if first is not None else None
        if run_id is None:
            return
        try:
            self._channel_rows = self._service.channels_for_run(int(run_id))
        except Exception as error:
            QMessageBox.critical(self, "Channel history unavailable", str(error))
            return
        self._populate(
            self.channel_table,
            CHANNEL_HEADERS,
            channel_report_rows(self._channel_rows),
        )

    def export_current_report(self):
        if self._report is None:
            return
        index = self.tabs.currentIndex()
        definitions = {
            0: ("runs", RUN_HEADERS, run_report_rows(self._report)),
            1: (
                "assignments",
                ASSIGNMENT_HEADERS,
                assignment_report_rows(self._report),
            ),
            2: ("channels", CHANNEL_HEADERS, channel_report_rows(self._channel_rows)),
            3: (
                "replacements",
                REPLACEMENT_HEADERS,
                replacement_report_rows(self._report),
            ),
        }
        name, headers, rows = definitions[index]
        if not rows:
            QMessageBox.information(
                self,
                "Database Reports",
                "There are no rows to export on this tab.",
            )
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Database Report",
            f"database-report-{name}-{stamp}.csv",
            "CSV files (*.csv)",
        )
        if not selected:
            return
        path = Path(selected)
        try:
            path.write_text(format_report_csv(headers, rows), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, "Could not export report", str(error))
            return
        parent = self.parent()
        if parent is not None and hasattr(parent, "statusBar"):
            parent.statusBar().showMessage(
                f"Database report exported to {path.name}.",
                5000,
            )


__all__ = [
    "ASSIGNMENT_HEADERS",
    "CHANNEL_HEADERS",
    "DatabaseReportsDialog",
    "REPLACEMENT_HEADERS",
    "RUN_HEADERS",
    "assignment_report_rows",
    "channel_report_rows",
    "replacement_report_rows",
    "run_report_rows",
]
