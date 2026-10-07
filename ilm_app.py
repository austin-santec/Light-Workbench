"""PyQt5 desktop viewer for insertion-loss run data."""

import sys
import uuid
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import (
    QItemSelectionModel,
    QSettings,
    QTimer,
    Qt,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QDesktopServices, QIcon, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QInputDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolButton,
    QMenu,
    QKeySequenceEdit,
    QLineEdit,
    QSpinBox,
    QSizePolicy,
    QShortcut,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QProgressDialog,
    QScrollArea,
)

from application.run_controller import HardwareRunController
from application.hardware_connection import HardwareConnectionManager
from application.support_logging import (
    SupportLoggingService,
    get_support_logging_service,
    install_exception_hooks,
    set_support_logging_service,
)
from application.live_controller import LiveILReadingController
from application.hardware_planning import parse_hardware_channels
from application.hardware_session import HardwareRunSession
from application.run_start import (
    build_hardware_run_request,
    prepare_hardware_run,
)
from application.run_preflight import (
    RunPreflightIssueCategory,
    validate_run_preflight,
)
from application.admin_session import AdminSession
from application.part_number_lookup import (
    PartNumberLookupController,
    classify_part_lookup_error,
)
from application.coc_workflow import CocRunOption, CocWorkflow
from application.reference_session import ReferenceSession
from domain.measurement import (
    calculate_insertion_loss,
    format_dark_reference_error,
    validate_insertion_loss,
    validate_reference_measurements,
)
from domain.reference import ReferenceMethod, new_reference_snapshot
from domain.hardware_connection import (
    HardwareBusyError,
    HardwareCapability,
    HardwareNotReadyError,
)
from domain.models import ConnectionState, DeviceCategory
from domain.limit_profiles import (
    LimitProfile,
    default_limit_profiles,
    legacy_limit_profile,
    normalize_switch_model,
)
from domain.comparison import comparison_values, index_measurements
from domain.measurement_attempts import (
    latest_attempt_for_channel,
    new_measurement_attempt,
    normalise_attempts,
)
from domain.raw_export import format_raw_measurements
from domain.coc_preparation import infer_front_panel_channel_count
from domain.timing import SwitchTestTimer
from hardware.factory import HardwareFactory
from infrastructure.coc_exporter import (
    COC_TEMPLATE_45_FILENAME,
    COC_TEMPLATE_48_FILENAME,
    DEFAULT_PART_LOOKUP_ROOT,
    FileCocExporter,
)
from infrastructure.run_repository import DEFAULT_RUN_ROOT, FileRunRepository
from infrastructure.unit_repository import FileUnitRepository
from infrastructure.limit_profile_repository import LimitProfileRepository
from infrastructure.support_bundle import export_support_bundle
from hardware.optical_switch import OSX150
from hardware.power_meter import SantecPowerMeter, SimulatedPowerMeter
from run_data import MeasurementRecord, RunData
from domain.replacements import (
    ReplacementReading,
    analyze_replacements,
    effective_replacements,
    legacy_replacement_history,
    new_replacement_event,
    new_replacement_void_event,
    normalise_completed_replacements,
    normalise_replacement_history,
    recommendation_category,
)
from tools.dependency_check import DependencyReport, collect_dependency_report
from ui.red_light_test import RedLightTestDialog
from config.app_info import APP_NAME, APP_TAGLINE, APP_VERSION, about_text
from ui.live_il_reading import LiveILReadingDialog, LiveILReadingWorker
from ui.power_measurement_diagnostics import PowerMeasurementDiagnosticsDialog
from ui.hardware_status import HardwareStatusPanel
from ui.support_logs import LoggingStatusDialog, SupportBundleDialog
from ui.admin_config import AdminConfigDialog, AdminPasswordDialog
from ui.reading_history import ReadingHistoryDialog
from ui.coc_export_dialog import CocExportDialog, format_optimization_warning
from ui.switch_ip import SwitchIpAddressDialog
from domain.support_events import SupportEventCategory, SupportLogLevel
from config.app_config import DEFAULT_PATHS


ACCENT = "#e60013"
DANGER = QColor("#ffe1dc")
DEFAULT_READ_SHORTCUT = "Return"
KEYPAD_ENTER_SHORTCUT = "Enter"
FILTER_ALL = 0
FILTER_WITHIN_LIMIT = 1
FILTER_ANY_OVER_LIMIT = 2
NORMAL_BRANDING_ASSET = "C&C lulu.png"
ADMIN_BRANDING_ASSET = "C&C lulu white eyes.png"


def bundled_asset_path(filename):
    """Return an asset path in source or a packaged PyInstaller build."""
    roots = [Path(__file__).resolve().parent]
    if getattr(sys, "_MEIPASS", None):
        roots.insert(0, Path(sys._MEIPASS))
    return next(
        (
            root_path / "assets" / filename
            for root_path in roots
            if (root_path / "assets" / filename).is_file()
        ),
        None,
    )


FILTER_1310_OVER_LIMIT = 3
FILTER_1550_OVER_LIMIT = 4
FILTER_BOTH_OVER_LIMIT = 5
STANDARD_PART_NUMBERS = [
    "OSX-150-1A-008-09-FA-00B-1H",
    "OSX-150-1A-012-09-FA-00B-2HD",
    "OSX-150-1A-016-PM-FA-00B-2H",
    "OSX-150-1A-048-09-FA-00B-3H",
    "OSX-150-1A-036-09-FA-00B-2H",
]

LIGHT_STYLESHEET = """
QMainWindow { background: #eceff1; }
QWidget#central_widget { background: #eceff1; }
QGroupBox { background: #f7f8f9; font-weight: 600; border: 1px solid #c7cdd1; border-radius: 6px; margin-top: 12px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #e60013; }
QDialog, QMessageBox, QInputDialog, QProgressDialog { background: white; color: #202124; font-size: 13px; }
QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel, QProgressDialog QLabel { color: #202124; font-size: 13px; }
QPushButton { background: #e60013; color: white; border: none; border-radius: 4px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: #b80010; }
QPushButton:disabled { background: #8b000b; color: #f3c7ca; }
QToolButton { background: #e60013; color: white; border: none; border-radius: 4px; padding: 8px 12px; font-weight: 600; }
QToolButton:hover { background: #b80010; }
QToolButton:disabled { background: #8b000b; color: #f3c7ca; }
QPushButton#hardware_primary_control { padding: 11px 20px; font-size: 16px; font-weight: 800; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: white; }
QDoubleSpinBox { padding: 5px; }
QTableWidget { background: white; border: 1px solid #c8d5d6; gridline-color: #dbe4e5; }
QHeaderView::section { background: #e4eeee; padding: 7px; border: none; font-weight: 600; }
QLabel#title { color: #e60013; font-size: 22px; font-weight: 700; }
QLabel#subtitle { color: #587073; }
QLabel#metric { color: #a6000d; font-size: 14px; font-weight: 700; }
QLabel#reading { color: #164e6b; font-size: 28px; font-weight: 800; }
QLabel#reading_channel { color: #587073; font-size: 16px; font-weight: 700; }
QLabel#reading_status { color: #587073; font-size: 16px; font-weight: 600; }
QLabel#live_indicator { color: #e60013; font-size: 14px; font-weight: 800; }
QLabel#button_title { color: white; font-size: 14px; font-weight: 800; }
QLabel#button_shortcut { color: #ffe8e8; font-size: 8px; font-weight: 500; }
QScrollArea#info_scroll_area { border: none; background: transparent; }
QWidget#info_scroll_viewport, QWidget#info_panel { background: #eceff1; }
QScrollBar:vertical { background: #e1e4e6; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #aeb7bb; min-height: 24px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

DARK_STYLESHEET = """
QMainWindow, QWidget#central_widget { background: #202124; color: #e8eaed; }
QWidget { color: #e8eaed; }
QMenuBar { background: #292b2f; color: #e8eaed; border-bottom: 1px solid #454a52; }
QMenuBar::item { background: transparent; padding: 5px 9px; }
QMenuBar::item:selected, QMenu::item:selected { background: #e60013; color: white; }
QMenu { background: #2d3035; color: #e8eaed; border: 1px solid #4a4f57; }
QMenu::item { padding: 6px 24px 6px 12px; }
QGroupBox { background: #2b2e33; color: #e8eaed; font-weight: 600; border: 1px solid #4a4f57; border-radius: 6px; margin-top: 12px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #e60013; }
QDialog, QMessageBox, QInputDialog, QProgressDialog { background: #202124; color: #e8eaed; font-size: 13px; }
QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel, QProgressDialog QLabel { color: #e8eaed; font-size: 13px; }
QPushButton { background: #e60013; color: white; border: none; border-radius: 4px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: #b80010; }
QPushButton:disabled { background: #8b000b; color: #f3c7ca; }
QToolButton { background: #e60013; color: white; border: none; border-radius: 4px; padding: 8px 12px; font-weight: 600; }
QToolButton:hover { background: #b80010; }
QToolButton:disabled { background: #8b000b; color: #f3c7ca; }
QPushButton#hardware_primary_control { padding: 11px 20px; font-size: 16px; font-weight: 800; }
QPushButton#hardware_primary_control QLabel#button_title { font-size: 16px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit { background: #373a40; color: #e8eaed; border: 1px solid #5a6069; selection-background-color: #e60013; selection-color: white; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled { background: #2b2e33; color: #9299a3; }
QComboBox QAbstractItemView { background: #373a40; color: #e8eaed; selection-background-color: #e60013; }
QDoubleSpinBox { padding: 5px; }
QTableWidget { background: #25272b; alternate-background-color: #2b2e33; color: #e8eaed; border: 1px solid #4a4f57; gridline-color: #454a52; selection-background-color: #8b000b; selection-color: white; }
QHeaderView::section { background: #3a3e45; color: #f0f2f4; padding: 7px; border: none; font-weight: 600; }
QStatusBar { background: #292b2f; color: #c7cdd4; }
QLabel#title { color: #e60013; font-size: 22px; font-weight: 700; }
QLabel#subtitle { color: #b3bbc5; }
QLabel#metric { color: #ff6670; font-size: 14px; font-weight: 700; }
QLabel#reading { color: #8bc9ee; font-size: 28px; font-weight: 800; }
QLabel#reading_channel { color: #b3bbc5; font-size: 16px; font-weight: 700; }
QLabel#reading_status { color: #b3bbc5; font-size: 16px; font-weight: 600; }
QLabel#live_indicator { color: #e60013; font-size: 14px; font-weight: 800; }
QLabel#button_title { color: white; font-size: 14px; font-weight: 800; }
QLabel#button_shortcut { color: #ffe8e8; font-size: 8px; font-weight: 500; }
QScrollArea#info_scroll_area { border: none; background: transparent; }
QWidget#info_scroll_viewport, QWidget#info_panel { background: #202124; }
QScrollBar:vertical { background: #2b2e33; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #5a6069; min-height: 24px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #373a40; color: #e8eaed; border: 1px solid #5a6069; }
"""

DARK_DANGER = QColor("#5b1f25")
DARK_DANGER_TEXT = QColor("#ffd7d7")


def format_channel_summary(channels):
    """Format an over-limit count together with its channel numbers."""
    channels = list(channels)
    count = len(channels)
    if not channels:
        return "0 (-)"
    return "%d (%s)" % (count, ", ".join(str(channel) for channel in channels))


class DependencyCheckDialog(QDialog):
    """Display a diagnostic report without adding it to run or COC metadata."""

    def __init__(self, report: DependencyReport, parent=None):
        super().__init__(parent)
        self.report = report
        self.setWindowTitle("%s - Dependency Check" % APP_NAME)
        self.resize(780, 520)

        layout = QVBoxLayout(self)
        summary = QLabel(
            "Overall status: %s\nComputer: %s\nChecked: %s"
            % (report.overall_status, report.computer_name, report.checked_at)
        )
        summary.setWordWrap(True)
        dark_mode = bool(getattr(parent, "dark_mode_enabled", False))
        summary.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: %s;"
            % (
                "#e60013"
                if report.overall_status == "ACTION REQUIRED"
                else ("#8bc9ee" if dark_mode else "#164e6b")
            )
        )
        layout.addWidget(summary)

        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlainText(report.as_text())
        layout.addWidget(self.report_view, 1)

        button_layout = QHBoxLayout()
        self.copy_button = QPushButton("Copy Report")
        self.copy_button.clicked.connect(self.copy_report)
        button_layout.addWidget(self.copy_button)
        button_layout.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def copy_report(self):
        QApplication.clipboard().setText(self.report.as_text())
        self.copy_button.setText("Report Copied")


class AboutDialog(QDialog):
    """Display Light Workbench project and release information."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About %s" % APP_NAME)
        self.setMinimumSize(500, 360)

        layout = QVBoxLayout(self)
        title = QLabel(APP_NAME)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 26px; font-weight: 800; color: #e60013;"
        )
        layout.addWidget(title)

        self.tagline_label = QLabel(APP_TAGLINE)
        self.tagline_label.setAlignment(Qt.AlignCenter)
        dark_mode = bool(getattr(parent, "dark_mode_enabled", False))
        self.tagline_label.setStyleSheet(
            "font-size: 14px; font-style: italic; color: %s;"
            % ("#b3bbc5" if dark_mode else "#164e6b")
        )
        layout.addWidget(self.tagline_label)

        self.about_view = QPlainTextEdit()
        self.about_view.setReadOnly(True)
        self.about_view.setPlainText(about_text())
        layout.addWidget(self.about_view, 1)

        button_layout = QHBoxLayout()
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self.copy_about)
        button_layout.addWidget(self.copy_button)
        button_layout.addStretch()
        close_button = QPushButton("OK")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def copy_about(self):
        QApplication.clipboard().setText(about_text())
        self.copy_button.setText("Copied")


class CompletedReplacementDialog(QDialog):
    """Record manual replacements while preserving an append-only history."""

    def __init__(
        self,
        records=None,
        recommendations=None,
        designated_spares=None,
        history=None,
        operator="",
        context=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Manage Port Replacements")
        self.setMinimumSize(760, 650)
        self.default_operator = str(operator or "").strip()
        self.context = dict(context or {})
        self.history = normalise_replacement_history(history if history is not None else records)
        self._original_events = {
            event["event_id"]: event
            for event in self.history
            if event.get("event_type") == "replacement_recorded"
        }
        initial_records = effective_replacements(self.history)
        self._row_records = []
        self._last_detail_row = -1
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Current Port", "Replacement Port"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._show_selected_details)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Record port replacements performed outside Light Workbench. "
                "This dialog does not change or verify the OSX mapping."
            )
        )
        layout.addWidget(self.table, 1)

        detail_layout = QFormLayout()
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("Example: Excessive insertion loss")
        self.operator_edit = QLineEdit(self.default_operator)
        self.operator_edit.setPlaceholderText("Initials")
        self.details_edit = QLineEdit()
        self.details_edit.setPlaceholderText("Optional additional details")
        detail_layout.addRow("Reason:", self.reason_edit)
        detail_layout.addRow("Operator:", self.operator_edit)
        detail_layout.addRow("Details:", self.details_edit)
        layout.addLayout(detail_layout)

        row_buttons = QHBoxLayout()
        add_button = QPushButton("Add Replacement")
        add_button.clicked.connect(self.add_row)
        row_buttons.addWidget(add_button)
        replace_again_button = QPushButton("Replace Again...")
        replace_again_button.clicked.connect(self.replace_again)
        row_buttons.addWidget(replace_again_button)
        remove_button = QPushButton("Void Selected")
        remove_button.setToolTip(
            "Mark the selected saved replacement inactive without deleting its history."
        )
        remove_button.clicked.connect(self.remove_selected_row)
        row_buttons.addWidget(remove_button)
        row_buttons.addStretch()
        layout.addLayout(row_buttons)

        spare_layout = QFormLayout()
        self.spare_ports_edit = QLineEdit()
        self.spare_ports_edit.setPlaceholderText("Example: 41, 46")
        self.spare_ports_edit.setToolTip(
            "Enter physical spare ports separated by commas."
        )
        self.spare_ports_edit.setText(
            ", ".join(str(port) for port in sorted(designated_spares or []))
        )
        spare_layout.addRow("Designated spare ports:", self.spare_ports_edit)
        layout.addLayout(spare_layout)

        layout.addWidget(QLabel("Append-only audit history:"))
        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(
            ["Current", "Replacement", "Reason", "Operator", "Recorded", "Event"]
        )
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.history_table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept_records)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if not initial_records:
            initial_records = [
                {
                    "current_port": item["current_physical_port"],
                    "replacement_port": item["candidate_physical_port"],
                }
                for item in (recommendations or [])
            ]
        if initial_records:
            for record in initial_records:
                self.add_row(record)
        else:
            self.add_row()
        self._refresh_history_table()

    def add_row(self, record=None):
        self._sync_selected_details()
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = record or {}
        current_port = values.get("current_port", values.get("original_physical_port", 0))
        replacement_port = values.get(
            "replacement_port", values.get("replacement_physical_port", 0)
        )
        for column, value in enumerate((current_port, replacement_port)):
            spin = QSpinBox()
            spin.setRange(0, 256)
            spin.setSpecialValueText("")
            spin.setValue(int(value or 0))
            self.table.setCellWidget(row, column, spin)
        self._row_records.append(dict(values))
        self.table.selectRow(row)
        self._show_selected_details()

    def _sync_selected_details(self):
        row = self._last_detail_row
        if row < 0:
            row = self.table.currentRow()
        if row < 0 or row >= len(self._row_records):
            return
        record = self._row_records[row]
        record["current_port"] = self.table.cellWidget(row, 0).value()
        record["replacement_port"] = self.table.cellWidget(row, 1).value()
        record["reason"] = self.reason_edit.text().strip()
        record["operator"] = self.operator_edit.text().strip()
        record["reason_details"] = self.details_edit.text().strip()

    def _show_selected_details(self):
        previous_row = self._last_detail_row
        if 0 <= previous_row < len(self._row_records):
            record = self._row_records[previous_row]
            record["reason"] = self.reason_edit.text().strip()
            record["operator"] = self.operator_edit.text().strip()
            record["reason_details"] = self.details_edit.text().strip()
        row = self.table.currentRow()
        if row < 0 or row >= len(self._row_records):
            self.reason_edit.clear()
            self.operator_edit.setText(self.default_operator)
            self.details_edit.clear()
            self._last_detail_row = -1
            return
        self._last_detail_row = row
        record = self._row_records[row]
        self.reason_edit.setText(str(record.get("reason") or ""))
        self.operator_edit.setText(
            str(record.get("operator") or self.default_operator or "")
        )
        self.details_edit.setText(str(record.get("reason_details") or ""))

    def replace_again(self):
        self._sync_selected_details()
        row = self.table.currentRow()
        if row < 0 or row >= len(self._row_records):
            return
        previous = self._row_records[row]
        if not previous.get("event_id"):
            QMessageBox.information(
                self,
                "Replacement history unavailable",
                "Save this replacement first, then use Replace Again.",
            )
            return
        self.add_row(
            {
                "current_port": previous.get("replacement_port", 0),
                "replacement_port": 0,
                "root_port": previous.get("root_port", previous.get("current_port")),
                "previous_record_id": previous.get("event_id"),
            }
        )

    def remove_selected_row(self):
        self._sync_selected_details()
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self._row_records.pop(row)

    def _build_history(self):
        self._sync_selected_details()
        original_active = {
            event_id: event
            for event_id, event in self._original_events.items()
            if event_id in {
                record.get("event_id") for record in effective_replacements(self.history)
            }
        }
        retained_ids = {
            record.get("event_id")
            for record in self._row_records
            if record.get("event_id")
        }
        new_history = list(self.history)
        for event_id, event in original_active.items():
            if event_id not in retained_ids:
                new_history.append(
                    new_replacement_void_event(
                        event_id,
                        self.default_operator or "Not recorded",
                        "Removed from active replacements",
                    )
                )

        for record in self._row_records:
            current_port = record.get("current_port", 0)
            replacement_port = record.get("replacement_port", 0)
            if not current_port and not replacement_port:
                continue
            if not current_port or not replacement_port:
                raise ValueError(
                    "Complete both port fields in each replacement row, or remove the blank row."
                )
            event_id = record.get("event_id")
            original = self._original_events.get(event_id) if event_id else None
            if original:
                unchanged = (
                    int(original.get("root_port") or original["current_port"])
                    == int(current_port)
                    and int(original["replacement_port"]) == int(replacement_port)
                    and str(original.get("reason") or "") == str(record.get("reason") or "")
                    and str(original.get("operator") or "") == str(record.get("operator") or "")
                    and str(original.get("reason_details") or "")
                    == str(record.get("reason_details") or "")
                )
                if unchanged:
                    continue
                new_history.append(
                    new_replacement_void_event(
                        event_id,
                        record.get("operator") or self.default_operator or "Not recorded",
                        "Corrected replacement record",
                    )
                )
                current_port = original["current_port"]
                root_port = original.get("root_port", current_port)
                previous_record_id = original.get("previous_record_id")
            else:
                root_port = record.get("root_port", current_port)
                previous_record_id = record.get("previous_record_id")
                if previous_record_id:
                    previous_event = self._original_events.get(previous_record_id)
                    if previous_event and int(previous_event["replacement_port"]) != int(current_port):
                        raise ValueError(
                            "A repeated replacement must start from the previous replacement port."
                        )
            new_history.append(
                new_replacement_event(
                    current_port,
                    replacement_port,
                    record.get("reason"),
                    record.get("operator") or self.default_operator,
                    reason_details=record.get("reason_details"),
                    previous_record_id=previous_record_id,
                    root_port=root_port,
                    source_run_number=self.context.get("source_run_number"),
                    main_board_serial=self.context.get("main_board_serial"),
                    switch_serial=self.context.get("switch_serial"),
                    record_id=event_id if not original else None,
                )
            )
        return normalise_replacement_history(new_history)

    def accept_records(self):
        try:
            self.history = self._build_history()
            self.records = effective_replacements(self.history)
            normalise_completed_replacements(self.records)
            self.designated_spares = self._spares_from_edit()
            replacement_ports = {
                record["replacement_port"] for record in self.records
            }
            unlisted_spares = sorted(
                replacement_ports.difference(self.designated_spares)
            )
            if self.designated_spares and unlisted_spares:
                response = QMessageBox.question(
                    self,
                    "Replacement is not a designated spare",
                    "Port(s) %s are used as replacements but are not designated "
                    "spares. Add them to the designated-spare list?"
                    % ", ".join(str(port) for port in unlisted_spares),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if response == QMessageBox.Yes:
                    self.designated_spares = sorted(
                        set(self.designated_spares).union(unlisted_spares)
                    )
        except ValueError as error:
            QMessageBox.warning(self, "Invalid replacement or spare record", str(error))
            return
        self.accept()

    def _refresh_history_table(self):
        self.history_table.setRowCount(0)
        for event in self.history:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            if event.get("event_type") == "replacement_recorded":
                values = (
                    event.get("current_port", ""),
                    event.get("replacement_port", ""),
                    event.get("reason", ""),
                    event.get("operator", ""),
                    event.get("recorded_at_utc", "") or "Not recorded",
                    "Recorded",
                )
            else:
                values = (
                    "",
                    "",
                    event.get("reason", ""),
                    event.get("operator", ""),
                    event.get("recorded_at_utc", "") or "Not recorded",
                    "Voided",
                )
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(str(value)))

    def _spares_from_edit(self):
        values = []
        seen = set()
        raw_value = self.spare_ports_edit.text().strip()
        if not raw_value:
            return values
        for value in raw_value.replace(";", ",").split(","):
            value = value.strip()
            if not value:
                continue
            try:
                port = int(value)
            except ValueError:
                raise ValueError("Designated spare ports must be whole numbers.")
            if port < 1 or port > 256:
                raise ValueError("Designated spare ports must be between 1 and 256.")
            if port not in seen:
                values.append(port)
                seen.add(port)
        return sorted(values)


class ShortcutButton(QPushButton):
    """A primary action button with a compact live shortcut label."""

    def __init__(self, title, parent=None):
        super().__init__("", parent)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("button_title")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.shortcut_label = QLabel("[Unassigned]", self)
        self.shortcut_label.setObjectName("button_shortcut")
        self.shortcut_label.setAlignment(Qt.AlignCenter)
        self.shortcut_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        button_layout = QVBoxLayout(self)
        button_layout.setContentsMargins(8, 4, 8, 4)
        button_layout.setSpacing(0)
        button_layout.addWidget(self.title_label)
        button_layout.addWidget(self.shortcut_label)
        self.setAccessibleName(title)

    def set_shortcut(self, shortcut):
        """Display a QKeySequence or string in brackets under the title."""
        text = shortcut.toString() if isinstance(shortcut, QKeySequence) else str(shortcut)
        self.shortcut_label.setText("[%s]" % (text or "Unassigned"))


class MainWindow(QMainWindow):
    reference_values_changed = pyqtSignal(float, float)

    def __init__(
        self,
        initial_path: str | None = None,
        support_logger=None,
        part_lookup_controller=None,
    ):
        super().__init__()
        self.support_logger = support_logger or get_support_logging_service()
        self.current_run_workflow = None
        self.reference_workflow = None
        self._support_log_size_warning_shown = False
        self.run_data: RunData | None = None
        self.admin_session = AdminSession()
        self.reference_session = ReferenceSession()
        self._last_applied_reference_snapshot = None
        self.active_run_reference_snapshot = None
        self.pending_reading_validation = None
        self._syncing_reference_widgets = False
        self.limit_profile_repository = LimitProfileRepository()
        self.limit_profiles = default_limit_profiles()
        self.limit_profile_error = None
        try:
            self.limit_profiles = self.limit_profile_repository.load_profiles()
        except (OSError, ValueError, TypeError) as error:
            self.limit_profile_error = str(error)
        self.active_limit_profile = self.limit_profiles["OSX-150"]
        # Keep adapter selection in one composition point. Passing the module
        # aliases preserves the existing test seam while allowing future
        # workstation-specific hardware configurations.
        self.hardware_factory = HardwareFactory(
            power_meter_factory=SantecPowerMeter,
            switch_factory=self._create_switch_adapter,
        )
        self.hardware_connection_manager = HardwareConnectionManager(
            self.hardware_factory,
            self,
            support_logger=self.support_logger,
        )
        self.hardware_connection_manager.device_status_changed.connect(
            self._hardware_device_status_changed
        )
        self.hardware_connection_manager.snapshot_changed.connect(
            self._hardware_connection_snapshot_changed
        )
        self.hardware_connection_manager.operation_finished.connect(
            self._hardware_connection_operation_finished
        )
        self.hardware_connection_manager.switch_ip_query_finished.connect(
            self._switch_ip_query_finished
        )
        self.coc_exporter = FileCocExporter(self.support_logger)
        self.part_lookup_controller = part_lookup_controller or PartNumberLookupController(
            self.coc_exporter.find_part_number,
            self,
        )
        self.part_lookup_controller.succeeded.connect(
            self._automatic_part_lookup_succeeded
        )
        self.part_lookup_controller.failed.connect(self._automatic_part_lookup_failed)
        self._device_connection_states = {}
        self._connected_switch_serial = ""
        self._switch_ip_query_operation_id = ""
        self._active_part_lookup_request = None
        self._part_lookup_requests = {}
        self.run_repository = FileRunRepository(self.support_logger)
        self.unit_repository = FileUnitRepository(self.support_logger)
        self.coc_workflow = CocWorkflow(
            self.run_repository,
            self.unit_repository,
        )
        self.demo_meter: SimulatedPowerMeter | None = None
        self.demo_channel = 0
        self.demo_measurement = None
        self.current_loss_1310 = None
        self.current_loss_1550 = None
        self.current_reading_channel = None
        self.hardware_thread = None
        self.hardware_worker = None
        self.hardware_controller = HardwareRunController(self)
        self.reference_controller = LiveILReadingController(
            self,
            worker_factory=LiveILReadingWorker,
        )
        self.reference_controller.connected.connect(self._reference_meter_connected)
        self.reference_controller.reference_ready.connect(
            self._reference_calculation_ready
        )
        self.reference_controller.failed.connect(self._reference_calculation_failed)
        # Live Write Mode is session-only and is the normal first-launch
        # workflow.
        self.live_write_mode_enabled = True
        self.reference_progress = None
        self.run_recorder = None
        self.unit_directory = None
        self.unit_record = {}
        self.replacement_analysis = None
        self.replacement_history = []
        self.completed_replacements = []
        self.designated_spares = []
        self.hardware_session = HardwareRunSession()
        self.switch_test_timer = None
        self.displayed_records = []
        self.comparison_run_data = None
        self.comparison_run_number = None
        self.settings = QSettings("Light Workbench", "LightWorkbench")
        self._migrate_legacy_settings()
        self.switch_visa_address = str(
            self.settings.value("switch_visa_address", "") or ""
        ).strip()
        self.dark_mode_enabled = self.settings.value(
            "dark_mode",
            True,
            type=bool,
        )
        self.continue_shortcut = None
        self.keypad_enter_shortcut = None
        self.retest_shortcut = None
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 720)
        self._build_ui()
        self._refresh_admin_branding()
        self._connect_hardware_controller()
        self._record_support(
            SupportEventCategory.APPLICATION,
            "application.main_window_ready",
            status="success",
        )
        if self.support_logger is not None and self.support_logger.status().fallback_active:
            QTimer.singleShot(0, self._show_degraded_logging_warning)
        if self.support_logger is not None:
            QTimer.singleShot(0, self._warn_if_support_logs_exceed_limit)
            self.support_log_size_timer = QTimer(self)
            self.support_log_size_timer.setInterval(30000)
            self.support_log_size_timer.timeout.connect(
                self._warn_if_support_logs_exceed_limit
            )
            self.support_log_size_timer.start()
        if initial_path:
            self.load_path(Path(initial_path))

    # Compatibility properties keep existing UI/test call sites stable while
    # the actual hardware workflow state lives in one application-layer model.
    @property
    def hardware_retest(self):
        return self.hardware_session.retest

    @hardware_retest.setter
    def hardware_retest(self, value):
        self.hardware_session.retest = bool(value)

    @property
    def hardware_pending_reading(self):
        return self.hardware_session.pending_reading

    @hardware_pending_reading.setter
    def hardware_pending_reading(self, value):
        self.hardware_session.pending_reading = value

    @property
    def hardware_pending_channel(self):
        return self.hardware_session.pending_channel

    @hardware_pending_channel.setter
    def hardware_pending_channel(self, value):
        self.hardware_session.pending_channel = value

    @property
    def hardware_pending_physical_port(self):
        return self.hardware_session.pending_physical_port

    @hardware_pending_physical_port.setter
    def hardware_pending_physical_port(self, value):
        self.hardware_session.pending_physical_port = value

    @property
    def hardware_manual_channel_order(self):
        return self.hardware_session.manual_channel_order

    @hardware_manual_channel_order.setter
    def hardware_manual_channel_order(self, value):
        self.hardware_session.manual_channel_order = bool(value)

    @property
    def hardware_full_pass(self):
        return self.hardware_session.full_pass

    @hardware_full_pass.setter
    def hardware_full_pass(self, value):
        self.hardware_session.full_pass = bool(value)

    @property
    def hardware_configured_channel_count(self):
        return self.hardware_session.configured_channel_count

    @hardware_configured_channel_count.setter
    def hardware_configured_channel_count(self, value):
        self.hardware_session.configured_channel_count = value

    @property
    def hardware_run_active(self):
        """Compatibility view of the controller-owned hardware lifecycle."""
        return self.hardware_controller.is_active or self.hardware_thread is not None

    @property
    def reference_thread(self):
        """Compatibility view of the shared reference controller thread."""
        return self.reference_controller.thread

    @property
    def reference_worker(self):
        """Compatibility view of the shared reference controller worker."""
        return self.reference_controller.worker

    def _connect_hardware_controller(self):
        """Connect controller events to the existing UI handlers."""
        self.hardware_controller.channel_selection_required.connect(
            self.hardware_channel_selection_required
        )
        self.hardware_controller.continuation_selection_required.connect(
            self.hardware_continuation_selection_required
        )
        self.hardware_controller.channel_configuration_ready.connect(
            self.hardware_channel_configuration_ready
        )
        self.hardware_controller.operator_required.connect(
            self.hardware_operator_required
        )
        self.hardware_controller.reading_ready.connect(self.hardware_reading_ready)
        self.hardware_controller.device_status_changed.connect(
            self._hardware_device_status_changed
        )
        self.hardware_controller.progress_changed.connect(
            self.hardware_progress_changed
        )
        self.hardware_controller.completed.connect(self.hardware_completed)
        self.hardware_controller.stopped.connect(self.hardware_stopped)
        self.hardware_controller.failed.connect(self.hardware_failed)
        self.hardware_controller.thread_finished.connect(
            self.hardware_thread_finished
        )

    def _hardware_device_status_changed(self, device_info):
        """Render transient device identity reported by the run controller."""
        if hasattr(self, "hardware_status_panel"):
            self.hardware_status_panel.set_device_status(device_info)
        if device_info.connection_warning:
            self.statusBar().showMessage(device_info.connection_warning, 8000)
        self._handle_connected_switch_metadata(device_info)

    def _handle_connected_switch_metadata(self, device_info):
        """Autofill setup metadata once for each real switch connection."""
        category = device_info.category
        previous_state = self._device_connection_states.get(
            category,
            ConnectionState.DISCONNECTED,
        )
        self._device_connection_states[category] = device_info.state
        if (
            category != DeviceCategory.OPTICAL_SWITCH
            or device_info.state != ConnectionState.CONNECTED
        ):
            return

        model = normalize_switch_model(device_info.model)
        if model not in ("OSX-100", "OSX-150"):
            return
        serial = self.coc_exporter.normalise_serial(device_info.serial_number)
        if not serial:
            return

        serial_changed = serial.casefold() != self._connected_switch_serial.casefold()
        new_connection = previous_state in (
            ConnectionState.DISCONNECTED,
            ConnectionState.CONNECTING,
            ConnectionState.ERROR,
        )
        if not serial_changed and not new_connection:
            return
        self._connected_switch_serial = serial
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "metadata.main_board_serial_detected",
            model=model,
            unit_serial=serial,
            lookup_mode="automatic",
            status="detected",
        )

        if self.run_data is not None or self.hardware_run_active:
            reason = (
                "active_run" if self.hardware_run_active else "loaded_historical_run"
            )
            self._record_support(
                SupportEventCategory.WORKFLOW,
                "metadata.autofill_skipped",
                model=model,
                unit_serial=serial,
                lookup_mode="automatic",
                reason=reason,
                status="skipped",
            )
            self.statusBar().showMessage(
                "Connected %s serial %s was not copied into the loaded run metadata."
                % (model, serial),
                8000,
            )
            return

        current_serial = self.coc_exporter.normalise_serial(
            self.hardware_main_board_serial.text()
        )
        form_serial_changed = current_serial.casefold() != serial.casefold()
        self._active_part_lookup_request = None
        if form_serial_changed:
            self.hardware_main_board_serial.setText(serial)
            self.hardware_part_number.setCurrentText("")
            self.metadata_labels["Part number"].setText("-")
        elif self.hardware_part_number.currentText().strip():
            return

        self._start_automatic_part_lookup(serial, model)

    def _start_automatic_part_lookup(self, serial, model):
        try:
            request_id = self.part_lookup_controller.start(
                serial,
                DEFAULT_PART_LOOKUP_ROOT,
            )
        except Exception as error:
            self._show_automatic_part_lookup_failure(
                serial,
                model,
                classify_part_lookup_error(error),
                str(error),
            )
            return
        self._active_part_lookup_request = request_id
        self._part_lookup_requests[request_id] = (serial, model)
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "metadata.part_lookup_started",
            model=model,
            unit_serial=serial,
            lookup_mode="automatic",
            lookup_request_id=request_id,
            status="started",
        )

    def _automatic_part_lookup_is_current(self, request_id, serial):
        if request_id != self._active_part_lookup_request:
            return False
        if self.run_data is not None or self.hardware_run_active:
            return False
        current_serial = self.coc_exporter.normalise_serial(
            self.hardware_main_board_serial.text()
        )
        if current_serial.casefold() != serial.casefold():
            return False
        return not self.hardware_part_number.currentText().strip()

    def _automatic_part_lookup_succeeded(self, request_id, serial, part_number):
        serial, model = self._part_lookup_requests.pop(
            request_id,
            (serial, "OSX"),
        )
        if not self._automatic_part_lookup_is_current(request_id, serial):
            self._record_stale_part_lookup(request_id, serial, model)
            return
        self._active_part_lookup_request = None
        self._apply_part_number_result(part_number, update_run_data=False)
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "metadata.part_lookup_succeeded",
            model=model,
            unit_serial=serial,
            part_number=part_number,
            lookup_mode="automatic",
            lookup_request_id=request_id,
            status="success",
        )
        self.statusBar().showMessage(
            "Main board serial %s detected; part number %s found."
            % (serial, part_number),
            8000,
        )

    def _automatic_part_lookup_failed(
        self,
        request_id,
        serial,
        failure_category,
        message,
    ):
        serial, model = self._part_lookup_requests.pop(
            request_id,
            (serial, "OSX"),
        )
        if not self._automatic_part_lookup_is_current(request_id, serial):
            self._record_stale_part_lookup(request_id, serial, model)
            return
        self._active_part_lookup_request = None
        self._show_automatic_part_lookup_failure(
            serial,
            model,
            failure_category,
            message,
            request_id=request_id,
        )

    def _show_automatic_part_lookup_failure(
        self,
        serial,
        model,
        failure_category,
        message,
        *,
        request_id=None,
    ):
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "metadata.part_lookup_failed",
            level=SupportLogLevel.WARNING,
            model=model,
            unit_serial=serial,
            lookup_mode="automatic",
            lookup_request_id=request_id,
            reason=failure_category,
            error_message=message,
            status="error",
        )
        detail = " ".join(str(message).split())
        self.statusBar().showMessage(
            "%s connected and main board serial %s was detected, but the part-number "
            "lookup failed: %s Enter the part number manually or use Lookup Part "
            "Number to retry." % (model, serial, detail),
            12000,
        )

    def _record_stale_part_lookup(self, request_id, serial, model):
        if self._active_part_lookup_request == request_id:
            self._active_part_lookup_request = None
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "metadata.part_lookup_result_ignored",
            level=SupportLogLevel.WARNING,
            model=model,
            unit_serial=serial,
            lookup_mode="automatic",
            lookup_request_id=request_id,
            reason="stale_or_protected_metadata",
            status="ignored",
        )

    def _hardware_connection_snapshot_changed(self, _snapshot):
        """Apply capability readiness to only hardware-dependent controls."""
        if self.reference_session.is_valid and not self._reference_hardware_matches_snapshot():
            self.invalidate_reference("The measurement hardware connection changed; recalculate the reference.")
        if self.run_data is None:
            model = self._connected_switch_model()
            profile = self.limit_profiles.get(model)
            if profile is not None and hasattr(self, "criteria_profile_label"):
                self._set_active_limit_profile(profile)
        self._update_hardware_readiness_controls()

    def _update_hardware_readiness_controls(self):
        if not hasattr(self, "start_hardware_button"):
            return
        run_available = (
            self.hardware_connection_manager.run_ready
            and not self.hardware_run_active
        )
        self.start_hardware_button.setEnabled(run_available)
        self.start_hardware_button.setToolTip(
            "Start a run using the connected measurement hardware and optical switch."
            if run_available
            else "Connect the measurement hardware and optical switch before starting a run."
        )
        reference_available = (
            self.hardware_connection_manager.measurement_ready
            and not self.hardware_run_active
            and self.reference_thread is None
        )
        self.calculate_reference_button.setEnabled(reference_available)
        self.calculate_reference_button.setToolTip(
            "Calculate both reference offsets using the connected measurement hardware."
            if reference_available
            else "Connect the measurement hardware before calculating a reference."
        )
        self._refresh_reference_controls()
        self.retest_button.setEnabled(
            bool(self.run_data and self.run_data.measurements)
            and run_available
        )

    def _hardware_connection_operation_finished(self, operation_name, results):
        if hasattr(self, "connect_hardware_button"):
            self.connect_hardware_button.setEnabled(True)
        failures = [
            "%s: %s" % (self._hardware_capability_label(capability), message)
            for capability, message in results.items()
            if message
        ]
        if failures:
            QMessageBox.warning(
                self,
                operation_name,
                "The hardware operation completed with the following issue(s):\n\n"
                + "\n\n".join(failures),
            )
        else:
            self.statusBar().showMessage("%s completed." % operation_name, 5000)
        self._update_hardware_readiness_controls()

    @staticmethod
    def _hardware_capability_label(capability):
        return {
            HardwareCapability.MEASUREMENT: "Measurement hardware",
            HardwareCapability.LASER_SOURCE: "Laser source",
            HardwareCapability.OPTICAL_SWITCH: "Optical switch",
        }.get(capability, str(capability))

    def _start_hardware_connection_operation(self, operation):
        if self.hardware_run_active:
            QMessageBox.warning(
                self,
                "Hardware run active",
                "Stop the current hardware run before changing connections.",
            )
            return
        self.connect_hardware_button.setEnabled(False)
        operation()

    def _create_switch_adapter(self):
        """Create a switch using separate manual and remembered addresses."""
        return OSX150(
            resource_address=self.switch_visa_address,
            last_known_address=str(
                self.settings.value("last_switch_visa_address", "") or ""
            ).strip(),
            address_observer=self._remember_automatically_detected_switch,
        )

    def _record_support(self, category, event, **fields):
        """Best-effort UI event recording that never changes an operator action."""
        if self.support_logger is None:
            return False
        try:
            return self.support_logger.record(category, event, **fields)
        except Exception:
            return False

    def _new_workflow(self, workflow_type):
        if self.support_logger is None:
            return None
        return self.support_logger.new_workflow(workflow_type)

    def _meter_proxy_for_workflow(
        self,
        owner_token,
        owner_label,
        workflow,
        *,
        connect_if_needed,
    ):
        meter = self.hardware_connection_manager.create_power_meter_proxy(
            owner_token,
            owner_label,
            connect_if_needed=connect_if_needed,
        )
        if workflow is not None:
            meter.set_trace_metadata(
                workflow_id=workflow.workflow_id,
                workflow_type=workflow.workflow_type,
            )
        return meter

    def _switch_proxy_for_workflow(
        self,
        owner_token,
        owner_label,
        workflow,
        *,
        connect_if_needed,
    ):
        switch = self.hardware_connection_manager.create_switch_proxy(
            owner_token,
            owner_label,
            connect_if_needed=connect_if_needed,
        )
        if workflow is not None:
            switch.set_trace_metadata(
                workflow_id=workflow.workflow_id,
                workflow_type=workflow.workflow_type,
            )
        return switch

    @staticmethod
    def _remember_automatically_detected_switch(address):
        """Persist successful automatic discovery from the worker thread."""
        QSettings("Light Workbench", "LightWorkbench").setValue(
            "last_switch_visa_address", address
        )

    def _build_ui(self):
        self.setStyleSheet(self._theme_stylesheet(self.dark_mode_enabled))

        self.open_csv_action = QAction("Open CSV Run...", self)
        self.open_csv_action.triggered.connect(self.open_csv)
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.open_csv_action)
        data_output_action = QAction("Data Output Folder", self)
        data_output_action.triggered.connect(self.open_data_output_folder)
        file_menu.addAction(data_output_action)

        edit_menu = self.menuBar().addMenu("Edit")
        keybinds_action = QAction("Keybinds...", self)
        keybinds_action.triggered.connect(self.show_keybind_dialog)
        edit_menu.addAction(keybinds_action)
        self.admin_mode_action = QAction("Admin Mode...", self)
        self.admin_mode_action.setCheckable(True)
        self.admin_mode_action.triggered.connect(self.toggle_admin_mode)
        edit_menu.addAction(self.admin_mode_action)
        self.admin_config_action = QAction("Admin Config...", self)
        self.admin_config_action.setEnabled(False)
        self.admin_config_action.triggered.connect(self.show_admin_config)
        edit_menu.addAction(self.admin_config_action)

        tools_menu = self.menuBar().addMenu("Tools")
        switch_address_action = QAction("Switch VISA Address...", self)
        switch_address_action.triggered.connect(self.choose_switch_visa_address)
        tools_menu.addAction(switch_address_action)
        self.get_switch_ip_action = QAction("Get IP...", self)
        self.get_switch_ip_action.setToolTip(
            "Read the LAN address from the already-connected optical switch."
        )
        self.get_switch_ip_action.triggered.connect(self.show_switch_ip)
        tools_menu.addAction(self.get_switch_ip_action)
        dependency_action = QAction("Check Dependencies...", self)
        dependency_action.triggered.connect(self.show_dependency_check)
        tools_menu.addAction(dependency_action)
        red_light_action = QAction("Red Light Test...", self)
        red_light_action.triggered.connect(self.show_red_light_test)
        tools_menu.addAction(red_light_action)
        live_il_action = QAction("Live IL Reading...", self)
        live_il_action.triggered.connect(self.show_live_il_reading)
        tools_menu.addAction(live_il_action)
        power_diagnostics_action = QAction(
            "Power Measurement Diagnostics...",
            self,
        )
        power_diagnostics_action.triggered.connect(
            self.show_power_measurement_diagnostics
        )
        tools_menu.addAction(power_diagnostics_action)
        self.live_write_mode_action = QAction("Live Write Mode", self)
        self.live_write_mode_action.setCheckable(True)
        self.live_write_mode_action.setChecked(self.live_write_mode_enabled)
        self.live_write_mode_action.triggered.connect(self.toggle_live_write_mode)
        tools_menu.addAction(self.live_write_mode_action)
        self.dark_mode_action = QAction("Dark Mode", self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setChecked(self.dark_mode_enabled)
        self.dark_mode_action.triggered.connect(self.toggle_dark_mode)
        tools_menu.addAction(self.dark_mode_action)

        lookup_folder_action = QAction("Part Number Lookup Folder", self)
        lookup_folder_action.triggered.connect(self.open_part_lookup_folder)
        file_menu.addAction(lookup_folder_action)
        template_action = QAction("COC Template...", self)
        template_action.triggered.connect(self.choose_coc_template)
        file_menu.addAction(template_action)
        self.write_coc_action = QAction("Write COC...", self)
        self.write_coc_action.triggered.connect(self.write_coc)
        self.write_coc_action.setEnabled(False)
        file_menu.addAction(self.write_coc_action)
        file_menu.addAction("Exit", self.close)

        help_menu = self.menuBar().addMenu("Help")
        instructions_action = QAction("IL Instructions", self)
        instructions_action.triggered.connect(self.show_il_instructions)
        help_menu.addAction(instructions_action)
        self.support_logs_menu = help_menu.addMenu("Support Logs")
        self.open_logs_action = QAction("Open Logs Folder", self)
        self.open_logs_action.triggered.connect(self.open_support_logs_folder)
        self.support_logs_menu.addAction(self.open_logs_action)
        self.export_support_bundle_action = QAction("Export Support Bundle...", self)
        self.export_support_bundle_action.triggered.connect(
            self.export_support_bundle_dialog
        )
        self.support_logs_menu.addAction(self.export_support_bundle_action)
        self.copy_logs_path_action = QAction("Copy Logs Folder Path", self)
        self.copy_logs_path_action.triggered.connect(self.copy_support_logs_path)
        self.support_logs_menu.addAction(self.copy_logs_path_action)
        self.logging_status_action = QAction("Logging Status...", self)
        self.logging_status_action.triggered.connect(self.show_logging_status)
        self.support_logs_menu.addAction(self.logging_status_action)
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        central = QWidget()
        central.setObjectName("central_widget")
        root = QVBoxLayout(central)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        titles.addWidget(title)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("company_logo")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setToolTip("C&C Lulu")
        self.logo_label.setMaximumSize(140, 56)
        header.addWidget(self.logo_label)
        header.addLayout(titles)
        header.addStretch()
        self.hardware_status_panel = HardwareStatusPanel(central)
        self.hardware_status_panel.set_laser_visible(
            self.hardware_connection_manager.has_separate_laser
        )
        header.addWidget(self.hardware_status_panel)
        self.connect_hardware_button = QToolButton()
        self.connect_hardware_button.setText("Connect Hardware...")
        self.connect_hardware_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.connect_hardware_button.setToolTip(
            "Connect all hardware required for a normal IL run, or use the "
            "menu to connect one hardware capability."
        )
        self.connect_hardware_button.clicked.connect(
            lambda: self._start_hardware_connection_operation(
                self.hardware_connection_manager.connect_all
            )
        )
        hardware_menu = QMenu(self.connect_hardware_button)
        connect_all_action = hardware_menu.addAction("Connect All Required Hardware")
        connect_all_action.triggered.connect(
            lambda: self._start_hardware_connection_operation(
                self.hardware_connection_manager.connect_all
            )
        )
        connect_measurement_action = hardware_menu.addAction(
            "Connect Measurement Hardware"
        )
        connect_measurement_action.triggered.connect(
            lambda: self._start_hardware_connection_operation(
                self.hardware_connection_manager.connect_measurement_hardware
            )
        )
        connect_switch_action = hardware_menu.addAction("Connect Optical Switch")
        connect_switch_action.triggered.connect(
            lambda: self._start_hardware_connection_operation(
                self.hardware_connection_manager.connect_switch
            )
        )
        hardware_menu.addSeparator()
        disconnect_measurement_action = hardware_menu.addAction(
            "Disconnect Measurement Hardware"
        )
        disconnect_measurement_action.triggered.connect(
            lambda: self._start_hardware_connection_operation(
                self.hardware_connection_manager.disconnect_measurement_hardware
            )
        )
        disconnect_switch_action = hardware_menu.addAction(
            "Disconnect Optical Switch"
        )
        disconnect_switch_action.triggered.connect(
            lambda: self._start_hardware_connection_operation(
                self.hardware_connection_manager.disconnect_switch
            )
        )
        disconnect_all_action = hardware_menu.addAction("Disconnect All Hardware")
        disconnect_all_action.triggered.connect(
            lambda: self._start_hardware_connection_operation(
                self.hardware_connection_manager.disconnect_all
            )
        )
        self.connect_hardware_button.setMenu(hardware_menu)
        header.addWidget(self.connect_hardware_button)
        self.open_csv_button = QPushButton("Open Existing CSV")
        self.open_csv_button.clicked.connect(self.open_csv)
        header.addWidget(self.open_csv_button)
        root.addLayout(header)

        self.file_label = QLabel("No run loaded")
        self.file_label.setObjectName("subtitle")
        root.addWidget(self.file_label)

        setup_row = QHBoxLayout()

        hardware_setup_box = QGroupBox("Hardware test setup")
        self.hardware_setup_box = hardware_setup_box
        hardware_setup_layout = QGridLayout(hardware_setup_box)
        hardware_setup_layout.addWidget(QLabel("Channel mode:"), 0, 0)
        self.hardware_channel_mode = QComboBox()
        self.hardware_channel_mode.addItems(["Full configured pass", "Single channel", "Specific channels/ranges"])
        self.hardware_channel_mode.currentIndexChanged.connect(
            self.update_channel_mode_controls
        )
        hardware_setup_layout.addWidget(self.hardware_channel_mode, 0, 1)
        self.channel_mode_context = QWidget()
        channel_mode_context_layout = QHBoxLayout(self.channel_mode_context)
        channel_mode_context_layout.setContentsMargins(0, 0, 0, 0)
        channel_mode_context_layout.setSpacing(8)
        self.hardware_channel_label = QLabel("Channel:")
        channel_mode_context_layout.addWidget(self.hardware_channel_label)
        self.hardware_single_channel = QSpinBox()
        self.hardware_single_channel.setRange(1, 256)
        self.hardware_single_channel.setValue(1)
        channel_mode_context_layout.addWidget(self.hardware_single_channel)
        self.manual_channel_order_checkbox = QCheckBox(
            "Choose channel order manually"
        )
        self.manual_channel_order_checkbox.setToolTip(
            "Optional full-pass mode for scattered channels; repeated channels "
            "replace their previous saved result."
        )
        channel_mode_context_layout.addWidget(self.manual_channel_order_checkbox)
        channel_mode_context_layout.addStretch()
        hardware_setup_layout.addWidget(
            self.channel_mode_context,
            0,
            2,
            1,
            2,
        )
        self.hardware_channel_ranges_label = QLabel("Channels/ranges:")
        hardware_setup_layout.addWidget(self.hardware_channel_ranges_label, 1, 0)
        self.hardware_channel_ranges = QLineEdit()
        self.hardware_channel_ranges.setPlaceholderText("Example: 1, 9, 10-15, 27")
        hardware_setup_layout.addWidget(self.hardware_channel_ranges, 1, 1, 1, 3)

        hardware_setup_layout.addWidget(QLabel("Main board serial:"), 2, 0)
        self.hardware_main_board_serial = QLineEdit()
        hardware_setup_layout.addWidget(self.hardware_main_board_serial, 2, 1)
        self.lookup_part_number_button = QPushButton("Lookup Part Number")
        self.lookup_part_number_button.clicked.connect(self.lookup_part_number)
        hardware_setup_layout.addWidget(self.lookup_part_number_button, 2, 2, 1, 2)

        hardware_setup_layout.addWidget(QLabel("Switch serial:"), 3, 0)
        self.hardware_switch_serial = QLineEdit()
        hardware_setup_layout.addWidget(self.hardware_switch_serial, 3, 1)
        hardware_setup_layout.addWidget(QLabel("Part number:"), 3, 2)
        self.hardware_part_number = QComboBox()
        self.hardware_part_number.setEditable(True)
        self.hardware_part_number.addItems(STANDARD_PART_NUMBERS)
        self.hardware_part_number.setCurrentIndex(-1)
        self.hardware_part_number.lineEdit().setPlaceholderText(
            "Type, select, or look up part number"
        )
        self.hardware_part_number.setToolTip(
            "Type a part number, choose a standard part number, or use lookup."
        )
        hardware_setup_layout.addWidget(self.hardware_part_number, 3, 3)

        hardware_setup_layout.addWidget(QLabel("1310 ref:"), 4, 0)
        self.reference_1310_spin = QDoubleSpinBox()
        self.reference_1310_spin.setRange(-100.0, 100.0)
        self.reference_1310_spin.setDecimals(2)
        self.reference_1310_spin.setSingleStep(0.01)
        self.reference_1310_spin.setValue(0.00)
        self.reference_1310_spin.setSuffix(" dBm")
        hardware_setup_layout.addWidget(self.reference_1310_spin, 4, 1)

        hardware_setup_layout.addWidget(QLabel("Operating band:"), 4, 2)
        self.hardware_operating_band = QComboBox()
        self.hardware_operating_band.addItems(["O band", "C band"])
        self.hardware_operating_band.setCurrentText("O band")
        hardware_setup_layout.addWidget(self.hardware_operating_band, 4, 3)
        hardware_setup_layout.addWidget(QLabel("1550 ref:"), 5, 0)
        self.reference_1550_spin = QDoubleSpinBox()
        self.reference_1550_spin.setRange(-100.0, 100.0)
        self.reference_1550_spin.setDecimals(2)
        self.reference_1550_spin.setSingleStep(0.01)
        self.reference_1550_spin.setValue(0.00)
        self.reference_1550_spin.setSuffix(" dBm")
        hardware_setup_layout.addWidget(self.reference_1550_spin, 5, 1)
        self.reference_1310_spin.valueChanged.connect(self.emit_reference_values)
        self.reference_1550_spin.valueChanged.connect(self.emit_reference_values)
        self.reference_1310_spin.valueChanged.connect(self._reference_values_changed_by_admin)
        self.reference_1550_spin.valueChanged.connect(self._reference_values_changed_by_admin)
        self.calculate_reference_button = QPushButton("Calculate Reference")
        self.calculate_reference_button.setToolTip(
            "Connect to the ILM/OP815 and calculate both reference offsets."
        )
        self.calculate_reference_button.clicked.connect(self.calculate_reference)
        hardware_setup_layout.addWidget(
            self.calculate_reference_button,
            5,
            2,
            1,
            2,
        )
        self.apply_manual_reference_button = QPushButton("Apply Manual Reference")
        self.apply_manual_reference_button.setToolTip(
            "Admin Mode only: authorize the displayed reference values for production runs."
        )
        self.apply_manual_reference_button.clicked.connect(self.apply_manual_reference)
        hardware_setup_layout.addWidget(
            self.apply_manual_reference_button,
            6,
            2,
            1,
            2,
        )
        hardware_setup_layout.addWidget(QLabel("Tested by:"), 6, 0)
        self.hardware_tested_by = QLineEdit()
        self.hardware_tested_by.setPlaceholderText("Initials")
        self.hardware_tested_by.setMaximumWidth(90)
        self.hardware_tested_by.setToolTip(
            "Enter the operator's initials. They are saved with the run and COC."
        )
        hardware_setup_layout.addWidget(self.hardware_tested_by, 6, 1)
        self.reference_status_label = QLabel("Reference status: Not referenced")
        self.reference_status_label.setWordWrap(True)
        hardware_setup_layout.addWidget(self.reference_status_label, 8, 0, 1, 4)
        hardware_setup_layout.addWidget(QLabel("Run number:"), 7, 0)
        self.hardware_run_number = QSpinBox()
        self.hardware_run_number.setRange(1, 9999)
        self.hardware_run_number.setValue(1)
        self.hardware_run_number.setToolTip(
            "Select which numbered test run belongs to this unit."
        )
        hardware_setup_layout.addWidget(self.hardware_run_number, 7, 1)
        self.load_run_button = QPushButton("Load Run")
        self.load_run_button.setToolTip(
            "Load the selected numbered run for the current unit."
        )
        self.load_run_button.clicked.connect(self.load_selected_unit_run)
        hardware_setup_layout.addWidget(self.load_run_button, 7, 2, 1, 2)
        self._scale_hardware_setup_fonts(hardware_setup_box, 1.2)
        self._refresh_reference_controls()
        self.update_channel_mode_controls(self.hardware_channel_mode.currentIndex())
        setup_row.addWidget(hardware_setup_box, 1)

        controls_box = QGroupBox("Hardware controls")
        controls_layout = QVBoxLayout(controls_box)
        controls_layout.setSpacing(8)

        run_controls_layout = QHBoxLayout()
        self.start_hardware_button = QPushButton("Start Run")
        self.start_hardware_button.setObjectName("hardware_primary_control")
        self.start_hardware_button.setToolTip(
            "Start a real OP815 and supported Santec OSX-100/OSX-150 hardware run."
        )
        self.start_hardware_button.clicked.connect(self.start_hardware)
        run_controls_layout.addWidget(self.start_hardware_button)
        self.stop_hardware_button = QPushButton("Stop run")
        self.stop_hardware_button.setObjectName("hardware_primary_control")
        self.stop_hardware_button.setToolTip("Stop the hardware run and keep completed readings.")
        self.stop_hardware_button.setEnabled(False)
        self.stop_hardware_button.clicked.connect(self.stop_hardware)
        run_controls_layout.addWidget(self.stop_hardware_button)
        controls_layout.addLayout(run_controls_layout)

        measurement_controls_layout = QHBoxLayout()
        self.continue_hardware_button = ShortcutButton("Read IL")
        self.continue_hardware_button.setToolTip("Read both wavelengths for the current channel.")
        self.continue_hardware_button.setObjectName("hardware_primary_control")
        self.continue_hardware_button.setEnabled(False)
        self.continue_hardware_button.clicked.connect(self.continue_hardware)
        measurement_controls_layout.addWidget(self.continue_hardware_button)
        self.write_hardware_button = ShortcutButton("Write IL")
        self.write_hardware_button.setToolTip("Accept and save the current IL reading.")
        self.write_hardware_button.setObjectName("hardware_primary_control")
        self.write_hardware_button.setEnabled(False)
        self.write_hardware_button.clicked.connect(self.write_hardware)
        measurement_controls_layout.addWidget(self.write_hardware_button)
        controls_layout.addLayout(measurement_controls_layout)

        self.change_hardware_channel_button = QPushButton("Change Channel...")
        self.change_hardware_channel_button.setToolTip(
            "Change the channel being measured without stopping the run."
        )
        self.change_hardware_channel_button.setEnabled(False)
        self.change_hardware_channel_button.clicked.connect(
            self.change_hardware_channel
        )

        self.retest_button = QPushButton("Retest selected")
        self.retest_button.setToolTip("Retest the selected completed channels.")
        self.retest_button.setEnabled(False)
        self.retest_button.clicked.connect(self.retest_selected)

        # Keep channel navigation actions together beneath the primary
        # measurement buttons.  Change Channel keeps the compact height of a
        # normal control button while matching the primary button width. Keep
        # Retest selected fixed as well so it does not stretch across the row.
        channel_controls_layout = QHBoxLayout()
        self.change_hardware_channel_button.setFixedWidth(125)
        self.retest_button.setFixedWidth(125)
        channel_controls_layout.addWidget(self.change_hardware_channel_button)
        channel_controls_layout.addWidget(self.retest_button)
        controls_layout.addLayout(channel_controls_layout)
        self.demo_channel_label = QLabel("No hardware run active")
        self.demo_channel_label.setWordWrap(True)
        # Retain the internal status target for existing run updates, but keep
        # it out of the hardware-controls layout so the controls stay compact.
        self.demo_channel_label.setVisible(False)
        self.write_coc_button = QPushButton("Write COC...")
        self.write_coc_button.setToolTip("Write the current run to a copied XLSX COC template.")
        self.write_coc_button.clicked.connect(self.write_coc)
        self.write_coc_button.setEnabled(False)
        self.copy_raw_data_button = QPushButton("Copy Raw Data...")
        self.copy_raw_data_button.setToolTip(
            "Copy completed channel readings as tab-separated text for Excel."
        )
        self.copy_raw_data_button.clicked.connect(self.copy_raw_data)
        self.copy_raw_data_button.setEnabled(False)
        for button in (self.write_coc_button, self.copy_raw_data_button):
            button.setFixedSize(125, 48)
        output_controls_layout = QHBoxLayout()
        output_controls_layout.addWidget(self.write_coc_button)
        output_controls_layout.addWidget(self.copy_raw_data_button)
        controls_layout.addLayout(output_controls_layout)
        for button in (
            self.start_hardware_button,
            self.continue_hardware_button,
            self.write_hardware_button,
            self.change_hardware_channel_button,
            self.stop_hardware_button,
            self.retest_button,
            self.write_coc_button,
            self.copy_raw_data_button,
        ):
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        for button in (
            self.start_hardware_button,
            self.stop_hardware_button,
            self.continue_hardware_button,
            self.write_hardware_button,
        ):
            button.setMinimumSize(125, 48)
        controls_box.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.update_shortcuts()
        setup_row.addWidget(controls_box)

        readings_box = QGroupBox("Current readings")
        self.current_readings_box = readings_box
        readings_box.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        readings_layout = QVBoxLayout(readings_box)
        readings_layout.setSpacing(5)
        self.current_channel_label = QLabel("Channel: -")
        self.current_channel_label.setObjectName("reading_channel")
        current_reading_header = QHBoxLayout()
        current_reading_header.addWidget(self.current_channel_label)
        current_reading_header.addStretch()
        self.hardware_live_indicator = QLabel("● LIVE")
        self.hardware_live_indicator.setObjectName("live_indicator")
        self.hardware_live_indicator.setToolTip(
            "The ILM is continuously updating the current channel reading."
        )
        self.hardware_live_indicator.setVisible(False)
        current_reading_header.addWidget(self.hardware_live_indicator)
        self.demo_1310_label = QLabel("1310 nm: -")
        self.demo_1310_label.setObjectName("reading")
        self.demo_1550_label = QLabel("1550 nm: -")
        self.demo_1550_label.setObjectName("reading")
        self.reading_status_label = QLabel("No reading yet")
        self.reading_status_label.setObjectName("reading_status")
        readings_layout.addLayout(current_reading_header)
        readings_layout.addWidget(self.demo_1310_label)
        readings_layout.addWidget(self.demo_1550_label)
        readings_layout.addWidget(self.reading_status_label)
        setup_row.addWidget(readings_box)
        root.addLayout(setup_row)

        content_splitter = QSplitter(Qt.Horizontal)
        self.content_splitter = content_splitter
        table_panel = QWidget()
        table_panel_layout = QVBoxLayout(table_panel)
        table_filter_layout = QHBoxLayout()
        table_filter_layout.addWidget(QLabel("Show readings:"))
        self.reading_filter = QComboBox()
        self.reading_filter.addItems(
            [
                "All channels",
                "Within warning limit",
                "Any wavelength over limit",
                "1310 nm over limit",
                "1550 nm over limit",
                "Both wavelengths over limit",
            ]
        )
        self.reading_filter.currentIndexChanged.connect(
            lambda _index: self.refresh_table()
        )
        table_filter_layout.addWidget(self.reading_filter)
        table_filter_layout.addWidget(QLabel("Compare with:"))
        self.comparison_run_combo = QComboBox()
        self.comparison_run_combo.setMinimumWidth(150)
        self.comparison_run_combo.addItem("No comparison", None)
        self.comparison_run_combo.currentIndexChanged.connect(
            self.load_comparison_run
        )
        self.comparison_run_combo.setEnabled(False)
        table_filter_layout.addWidget(self.comparison_run_combo)
        table_filter_layout.addStretch()
        table_panel_layout.addLayout(table_filter_layout)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Channel", "1310 nm IL (dB)", "1550 nm IL (dB)", "Status"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        table_panel_layout.addWidget(self.table)
        content_splitter.addWidget(table_panel)

        info_panel = QWidget()
        info_panel.setObjectName("info_panel")
        self.info_panel = info_panel
        info_layout = QVBoxLayout(info_panel)

        analysis_box = QGroupBox("Analysis")
        analysis_layout = QGridLayout(analysis_box)
        analysis_layout.setVerticalSpacing(7)
        analysis_layout.setColumnStretch(1, 1)
        # Keep the compatibility criteria widgets available to existing logic,
        # but keep implementation details out of the operator-facing panel.
        self.limit_spin = QDoubleSpinBox()
        self.limit_spin.setRange(-100.0, 100.0)
        self.limit_spin.setDecimals(4)
        self.limit_spin.setSingleStep(0.1)
        self.limit_spin.setValue(2.0)
        self.limit_spin.setSuffix(" dB")
        self.limit_spin.setReadOnly(True)
        self.limit_spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.limit_spin.setToolTip("Read-only compatibility display; edit criteria in Admin Config.")
        self.criteria_profile_label = QLabel("Connect hardware to load model criteria")
        self.criteria_profile_label.setWordWrap(True)
        self.select_over_limit_button = QPushButton("Select Failures")
        self.select_over_limit_button.clicked.connect(self.select_over_limit)
        self.limit_spin.hide()
        self.criteria_profile_label.hide()
        self.select_over_limit_button.hide()
        self.metric_labels = {}
        for row, (key, display) in enumerate(
            (
                ("total", "Total channels"),
                ("over_limit", "Failed channels"),
                ("over_1310", "1310 nm failed"),
                ("over_1550", "1550 nm failed"),
                ("over_both", "Both wavelengths failed"),
                ("too_good", "Too-good channels"),
                ("optimization", "Optimization warnings"),
            ),
            start=0,
        ):
            label = QLabel("-")
            label.setObjectName("metric")
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            self.metric_labels[key] = label
            analysis_layout.addWidget(QLabel(display + ":"), row, 0)
            analysis_layout.addWidget(label, row, 1, 1, 2)
        info_layout.addWidget(analysis_box)

        replacement_box = QGroupBox("Replacement analysis")
        replacement_layout = QVBoxLayout(replacement_box)
        self.replacement_summary_label = QLabel("Not run")
        self.replacement_summary_label.setWordWrap(True)
        self.replacement_analysis_button = QPushButton("Analyze Replacements")
        self.replacement_analysis_button.clicked.connect(self.show_replacement_analysis)
        self.replacement_analysis_button.setEnabled(False)
        self.completed_replacements_label = QLabel("No completed replacements recorded")
        self.completed_replacements_label.setWordWrap(True)
        self.record_replacements_button = QPushButton("Manage Port Replacements...")
        self.record_replacements_button.clicked.connect(
            self.show_completed_replacements
        )
        self.record_replacements_button.setEnabled(False)
        self.copy_replacement_notes_button = QPushButton("Copy Replacement Notes")
        self.copy_replacement_notes_button.setToolTip(
            "Copy the completed port swaps in a format ready to paste into Unit Editor notes."
        )
        self.copy_replacement_notes_button.clicked.connect(
            self.copy_replacement_notes
        )
        self.copy_replacement_notes_button.setEnabled(False)
        replacement_layout.addWidget(self.replacement_summary_label)
        replacement_layout.addWidget(self.replacement_analysis_button)
        replacement_layout.addWidget(self.completed_replacements_label)
        replacement_buttons = QHBoxLayout()
        replacement_buttons.addWidget(self.record_replacements_button)
        replacement_buttons.addWidget(self.copy_replacement_notes_button)
        replacement_layout.addLayout(replacement_buttons)
        info_layout.addWidget(replacement_box)

        metadata_box = QGroupBox("Run information")
        metadata_layout = QFormLayout(metadata_box)
        self.metadata_labels = {}
        for key in (
            "Part number",
            "Main board serial",
            "Switch serial",
            "Operating band",
            "Tested by",
            "Run number",
            "Source file",
        ):
            label = QLabel("-")
            label.setWordWrap(True)
            self.metadata_labels[key] = label
            metadata_layout.addRow(key + ":", label)
        self.view_history_button = QPushButton("View Reading History...")
        self.view_history_button.setToolTip(
            "View every accepted reading and retest saved for this run."
        )
        self.view_history_button.clicked.connect(self.show_reading_history)
        self.view_history_button.setEnabled(False)
        metadata_layout.addRow(self.view_history_button)
        info_layout.addWidget(metadata_box)
        info_layout.addStretch()
        self.info_scroll_area = QScrollArea()
        self.info_scroll_area.setObjectName("info_scroll_area")
        self.info_scroll_area.setWidgetResizable(True)
        self.info_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.info_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.info_scroll_area.viewport().setObjectName("info_scroll_viewport")
        self.info_scroll_area.setWidget(info_panel)
        content_splitter.addWidget(self.info_scroll_area)
        # Give the information column enough width for its controls and
        # recommendation text on the initial 1120px-wide window.
        content_splitter.setSizes([620, 450])
        root.addWidget(content_splitter, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.admin_mode_indicator = QLabel("")
        self.admin_mode_indicator.setStyleSheet("color: #e60013; font-weight: 800;")
        self.statusBar().addPermanentWidget(self.admin_mode_indicator)
        self.statusBar().showMessage("Ready. Open a saved CSV run to begin.")
        self._update_hardware_readiness_controls()

    def _scale_hardware_setup_fonts(self, setup_box, scale):
        """Scale only the fonts contained in the Hardware test setup box."""
        # Set descendants before the parent so inherited fonts are not doubled
        # a second time when the child font is read.
        widgets = [*setup_box.findChildren(QWidget), setup_box]
        for widget in widgets:
            font = widget.font()
            if font.pointSizeF() > 0:
                font.setPointSizeF(font.pointSizeF() * scale)
            elif font.pixelSize() > 0:
                font.setPixelSize(round(font.pixelSize() * scale))
            widget.setFont(font)

    def _theme_stylesheet(self, dark_mode):
        """Return the stylesheet for the selected application appearance."""
        return DARK_STYLESHEET if dark_mode else LIGHT_STYLESHEET

    def _connected_switch_model(self):
        """Return the detected supported switch model, with test fallback."""
        try:
            snapshot = self.hardware_connection_manager.snapshot(
                HardwareCapability.OPTICAL_SWITCH
            )
            device_info = snapshot.device_info
            model = normalize_switch_model(getattr(device_info, "model", ""))
            if model in self.limit_profiles:
                return model
        except (AttributeError, KeyError, TypeError):
            pass
        # Existing fake hardware adapters do not expose identity. Keep their
        # historical OSX-150-compatible behavior while real devices must match.
        return "OSX-150"

    def _reference_hardware_identity(self):
        """Return stable connected-meter identity used to invalidate references."""
        try:
            info = self.hardware_connection_manager.snapshot(
                HardwareCapability.MEASUREMENT
            ).device_info
            laser_info = None
            if self.hardware_connection_manager.has_separate_laser:
                laser_info = self.hardware_connection_manager.snapshot(
                    HardwareCapability.LASER_SOURCE
                ).device_info
            return (
                info.model,
                info.serial_number,
                info.resource_address,
                getattr(laser_info, "model", ""),
                getattr(laser_info, "serial_number", ""),
            )
        except (AttributeError, KeyError, TypeError):
            return ()

    def _reference_hardware_matches_snapshot(self):
        snapshot = self.reference_session.snapshot
        if snapshot is None:
            return False
        try:
            measurement = self.hardware_connection_manager.snapshot(
                HardwareCapability.MEASUREMENT
            )
            if not measurement.connected:
                return False
        except (AttributeError, KeyError, TypeError):
            return False
        identity = self._reference_hardware_identity()
        return bool(identity) and (
            not snapshot.meter_model or snapshot.meter_model == identity[0]
        ) and (
            not snapshot.meter_serial or snapshot.meter_serial == identity[1]
        )

    def _refresh_reference_controls(self):
        """Lock production reference fields except for an authenticated admin."""
        if not hasattr(self, "reference_1310_spin"):
            return
        editable = self.admin_session.is_active and not self.hardware_run_active
        for widget in (self.reference_1310_spin, self.reference_1550_spin):
            widget.setReadOnly(not editable)
            widget.setButtonSymbols(
                QAbstractSpinBox.UpDownArrows if editable else QAbstractSpinBox.NoButtons
            )
        self.apply_manual_reference_button.setEnabled(editable)
        snapshot = self.reference_session.snapshot
        if self.reference_session.is_valid and snapshot is not None:
            label = "Reference status: %s" % (
                "Calculated"
                if snapshot.method == ReferenceMethod.CALCULATED.value
                else "Admin manual"
            )
        else:
            label = "Reference status: %s" % self.reference_session.reason
        self.reference_status_label.setText(label)

    def _reference_values_changed_by_admin(self, *_values):
        if self._syncing_reference_widgets:
            return
        if self.admin_session.is_active and not self.hardware_run_active:
            self.reference_session.invalidate(
                "Manual values changed; press Apply Manual Reference in Admin Mode."
            )
            self._update_hardware_readiness_controls()

    def _reference_snapshot_context(self):
        identity = self._reference_hardware_identity()
        return {
            "meter_model": identity[0] if identity else "",
            "meter_serial": identity[1] if len(identity) > 1 else "",
            "meter_resource_address": identity[2] if len(identity) > 2 else "",
            "laser_model": identity[3] if len(identity) > 3 else "",
            "laser_serial": identity[4] if len(identity) > 4 else "",
            "operator_initials": self.hardware_tested_by.text().strip()
            if hasattr(self, "hardware_tested_by") else "",
        }

    def _apply_reference_snapshot_to_widgets(self, snapshot):
        self._syncing_reference_widgets = True
        try:
            self.reference_1310_spin.setValue(snapshot.reference_1310_dbm)
            self.reference_1550_spin.setValue(snapshot.reference_1550_dbm)
        finally:
            self._syncing_reference_widgets = False

    def apply_calculated_reference(self, reference_1310, reference_1550):
        """Authorize a newly completed measurement-based reference."""
        snapshot = new_reference_snapshot(
            reference_1310,
            reference_1550,
            method=ReferenceMethod.CALCULATED,
            **self._reference_snapshot_context(),
        )
        self.reference_session.apply(snapshot)
        self._last_applied_reference_snapshot = snapshot
        self._apply_reference_snapshot_to_widgets(snapshot)
        self._record_support(
            SupportEventCategory.MEASUREMENT,
            "reference.snapshot_applied",
            reference_snapshot_id=snapshot.snapshot_id,
            reference_method=snapshot.method,
            reference_state=self.reference_session.state,
            reference_established_at=snapshot.established_at,
            meter_model=snapshot.meter_model,
            meter_serial=snapshot.meter_serial,
            status="success",
        )
        self._update_hardware_readiness_controls()
        return snapshot

    def apply_diagnostic_calculated_reference(
        self, measured_powers, reference_1310, reference_1550
    ):
        """Apply a diagnostic baseline only after validating its raw power."""
        validation = validate_reference_measurements(measured_powers)
        if not validation.valid:
            message = format_dark_reference_error(measured_powers)
            self._record_support(
                SupportEventCategory.WORKFLOW,
                "reference.failed",
                level=SupportLogLevel.ERROR,
                validation_reason=validation.reason,
                invalid_wavelength=",".join(
                    str(value) for value in validation.invalid_wavelengths
                ),
                measured_power_dbm={
                    str(wavelength): measured_powers[wavelength]
                    for wavelength in validation.invalid_wavelengths
                },
                threshold_dbm=-40.0,
                error_message=message,
                status="error",
            )
            QMessageBox.critical(self, "Reference calculation failed", message)
            return False
        self.apply_calculated_reference(reference_1310, reference_1550)
        return True

    def apply_manual_reference(self):
        """Authorize manually entered references only from Admin Mode."""
        if not self.admin_session.is_active:
            return
        snapshot = new_reference_snapshot(
            self.reference_1310_spin.value(),
            self.reference_1550_spin.value(),
            method=ReferenceMethod.MANUAL_ADMIN,
            **self._reference_snapshot_context(),
        )
        self.reference_session.apply(snapshot)
        self._last_applied_reference_snapshot = snapshot
        self._record_support(
            SupportEventCategory.OPERATOR,
            "reference.manual_admin_applied",
            admin_mode=True,
            reference_snapshot_id=snapshot.snapshot_id,
            reference_method=snapshot.method,
            reference_state=self.reference_session.state,
            reference_established_at=snapshot.established_at,
            reference_1310_dbm=snapshot.reference_1310_dbm,
            reference_1550_dbm=snapshot.reference_1550_dbm,
            status="success",
        )
        self._update_hardware_readiness_controls()
        self.statusBar().showMessage("Admin manual reference applied.", 5000)

    def invalidate_reference(self, reason):
        """Invalidate production authorization without deleting historical audit data."""
        self.reference_session.invalidate(reason)
        self._record_support(
            SupportEventCategory.MEASUREMENT,
            "reference.invalidated",
            reference_state=self.reference_session.state,
            reference_invalidation_reason=str(reason),
            status="invalidated",
        )
        if hasattr(self, "reference_status_label"):
            self._refresh_reference_controls()

    def _profile_for_current_run(self):
        """Resolve the run snapshot or the current connected-model profile."""
        if self.run_data is not None and self.run_data.criteria_snapshot:
            try:
                return LimitProfile.from_mapping(self.run_data.criteria_snapshot)
            except (ValueError, TypeError, KeyError):
                pass
        if self.run_data is not None:
            # Unsnapshotted in-memory/legacy callers still use the historical
            # editable-limit semantics until the run is saved with criteria.
            return legacy_limit_profile(self.limit_spin.value())
        return self.active_limit_profile

    def _set_active_limit_profile(self, profile):
        self.active_limit_profile = profile
        display_warning = (
            "not applicable" if not profile.warning_enabled
            else "%.4f dB" % profile.warning_above_db
        )
        self.criteria_profile_label.setText(
            "%s r%s\nToo-good < %.4f dB; warning > %s; fail > %.4f dB"
            % (
                profile.profile_name,
                profile.revision,
                profile.too_good_below_db,
                display_warning,
                profile.fail_above_db,
            )
        )
        # Retain the old widget value as a compatibility view for old callers.
        compatibility_limit = (
            profile.warning_above_db
            if profile.warning_enabled and profile.warning_above_db is not None
            else profile.fail_above_db
        )
        self.limit_spin.blockSignals(True)
        self.limit_spin.setValue(compatibility_limit)
        self.limit_spin.blockSignals(False)

    def toggle_admin_mode(self):
        """Enter or leave the session-only administrator mode."""
        if self.admin_session.is_active:
            if self.reference_session.state == "invalidated" and self._last_applied_reference_snapshot:
                self._apply_reference_snapshot_to_widgets(self._last_applied_reference_snapshot)
                self.reference_session.apply(self._last_applied_reference_snapshot)
            self.admin_session.exit()
            self.admin_mode_action.setText("Admin Mode...")
            self.admin_mode_action.setChecked(False)
            self.admin_mode_indicator.setText("")
            self.admin_config_action.setEnabled(False)
            self._refresh_admin_branding()
            self.statusBar().showMessage("Admin mode disabled.")
            self._record_support(
                SupportEventCategory.OPERATOR,
                "admin.mode_exited",
                admin_mode=False,
                status="success",
            )
            self._refresh_reference_controls()
            return
        dialog = AdminPasswordDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        if not self.admin_session.authenticate(dialog.password):
            QMessageBox.warning(self, "Admin Mode", "The admin password was not accepted.")
            self._record_support(
                SupportEventCategory.OPERATOR,
                "admin.mode_activation_failed",
                admin_mode=False,
                status="failed",
            )
            return
        self.admin_mode_action.setText("Exit Admin Mode")
        self.admin_mode_action.setChecked(True)
        self.admin_mode_indicator.setText("ADMIN MODE")
        self.admin_config_action.setEnabled(True)
        self._refresh_admin_branding()
        self.statusBar().showMessage("ADMIN MODE active for this session.")
        self._record_support(
            SupportEventCategory.OPERATOR,
            "admin.mode_activated",
            admin_mode=True,
            status="success",
        )
        self._refresh_reference_controls()

    def _refresh_admin_branding(self):
        """Show the white-eyes Lulu variant only during Admin Mode."""
        filename = (
            ADMIN_BRANDING_ASSET
            if self.admin_session.is_active
            else NORMAL_BRANDING_ASSET
        )
        asset_path = bundled_asset_path(filename)
        if asset_path is None and self.admin_session.is_active:
            asset_path = bundled_asset_path(NORMAL_BRANDING_ASSET)
        if asset_path is None:
            if hasattr(self, "logo_label"):
                self.logo_label.hide()
            return

        icon = QIcon(str(asset_path))
        self.setWindowIcon(icon)
        application = QApplication.instance()
        if application is not None:
            application.setWindowIcon(icon)
        if hasattr(self, "logo_label"):
            logo = QPixmap(str(asset_path))
            self.logo_label.setPixmap(
                logo.scaled(132, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self.logo_label.show()

    def show_admin_config(self):
        """Open model criteria configuration after admin authentication."""
        if not self.admin_session.is_active:
            return
        self._record_support(
            SupportEventCategory.OPERATOR,
            "admin.config_opened",
            admin_mode=True,
            status="started",
        )
        previous_profiles = dict(self.limit_profiles)
        dialog = AdminConfigDialog(self.limit_profiles, self.limit_profile_repository, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            self.limit_profiles = self.limit_profile_repository.load_profiles()
            self.limit_profile_error = None
        except (OSError, ValueError, TypeError) as error:
            self.limit_profile_error = str(error)
            self._record_support(
                SupportEventCategory.OPERATOR,
                "admin.config_validation_failed",
                admin_mode=True,
                error_type=type(error).__name__,
                error_message=str(error),
                status="failed",
            )
            QMessageBox.warning(self, "Invalid admin config", str(error))
            return
        if self.run_data is None or not self.run_data.criteria_snapshot:
            self._set_active_limit_profile(self.limit_profiles.get("OSX-150"))
        self.refresh_analysis()
        self._record_support(
            SupportEventCategory.OPERATOR,
            "admin.config_saved",
            admin_mode=True,
            criteria_profile="OSX-100/OSX-150",
            previous_too_good_db=previous_profiles["OSX-150"].too_good_below_db,
            previous_warning_db=previous_profiles["OSX-150"].warning_above_db,
            previous_fail_db=previous_profiles["OSX-150"].fail_above_db,
            new_too_good_db=self.limit_profiles["OSX-150"].too_good_below_db,
            new_warning_db=self.limit_profiles["OSX-150"].warning_above_db,
            new_fail_db=self.limit_profiles["OSX-150"].fail_above_db,
            status="success",
        )
        self.statusBar().showMessage("Admin criteria configuration reloaded.")

    def toggle_dark_mode(self, enabled):
        """Apply and persist the operator's light/dark appearance choice."""
        self.dark_mode_enabled = bool(enabled)
        if hasattr(self, "dark_mode_action"):
            self.dark_mode_action.setChecked(self.dark_mode_enabled)
        self.settings.setValue("dark_mode", self.dark_mode_enabled)
        self.setStyleSheet(self._theme_stylesheet(self.dark_mode_enabled))
        self._refresh_reading_status_color()
        self.statusBar().showMessage(
            "Dark mode enabled." if self.dark_mode_enabled else "Light mode enabled."
        )

    def _apply_run_mode_controls(self):
        """Update button and shortcut labels for the current session mode."""
        if hasattr(self, "live_write_mode_action"):
            self.live_write_mode_action.setChecked(self.live_write_mode_enabled)
        if hasattr(self, "continue_hardware_button"):
            title = "Live Reading" if self.live_write_mode_enabled else "Read IL"
            self.continue_hardware_button.title_label.setText(title)
            self.continue_hardware_button.setAccessibleName(title)
            self.continue_hardware_button.setToolTip(
                "Start continuous IL updates for the current channel; "
                "updates begin automatically when the channel is routed. "
                "Use Write IL when the reading is ready."
                if self.live_write_mode_enabled
                else "Read both wavelengths for the current channel."
            )
        if hasattr(self, "write_shortcut") and self.write_shortcut is not None:
            self.write_shortcut.setEnabled(True)

    def toggle_live_write_mode(self, enabled):
        """Enable continuous IL updates until the operator writes a reading."""
        enabled = bool(enabled)
        if self.hardware_run_active:
            self.live_write_mode_action.setChecked(self.live_write_mode_enabled)
            self.statusBar().showMessage(
                "Live Write Mode cannot be changed during an active hardware run."
            )
            return
        if enabled:
            confirmation = QMessageBox.question(
                self,
                "Enable Live Write Mode?",
                "After each channel is routed, the ILM will automatically keep "
                "updating the displayed values. Nothing will be saved until "
                "you press Write IL.\n\n"
                "Live Write Mode will turn off when Light Workbench closes.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirmation != QMessageBox.Yes:
                self.live_write_mode_action.setChecked(False)
                return
        self.live_write_mode_enabled = enabled
        self._apply_run_mode_controls()
        self.statusBar().showMessage(
            "Live Write Mode enabled: live readings start automatically; write when ready."
            if enabled
            else "Live Write Mode disabled: Read IL and Write IL are separate steps."
        )

    def open_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open insertion-loss CSV",
            str(DEFAULT_RUN_ROOT),
            "CSV files (*.csv);;All files (*.*)",
        )
        if path:
            self.load_path(Path(path))

    def open_data_output_folder(self):
        """Open the directory containing saved measurement-run folders."""
        try:
            DEFAULT_RUN_ROOT.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.warning(
                self,
                "Data Output Folder",
                "Could not create or access the data output folder:\n%s" % error,
            )
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(DEFAULT_RUN_ROOT))):
            QMessageBox.warning(
                self,
                "Data Output Folder",
                "Could not open the data output folder in File Explorer.",
            )

    def _migrate_legacy_settings(self):
        """Preserve preferences saved by the former application branding."""
        legacy = QSettings("Santec", "ILMTester")
        for key in (
            "coc_template_path",
            "continue_key",
            "write_key",
        ):
            if self.settings.value(key, None) is None:
                value = legacy.value(key, None)
                if value is not None:
                    self.settings.setValue(key, value)

    def show_dependency_check(self):
        """Show non-destructive environment and hardware diagnostics."""
        dialog = DependencyCheckDialog(collect_dependency_report(), self)
        dialog.exec_()

    def choose_switch_visa_address(self):
        """Save an optional direct VISA address for the next switch connection."""
        address, accepted = QInputDialog.getText(
            self,
            "Switch VISA Address",
            "Optional manual VISA address for a Santec OSX-100/OSX-150. Leave blank to try "
            "the last working address and then automatic USB discovery. Changes "
            "apply to the next switch connection:",
            text=self.switch_visa_address,
        )
        if not accepted:
            return
        self.switch_visa_address = address.strip()
        self.settings.setValue("switch_visa_address", self.switch_visa_address)
        self.statusBar().showMessage(
            "Switch VISA address saved for the next connection."
            if self.switch_visa_address
            else "Switch VISA address cleared; automatic discovery will be used.",
            5000,
        )

    def show_about(self):
        """Show the current Light Workbench version and capabilities."""
        AboutDialog(self).exec_()

    def show_il_instructions(self):
        """Open the bundled IL operator guide in the system web browser."""
        guide_roots = [Path(__file__).resolve().parent]
        if getattr(sys, "_MEIPASS", None):
            guide_roots.insert(0, Path(sys._MEIPASS))
        guide_path = next(
            (
                root_path / "ILM_READING_GUIDE.html"
                for root_path in guide_roots
                if (root_path / "ILM_READING_GUIDE.html").is_file()
            ),
            None,
        )
        if guide_path is None:
            QMessageBox.warning(
                self,
                "IL Instructions",
                "The IL instruction guide could not be found.",
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide_path))):
            QMessageBox.warning(
                self,
                "IL Instructions",
                "Could not open the IL instruction guide in a web browser.",
            )

    def show_red_light_test(self):
        """Open the red-light test setup without connecting automatically."""
        if self.hardware_run_active:
            QMessageBox.warning(
                self,
                "Hardware run active",
                "Stop the current hardware run before opening a Red Light Test.",
            )
            return
        owner_token = object()
        workflow = self._new_workflow("red_light_test")
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "tool.red_light_opened",
            workflow_id=workflow.workflow_id if workflow else "",
            workflow_type="red_light_test",
            status="opened",
        )
        RedLightTestDialog(
            self,
            switch_factory=lambda: self._switch_proxy_for_workflow(
                owner_token,
                "Red Light Test",
                workflow,
                connect_if_needed=True,
            ),
        ).exec_()
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "tool.red_light_closed",
            workflow_id=workflow.workflow_id if workflow else "",
            workflow_type="red_light_test",
            status="closed",
        )

    def show_live_il_reading(self):
        """Open the meter-only live IL reader without touching run data."""
        if self.hardware_run_active:
            QMessageBox.warning(
                self,
                "Hardware run active",
                "Stop the current hardware run before starting a Live IL Reading.",
            )
            return
        owner_token = object()
        workflow = self._new_workflow("live_il")
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "tool.live_il_opened",
            workflow_id=workflow.workflow_id if workflow else "",
            workflow_type="live_il",
            status="opened",
        )
        dialog = LiveILReadingDialog(
            self,
            reference_1310=self.reference_1310_spin.value(),
            reference_1550=self.reference_1550_spin.value(),
            meter_factory=lambda: self._meter_proxy_for_workflow(
                owner_token,
                "Live IL Reading",
                workflow,
                connect_if_needed=True,
            ),
            support_logger=self.support_logger,
            workflow_id=workflow.workflow_id if workflow else "",
        )
        self.reference_values_changed.connect(dialog.set_reference_values)
        dialog.references_changed.connect(self.set_reference_values)
        dialog.exec_()
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "tool.live_il_closed",
            workflow_id=workflow.workflow_id if workflow else "",
            workflow_type="live_il",
            status="closed",
        )

    def show_switch_ip(self):
        """Read the connected switch LAN address through the manager."""
        if self._switch_ip_query_operation_id:
            return

        snapshot = self.hardware_connection_manager.snapshot(
            HardwareCapability.OPTICAL_SWITCH
        )
        if snapshot.owner:
            QMessageBox.information(
                self,
                "Optical switch busy",
                "The optical switch is currently in use by %s. Stop or close "
                "that operation before querying its IP address." % snapshot.owner,
            )
            return
        if not snapshot.connected:
            QMessageBox.information(
                self,
                "Optical switch not connected",
                "Connect the optical switch first, then choose Tools > Get IP...",
            )
            return

        operation_id = (
            self.support_logger.new_operation_id("switch-ip")
            if self.support_logger is not None
            else "switch-ip-%s" % uuid.uuid4().hex
        )
        self._switch_ip_query_operation_id = operation_id
        self.get_switch_ip_action.setEnabled(False)
        info = snapshot.device_info
        command = ":SYSTem:COMMunicate:LAN:ADDRess?"
        self._record_support(
            SupportEventCategory.CONNECTION,
            "switch.ip_query_started",
            operation_id=operation_id,
            model=info.model,
            device_serial=info.serial_number,
            resource_address=info.resource_address,
            command=command,
            status="started",
        )
        self.hardware_connection_manager.query_switch_ip(operation_id)

    def _switch_ip_query_finished(self, operation_id, address, error):
        """Present one manager-owned IP result on the GUI thread."""
        if operation_id != self._switch_ip_query_operation_id:
            return
        self._switch_ip_query_operation_id = ""
        self.get_switch_ip_action.setEnabled(True)
        snapshot = self.hardware_connection_manager.snapshot(
            HardwareCapability.OPTICAL_SWITCH
        )
        info = snapshot.device_info
        fields = {
            "operation_id": operation_id,
            "model": info.model,
            "device_serial": info.serial_number,
            "resource_address": info.resource_address,
            "command": ":SYSTem:COMMunicate:LAN:ADDRess?",
        }
        if error is not None:
            if isinstance(error, HardwareNotReadyError):
                message = (
                    "The optical switch is no longer connected. Reconnect it and "
                    "try again."
                )
            elif isinstance(error, HardwareBusyError):
                message = str(error)
            else:
                message = "Could not read the optical switch LAN IP address.\n\n%s" % error
            self._record_support(
                SupportEventCategory.CONNECTION,
                "switch.ip_query_failed",
                level=SupportLogLevel.WARNING,
                error_type=type(error).__name__,
                error_message=str(error),
                status="error",
                **fields,
            )
            QMessageBox.warning(self, "Get IP", message)
            return

        self._record_support(
            SupportEventCategory.CONNECTION,
            "switch.ip_query_completed",
            network_address=address,
            status="success",
            **fields,
        )
        dialog = SwitchIpAddressDialog(
            address,
            model=info.model,
            serial_number=info.serial_number,
            parent=self,
        )
        dialog.copied.connect(
            lambda: self._record_support(
                SupportEventCategory.CONNECTION,
                "switch.ip_query_copied_to_clipboard",
                network_address=address,
                status="success",
                **fields,
            )
        )
        dialog.exec_()

    def show_power_measurement_diagnostics(self):
        """Open the non-recording raw-power diagnostic tool."""
        if self.hardware_run_active:
            QMessageBox.warning(
                self,
                "Hardware run active",
                "Stop the current hardware run before starting Power "
                "Measurement Diagnostics.",
            )
            return
        owner_token = object()
        workflow = self._new_workflow("power_diagnostics")
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "tool.power_diagnostics_opened",
            workflow_id=workflow.workflow_id if workflow else "",
            workflow_type="power_diagnostics",
            status="opened",
        )
        dialog = PowerMeasurementDiagnosticsDialog(
            self,
            reference_1310=self.reference_1310_spin.value(),
            reference_1550=self.reference_1550_spin.value(),
            meter_factory=lambda: self._meter_proxy_for_workflow(
                owner_token,
                "Power Measurement Diagnostics",
                workflow,
                connect_if_needed=True,
            ),
            switch_factory=lambda: self._switch_proxy_for_workflow(
                owner_token,
                "Power Measurement Diagnostics",
                workflow,
                connect_if_needed=True,
            ),
            support_logger=self.support_logger,
            workflow_id=workflow.workflow_id if workflow else "",
        )
        dialog.references_changed.connect(self.set_reference_values)
        dialog.calculated_references_applied.connect(
            self.apply_diagnostic_calculated_reference
        )
        dialog.exec_()
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "tool.power_diagnostics_closed",
            workflow_id=workflow.workflow_id if workflow else "",
            workflow_type="power_diagnostics",
            status="closed",
        )

    def emit_reference_values(self):
        self.reference_values_changed.emit(
            self.reference_1310_spin.value(), self.reference_1550_spin.value()
        )

    def set_reference_values(self, reference_1310, reference_1550):
        """Apply shared reference values without causing a signal feedback loop."""
        self.reference_1310_spin.blockSignals(True)
        self.reference_1550_spin.blockSignals(True)
        try:
            self.reference_1310_spin.setValue(reference_1310)
            self.reference_1550_spin.setValue(reference_1550)
        finally:
            self.reference_1310_spin.blockSignals(False)
            self.reference_1550_spin.blockSignals(False)
        self.reference_values_changed.emit(
            self.reference_1310_spin.value(), self.reference_1550_spin.value()
        )

    def calculate_reference(self):
        """Calculate references directly, without opening the Live IL window."""
        if self.hardware_run_active:
            QMessageBox.warning(
                self,
                "Hardware run active",
                "Stop the current hardware run before calculating a reference.",
            )
            return
        if self.reference_thread is not None:
            return
        if not self.hardware_connection_manager.measurement_ready:
            QMessageBox.warning(
                self,
                "Measurement hardware not connected",
                "Connect the measurement hardware before calculating a reference.",
            )
            return
        self.reference_session.begin_calculation()
        self._refresh_reference_controls()
        owner_token = object()
        self.reference_workflow = self._new_workflow("reference_calculation")
        meter = self._meter_proxy_for_workflow(
            owner_token,
            "Reference calculation",
            self.reference_workflow,
            connect_if_needed=False,
        )
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "reference.started",
            workflow_id=(
                self.reference_workflow.workflow_id
                if self.reference_workflow
                else ""
            ),
            workflow_type="reference_calculation",
            status="started",
        )

        progress = QProgressDialog(
            "Calculating reference offset...",
            None,
            0,
            0,
            self,
        )
        progress.setWindowTitle("Calculate Reference")
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        self.reference_progress = progress
        self.calculate_reference_button.setEnabled(False)

        try:
            self.reference_controller.start(lambda meter=meter: meter)
        except Exception as error:
            self._record_support(
                SupportEventCategory.WORKFLOW,
                "reference.failed",
                level=SupportLogLevel.ERROR,
                workflow_id=(
                    self.reference_workflow.workflow_id
                    if self.reference_workflow
                    else ""
                ),
                error_type=type(error).__name__,
                error_message=str(error),
                status="error",
            )
            self._close_reference_progress()
            self.invalidate_reference("Reference calculation failed: %s" % error)
            self._update_hardware_readiness_controls()
            QMessageBox.critical(self, "Reference calculation", str(error))

    def _reference_meter_connected(self, _description):
        """Start the offset measurement after the meter connection succeeds."""
        self.reference_controller.calculate_reference()

    def _reference_calculation_ready(self, reference_1310, reference_1550):
        self._record_support(
            SupportEventCategory.MEASUREMENT,
            "reference.completed",
            workflow_id=(
                self.reference_workflow.workflow_id
                if self.reference_workflow
                else ""
            ),
            workflow_type="reference_calculation",
            reference_1310_dbm=reference_1310,
            reference_1550_dbm=reference_1550,
            both_wavelengths_complete=True,
            status="success",
        )
        self.apply_calculated_reference(reference_1310, reference_1550)
        self.statusBar().showMessage(
            "Reference calculated. Measurement hardware remains connected.",
            5000,
        )
        self._finish_reference_calculation()

    def _reference_calculation_failed(self, message):
        if self.reference_worker is None:
            return
        validation_reason = (
            "dark_reference"
            if "below the expected signal level" in str(message)
            else ""
        )
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "reference.failed",
            level=SupportLogLevel.ERROR,
            workflow_id=(
                self.reference_workflow.workflow_id
                if self.reference_workflow
                else ""
            ),
            error_message=message,
            validation_reason=validation_reason,
            **({"threshold_dbm": -40.0} if validation_reason else {}),
            status="error",
        )
        self._finish_reference_calculation()
        self.invalidate_reference("Reference calculation failed: %s" % message)
        QMessageBox.critical(self, "Reference calculation failed", message)

    def _finish_reference_calculation(self):
        """Stop the temporary meter worker and close its progress popup."""
        self.reference_controller.stop_and_wait()
        self._close_reference_progress()
        self._update_hardware_readiness_controls()

    def _close_reference_progress(self):
        if self.reference_progress is not None:
            self.reference_progress.close()
            self.reference_progress.deleteLater()
            self.reference_progress = None

    def update_channel_mode_controls(self, mode_index):
        """Show only the channel selector used by the selected run mode."""
        single_channel_mode = mode_index == 1
        channel_ranges_mode = mode_index == 2
        full_pass_mode = mode_index == 0
        self.hardware_channel_label.setVisible(single_channel_mode)
        self.hardware_single_channel.setVisible(single_channel_mode)
        self.hardware_channel_ranges_label.setVisible(channel_ranges_mode)
        self.hardware_channel_ranges.setVisible(channel_ranges_mode)
        self.manual_channel_order_checkbox.setVisible(full_pass_mode)
        self.channel_mode_context.setVisible(full_pass_mode or single_channel_mode)

    def open_part_lookup_folder(self):
        """Open the fixed network folder used for part-number lookup."""
        lookup_root = Path(DEFAULT_PART_LOOKUP_ROOT)
        if not lookup_root.is_dir():
            QMessageBox.warning(
                self,
                "Part Number Lookup Folder",
                "The designated part-number lookup folder is not available:\n%s"
                % lookup_root,
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(lookup_root))):
            QMessageBox.warning(
                self,
                "Part Number Lookup Folder",
                "Could not open the designated folder in File Explorer:\n%s"
                % lookup_root,
            )
            return
        self.statusBar().showMessage(
            "Opened part-number lookup folder: %s" % lookup_root
        )

    def choose_coc_template(self):
        current = self.coc_template_path(45)
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select XLSX COC template",
            str(current.parent),
            "Excel workbooks (*.xlsx)",
        )
        if selected:
            try:
                capacity = self.coc_exporter.inspect_template_capacity(selected)
            except (OSError, RuntimeError, ValueError) as error:
                QMessageBox.warning(self, "Invalid COC template", str(error))
                return
            self.settings.setValue(
                "coc_template_%d_path" % capacity,
                selected,
            )
            self.statusBar().showMessage(
                "%d-channel COC template selected: %s" % (capacity, selected)
            )

    def lookup_part_number(self):
        serial = self.hardware_main_board_serial.text().strip()
        lookup_root = str(DEFAULT_PART_LOOKUP_ROOT)
        self._active_part_lookup_request = None
        self._record_support(
            SupportEventCategory.OPERATOR,
            "metadata.part_lookup_started",
            unit_serial=self.coc_exporter.normalise_serial(serial),
            lookup_mode="manual",
            status="started",
        )
        try:
            part_number = self.coc_exporter.find_part_number(serial, lookup_root)
        except (OSError, LookupError, ValueError) as error:
            self._record_support(
                SupportEventCategory.OPERATOR,
                "metadata.part_lookup_failed",
                level=SupportLogLevel.WARNING,
                unit_serial=self.coc_exporter.normalise_serial(serial),
                lookup_mode="manual",
                reason=classify_part_lookup_error(error),
                error_type=type(error).__name__,
                error_message=str(error),
                status="error",
            )
            QMessageBox.warning(self, "Part number lookup", str(error))
            return

        self._apply_part_number_result(part_number, update_run_data=True)
        normalized_serial = self.coc_exporter.normalise_serial(serial)
        self._record_support(
            SupportEventCategory.OPERATOR,
            "metadata.part_lookup_succeeded",
            unit_serial=normalized_serial,
            part_number=part_number,
            lookup_mode="manual",
            status="success",
        )
        self.statusBar().showMessage(
            "Part number found for Main Board serial %s."
            % normalized_serial
        )

    def _apply_part_number_result(self, part_number, *, update_run_data):
        """Apply a completed lookup on the UI thread."""
        self.hardware_part_number.setCurrentText(part_number)
        self.metadata_labels["Part number"].setText(part_number)
        if update_run_data and self.run_data is not None:
            self.run_data.metadata["Part number"] = part_number

    def coc_template_path(self, front_panel_channel_count=45):
        """Resolve the validated template for the requested report capacity."""
        capacity = 45 if int(front_panel_channel_count) <= 45 else 48
        configured = self.settings.value("coc_template_%d_path" % capacity, "")
        if configured and Path(configured).is_file():
            try:
                if self.coc_exporter.inspect_template_capacity(configured) == capacity:
                    return Path(configured)
            except (OSError, RuntimeError, ValueError):
                pass

        # Migrate the former single-template preference only when its actual
        # workbook capacity matches the report being prepared.
        legacy_configured = self.settings.value("coc_template_path", "")
        if legacy_configured and Path(legacy_configured).is_file():
            try:
                legacy_capacity = self.coc_exporter.inspect_template_capacity(
                    legacy_configured
                )
            except (OSError, RuntimeError, ValueError):
                legacy_capacity = None
            if legacy_capacity == capacity:
                self.settings.setValue(
                    "coc_template_%d_path" % capacity,
                    legacy_configured,
                )
                return Path(legacy_configured)

        roots = []
        if getattr(sys, "frozen", False):
            roots.extend(
                [
                    Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)),
                    Path(sys.executable).parent,
                ]
            )
        else:
            roots.append(Path(__file__).resolve().parent)
        filename = (
            COC_TEMPLATE_45_FILENAME
            if capacity == 45
            else COC_TEMPLATE_48_FILENAME
        )
        for root in roots:
            candidate = root / "Templates" / filename
            if candidate.is_file():
                return candidate
        return roots[0] / "Templates" / filename

    def _unit_metadata(self, metadata=None):
        """Return only identity fields that belong to the physical unit."""
        metadata = metadata or {}
        return {
            key: str(metadata.get(key) or "").strip()
            for key in ("Main board serial", "Part number")
        }

    def _load_unit_state(self, unit_directory):
        """Load shared replacements and spares for the active unit."""
        self.unit_directory = unit_directory
        if unit_directory is None:
            self.unit_record = {}
            self.replacement_history = []
            self.completed_replacements = []
            self.designated_spares = []
            self.refresh_comparison_runs()
            return
        try:
            self.unit_record = self.unit_repository.load_record(unit_directory)
        except (OSError, ValueError, TypeError, KeyError):
            self.unit_record = {}
        self.replacement_history = list(
            self.unit_record.get("replacement_history", [])
        )
        self.completed_replacements = effective_replacements(self.replacement_history)
        self.designated_spares = list(
            self.unit_record.get("designated_spares", [])
        )
        if self.run_data is not None:
            self.run_data.completed_replacements = list(self.completed_replacements)
        self.refresh_comparison_runs()

    def refresh_comparison_runs(self):
        """Refresh the optional previous-run selector for the active unit."""
        if not hasattr(self, "comparison_run_combo"):
            return

        selected_path = self.comparison_run_combo.currentData()
        self.comparison_run_combo.blockSignals(True)
        self.comparison_run_combo.clear()
        self.comparison_run_combo.addItem("No comparison", None)

        current_run_number = None
        if self.run_data is not None:
            try:
                current_run_number = int(self.run_data.metadata.get("Run number"))
            except (TypeError, ValueError):
                current_run_number = None

        run_entries = [
            item
            for item in self.unit_record.get("runs", [])
            if isinstance(item, dict)
        ]
        if self.unit_directory is not None:
            def run_sort_key(item):
                try:
                    return int(item.get("run_number", 0))
                except (TypeError, ValueError):
                    return 0

            for run_entry in sorted(run_entries, key=run_sort_key):
                try:
                    run_number = int(run_entry.get("run_number"))
                except (TypeError, ValueError):
                    continue
                if current_run_number == run_number:
                    continue
                directory_name = str(run_entry.get("directory") or "").strip()
                csv_name = str(run_entry.get("csv_file") or "").strip()
                if not directory_name or not csv_name:
                    continue
                csv_path = Path(self.unit_directory) / directory_name / csv_name
                if not csv_path.is_file():
                    continue
                self.comparison_run_combo.addItem(
                    "Run %d" % run_number,
                    str(csv_path),
                )

        self.comparison_run_combo.setEnabled(
            self.comparison_run_combo.count() > 1
        )
        if selected_path:
            selected_index = self.comparison_run_combo.findData(selected_path)
            if selected_index >= 0:
                self.comparison_run_combo.setCurrentIndex(selected_index)
            else:
                self.comparison_run_data = None
                self.comparison_run_number = None
        elif self.comparison_run_data is not None:
            self.comparison_run_data = None
            self.comparison_run_number = None
        self.comparison_run_combo.blockSignals(False)
        self.refresh_table()

    def load_comparison_run(self, _index):
        """Load or clear the read-only comparison run selected by the user."""
        selected_path = self.comparison_run_combo.currentData()
        if not selected_path:
            self.comparison_run_data = None
            self.comparison_run_number = None
            self.refresh_table()
            return

        try:
            comparison_data = self.run_repository.load_csv(Path(selected_path))
        except (OSError, ValueError) as error:
            self.comparison_run_combo.blockSignals(True)
            self.comparison_run_combo.setCurrentIndex(0)
            self.comparison_run_combo.blockSignals(False)
            self.comparison_run_data = None
            self.comparison_run_number = None
            QMessageBox.warning(
                self,
                "Could not load comparison run",
                str(error),
            )
            self.refresh_table()
            return

        self.comparison_run_data = comparison_data
        try:
            self.comparison_run_number = int(
                comparison_data.metadata.get(
                    "Run number",
                    self.comparison_run_combo.currentText().split()[-1],
                )
            )
        except (TypeError, ValueError):
            self.comparison_run_number = None
        self.refresh_table()
        self.statusBar().showMessage(
            "Comparing the current run with %s."
            % self.comparison_run_combo.currentText()
        )

    def persist_unit_record(self):
        """Persist device-level replacements, spares, and the active run index."""
        if self.unit_directory is None:
            return
        metadata = (
            self.run_data.metadata
            if self.run_data is not None
            else self._current_hardware_identity()
        )
        run_number = None
        run_directory = None
        switch_serial = metadata.get("Switch serial", "")
        if self.run_data is not None:
            try:
                run_number = int(self.run_data.metadata.get("Run number", 1))
            except (TypeError, ValueError):
                run_number = None
            switch_serial = self.run_data.metadata.get("Switch serial", switch_serial)
            if self.run_recorder is not None:
                run_directory = self.run_recorder.directory
            elif self.run_data.source_path:
                source_path = Path(self.run_data.source_path)
                if (
                    source_path.parent.is_dir()
                    and source_path.parent.parent == Path(self.unit_directory)
                    and source_path.parent.name.startswith("Run-")
                ):
                    run_directory = source_path.parent
        self.unit_repository.save_record(
            self.unit_directory,
            self._unit_metadata(metadata),
            self.completed_replacements,
            self.designated_spares,
            run_number,
            run_directory,
            switch_serial=switch_serial,
            replacement_history=self.replacement_history,
        )
        self.unit_record = self.unit_repository.load_record(self.unit_directory)

    def ensure_unit_state_for_current_fields(self):
        """Create or load the shared unit context when upgrading a legacy run."""
        if self.unit_directory is not None:
            return
        candidate = self.unit_repository.unit_directory_for_metadata(
            DEFAULT_RUN_ROOT,
            self._current_hardware_identity(),
        )
        if (candidate / "unit.json").is_file():
            self._load_unit_state(candidate)
        else:
            self.unit_directory = candidate
            self.unit_record = {}

    def load_selected_unit_run(self):
        """Load a numbered run for the unit identified in setup fields."""
        if self.hardware_run_active:
            self.statusBar().showMessage("Stop the active hardware run first.")
            return
        metadata = self._current_hardware_identity()
        unit_directory = self.unit_repository.unit_directory_for_metadata(
            DEFAULT_RUN_ROOT,
            metadata,
        )
        run_number = self.hardware_run_number.value()
        csv_path = self.run_repository.find_run_csv_for_number(
            unit_directory,
            run_number,
            metadata.get("Switch serial", ""),
        )
        if csv_path is None:
            available = self.unit_repository.available_run_numbers(unit_directory)
            available_text = ", ".join(str(number) for number in available)
            QMessageBox.information(
                self,
                "Run not found",
                "No Run %d was found for this unit.\n\nAvailable runs: %s"
                % (run_number, available_text or "none"),
            )
            return
        self.load_path(csv_path)

    def load_path(self, path: Path):
        try:
            run_data = self.run_repository.load_csv(path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Could not open run", str(error))
            return

        self.run_data = run_data
        self.run_recorder = None
        self._load_unit_state(self.unit_repository.infer_unit_directory(path))
        self.replacement_analysis = None
        self.switch_test_timer = None
        self.clear_current_reading()
        self.file_label.setText(str(path))
        self.metadata_labels["Source file"].setText(path.name)
        self.hardware_part_number.setCurrentText(
            run_data.metadata.get("Part number", "")
        )
        self.hardware_main_board_serial.setText(
            run_data.metadata.get("Main board serial", "")
        )
        self.hardware_switch_serial.setText(
            run_data.metadata.get(
                "Switch serial",
                run_data.metadata.get("Switch serial (last 5 digits)", ""),
            )
        )
        operating_band = run_data.metadata.get("Operating band", "O band")
        if self.hardware_operating_band.findText(operating_band) < 0:
            operating_band = "O band"
        self.hardware_operating_band.setCurrentText(operating_band)
        self.hardware_tested_by.setText(run_data.metadata.get("Tested by", ""))
        try:
            self.hardware_run_number.setValue(
                max(1, int(run_data.metadata.get("Run number", 1)))
            )
        except (TypeError, ValueError):
            self.hardware_run_number.setValue(1)
        self.metadata_labels["Part number"].setText(
            run_data.metadata.get("Part number", "Not recorded")
        )
        for key in ("Main board serial", "Switch serial", "Operating band", "Tested by"):
            value = run_data.metadata.get(key)
            if value is None and key == "Switch serial":
                value = run_data.metadata.get("Switch serial (last 5 digits)")
            self.metadata_labels[key].setText(value or "Not recorded")
        self.metadata_labels["Run number"].setText(
            str(self.hardware_run_number.value())
        )
        loaded_run_id = ""
        json_path = self.run_repository.find_json_path(path)
        if json_path.is_file():
            try:
                payload = self.run_repository.load_json(json_path)
                loaded_run_id = str(payload.get("run_id") or "")
                try:
                    run_data.measurement_attempts = normalise_attempts(
                        payload.get(
                            "measurement_attempts",
                            payload.get("attempts", []),
                        ),
                        run_data.measurements,
                        run_id=str(Path(path).resolve()),
                    )
                except (ValueError, TypeError, KeyError):
                    # An older diagnostic-only ``attempts`` list may not have
                    # complete reading values. Keep the run loadable and
                    # synthesize history from the accepted table below.
                    run_data.measurement_attempts = []
                completed_replacements = payload.get("completed_replacements", [])
                saved_history = payload.get("replacement_history")
                if isinstance(saved_history, list):
                    saved_history = normalise_replacement_history(saved_history)
                else:
                    saved_history = legacy_replacement_history(
                        completed_replacements
                        if isinstance(completed_replacements, list)
                        else []
                    )
                legacy_replacements = effective_replacements(saved_history)
                if self.unit_directory is None and legacy_replacements:
                    self.replacement_history = saved_history
                    self.completed_replacements = legacy_replacements
                    run_data.completed_replacements = list(legacy_replacements)
                switch_test_sessions = payload.get("switch_test_sessions", [])
                run_data.switch_test_sessions = (
                    switch_test_sessions
                    if isinstance(switch_test_sessions, list)
                    else []
                )
                if self.unit_directory is None:
                    self.completed_replacements = run_data.completed_replacements
                physical_ports = {
                    int(item["channel"]): item.get("physical_port")
                    for item in payload.get("measurements", [])
                    if item.get("physical_port") is not None
                }
                references = {
                    int(item["channel"]): item.get("reference")
                    for item in payload.get("measurements", [])
                    if isinstance(item, dict) and item.get("reference")
                }
                if physical_ports or references:
                    run_data.measurements = [
                        MeasurementRecord(
                            record.channel,
                            record.loss_1310,
                            record.loss_1550,
                            physical_ports.get(record.channel),
                            references.get(record.channel, record.reference_snapshot),
                        )
                        for record in run_data.measurements
                    ]
                criteria = payload.get("criteria")
                if isinstance(criteria, dict):
                    try:
                        profile = LimitProfile.from_mapping(criteria)
                    except (ValueError, TypeError, KeyError):
                        profile = legacy_limit_profile(
                            float(payload.get("warning_limit_db", 2.0))
                        )
                else:
                    # Runs created before model-specific criteria retain their
                    # original single warning limit and are marked legacy.
                    profile = legacy_limit_profile(
                        float(payload.get("warning_limit_db", 2.0))
                    )
                run_data.criteria_snapshot = profile.as_dict()
                run_data.warning_limit = profile.warning_above_db
                self._set_active_limit_profile(profile)
            except (OSError, ValueError, TypeError, KeyError):
                self.statusBar().showMessage(
                    "Loaded CSV; the companion run.json could not be read."
                )
        if not run_data.measurement_attempts:
            run_data.measurement_attempts = normalise_attempts(
                [],
                run_data.measurements,
                run_id=str(Path(path).resolve()),
            )
        run_data.attempts = [
            attempt.as_dict() for attempt in run_data.measurement_attempts
        ]
        historical_reference = next(
            (
                record.reference_snapshot
                for record in reversed(run_data.measurements)
                if isinstance(record.reference_snapshot, dict)
            ),
            None,
        )
        if historical_reference:
            try:
                self._syncing_reference_widgets = True
                self.reference_1310_spin.setValue(
                    float(historical_reference["reference_1310_dbm"])
                )
                self.reference_1550_spin.setValue(
                    float(historical_reference["reference_1550_dbm"])
                )
            except (KeyError, TypeError, ValueError):
                pass
            finally:
                self._syncing_reference_widgets = False
        self.invalidate_reference(
            "Loaded references are historical only; calculate a new reference before acquisition."
        )
        self.run_recorder = self.run_repository.recorder_from_existing(
            path,
            metadata=run_data.metadata,
            limit=self.limit_spin.value(),
            criteria_snapshot=run_data.criteria_snapshot,
            measurement_attempts=run_data.measurement_attempts,
            run_id=loaded_run_id or None,
            replacement_analysis=run_data.replacement_analysis,
            switch_test_sessions=run_data.switch_test_sessions,
            completed_replacements=run_data.completed_replacements,
        )
        run_data.source_path = self.run_recorder.csv_path
        self.switch_test_timer = SwitchTestTimer(
            run_data.metadata,
            run_data.switch_test_sessions,
        )
        self.refresh_analysis()
        self.refresh_replacement_summary()
        self.statusBar().showMessage("Loaded %d measurements." % len(run_data.measurements))

    def start_demo(self):
        channel_count = self.demo_channel_count.value()
        readings = []
        reference_1310 = self.reference_1310_spin.value()
        reference_1550 = self.reference_1550_spin.value()
        for channel in range(1, channel_count + 1):
            loss_1310 = 1.25 + (channel % 5) * 0.08
            loss_1550 = 1.05 + (channel % 4) * 0.07
            if channel % 7 == 0:
                loss_1310 += 0.85
            if channel % 9 == 0:
                loss_1550 += 1.1
            readings.append({
                1310: reference_1310 - loss_1310,
                1550: reference_1550 - loss_1550,
            })

        self.demo_meter = SimulatedPowerMeter(readings)
        self.demo_meter.connect()
        self.demo_channel = 1
        self.demo_measurement = None
        self.clear_current_reading(self.demo_channel)
        self.run_data = RunData(
            Path("Simulation"),
            [],
            {
                "Operating band": "O band",
                "Tested by": self.hardware_tested_by.text().strip(),
                "Mode": "Simulation",
                "Run number": "1",
                "1310 reference dBm": "%.2f" % reference_1310,
                "1550 reference dBm": "%.2f" % reference_1550,
            },
        )
        self.run_recorder = self.run_repository.new_recorder(
            metadata={
                "Operating band": "O band",
                "Tested by": self.hardware_tested_by.text().strip(),
                "Mode": "Simulation",
                "Run number": "1",
                "1310 reference dBm": "%.2f" % reference_1310,
                "1550 reference dBm": "%.2f" % reference_1550,
            },
            limit=self.limit_spin.value(),
        )
        self.replacement_analysis = None
        self.run_data.replacement_analysis = None
        self.replacement_history = []
        self.completed_replacements = []
        self.designated_spares = []
        self.unit_directory = None
        self.unit_record = {}
        self.refresh_comparison_runs()
        self.run_data.completed_replacements = []
        self.switch_test_timer = None
        self.run_data.source_path = self.run_recorder.csv_path
        self.file_label.setText(str(self.run_recorder.csv_path))
        self.metadata_labels["Main board serial"].setText("SIMULATED")
        self.metadata_labels["Switch serial"].setText("SIMULATED")
        self.metadata_labels["Operating band"].setText("O band")
        self.metadata_labels["Tested by"].setText(
            self.hardware_tested_by.text().strip() or "Not recorded"
        )
        self.hardware_run_number.setValue(1)
        self.metadata_labels["Run number"].setText("1")
        self.metadata_labels["Source file"].setText("Simulation")
        self.demo_channel_label.setText(
            "Channel 1 of %d - ready to measure" % channel_count
        )
        self.measure_demo_button.setEnabled(True)
        self.accept_demo_button.setEnabled(False)
        self.retest_button.setEnabled(False)
        self.refresh_analysis()
        self.refresh_replacement_summary()
        self.statusBar().showMessage("Simulation started. No hardware is connected.")

    def measure_demo(self):
        if self.demo_meter is None or self.demo_channel == 0:
            return
        measurements = self.demo_meter.measure_both_wavelengths()
        self.demo_measurement = calculate_insertion_loss(
            {
                1310: self.reference_1310_spin.value(),
                1550: self.reference_1550_spin.value(),
            },
            measurements,
        )
        self.set_current_reading_channel(self.demo_channel)
        self.current_loss_1310 = self.demo_measurement[1310]
        self.current_loss_1550 = self.demo_measurement[1550]
        self.refresh_current_reading()
        self.accept_demo_button.setEnabled(True)
        self.demo_channel_label.setText("Channel %d - review reading" % self.demo_channel)

    def accept_demo(self):
        if self.run_data is None or self.demo_measurement is None:
            return
        record = MeasurementRecord(
            self.demo_channel,
            self.demo_measurement[1310],
            self.demo_measurement[1550],
        )
        self._accept_measurement_record(record)
        if self.demo_channel >= self.demo_channel_count.value():
            self.demo_channel_label.setText("Demo run complete")
            self.measure_demo_button.setEnabled(False)
            self.retest_button.setEnabled(True)
        else:
            self.demo_channel += 1
            self.demo_channel_label.setText(
                "Channel %d of %d - ready to measure"
                % (self.demo_channel, self.demo_channel_count.value())
            )
        self.demo_measurement = None
        self.accept_demo_button.setEnabled(False)
        self.refresh_analysis()
        self.scroll_to_channel(record.channel)

    def retest_selected(self):
        if self.hardware_run_active or self.run_data is None:
            return
        selected_rows = sorted(
            {index.row() for index in self.table.selectionModel().selectedRows()}
        )
        channels = [
            self.displayed_records[row].channel
            for row in selected_rows
            if row < len(self.displayed_records)
        ]
        if not channels:
            QMessageBox.information(
                self,
                "Select channels",
                "Select one or more completed channels in the table first.",
            )
            return

        if (
            self.demo_meter is not None
            and self.run_data.metadata.get("Mode") == "Simulation"
        ):
            self.retest_demo_channels(channels)
            return

        self.start_hardware(channels=channels, retest=True)

    def retest_demo_channels(self, channels):
        for channel in channels:
            self.demo_channel = channel
            self.measure_demo()
            if self.demo_measurement is None:
                return
            record = MeasurementRecord(
                channel,
                self.demo_measurement[1310],
                self.demo_measurement[1550],
            )
            self._accept_measurement_record(record, write_context="retest")
            self.demo_measurement = None
        self.refresh_analysis()
        self.retest_button.setEnabled(True)
        self.statusBar().showMessage("Selected simulation channels retested and saved.")

    def choose_hardware_run_mode(self):
        """Ask whether Start Run should continue or replace the loaded run."""
        try:
            loaded_run_number = int(self.run_data.metadata.get("Run number", 1))
        except (AttributeError, TypeError, ValueError):
            loaded_run_number = 1
        selected_run_number = self.hardware_run_number.value()
        if selected_run_number != loaded_run_number:
            choice = QMessageBox.question(
                self,
                "Start another run",
                "Run %d is loaded, but Run %d is selected.\n\n"
                "Start a new Run %d for this unit?"
                % (loaded_run_number, selected_run_number, selected_run_number),
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            return "new" if choice == QMessageBox.Yes else None
        choice = QMessageBox(self)
        choice.setWindowTitle("Choose run mode")
        choice.setText("A run is already loaded or paused.")
        choice.setInformativeText(
            "Continue editing that run, or start a separate new run?"
        )
        continue_button = choice.addButton(
            "Continue/Edit Current Run",
            QMessageBox.AcceptRole,
        )
        new_button = choice.addButton("Start New Run", QMessageBox.ActionRole)
        cancel_button = choice.addButton(QMessageBox.Cancel)
        choice.setDefaultButton(continue_button)
        choice.exec_()
        clicked_button = choice.clickedButton()
        if clicked_button == continue_button:
            return "continue"
        if clicked_button == new_button:
            return "new"
        if clicked_button == cancel_button:
            return None
        return None

    def _current_hardware_identity(self):
        """Return the editable identity fields used to name a hardware run."""
        return {
            "Part number": self.hardware_part_number.currentText().strip(),
            "Main board serial": self.hardware_main_board_serial.text().strip(),
            "Switch serial": self.hardware_switch_serial.text().strip(),
            "Operating band": self.hardware_operating_band.currentText().strip(),
            "Tested by": self.hardware_tested_by.text().strip(),
        }

    def _restore_hardware_identity(self, metadata):
        """Restore loaded identity values after declining an update."""
        self.hardware_part_number.setCurrentText(metadata.get("Part number", ""))
        self.hardware_main_board_serial.setText(
            metadata.get("Main board serial", "")
        )
        self.hardware_switch_serial.setText(
            metadata.get(
                "Switch serial",
                metadata.get("Switch serial (last 5 digits)", ""),
            )
        )
        operating_band = metadata.get("Operating band", "O band")
        if self.hardware_operating_band.findText(operating_band) < 0:
            operating_band = "O band"
        self.hardware_operating_band.setCurrentText(operating_band)
        self.hardware_tested_by.setText(metadata.get("Tested by", ""))

    def confirm_existing_run_identity(self):
        """Offer to update a loaded run's identity before continuing it."""
        if self.run_data is None:
            return True

        saved_identity = {
            key: self.run_data.metadata.get(key, "")
            for key in (
                "Part number",
                "Main board serial",
                "Switch serial",
                "Operating band",
                "Tested by",
            )
        }
        current_identity = self._current_hardware_identity()
        changed = [
            key
            for key in saved_identity
            if str(saved_identity[key] or "").strip()
            != str(current_identity[key] or "").strip()
        ]
        if not changed:
            return True

        changed_text = ", ".join(changed)
        choice = QMessageBox(self)
        choice.setWindowTitle("Update loaded run information?")
        choice.setText("The loaded run information has changed.")
        choice.setInformativeText(
            "Changed fields: %s\n\nUpdate the saved run before continuing?"
            % changed_text
        )
        update_button = choice.addButton(
            "Update Saved Information",
            QMessageBox.AcceptRole,
        )
        keep_button = choice.addButton(
            "Keep Saved Information",
            QMessageBox.DestructiveRole,
        )
        cancel_button = choice.addButton(QMessageBox.Cancel)
        choice.setDefaultButton(update_button)
        choice.exec_()
        clicked_button = choice.clickedButton()
        if clicked_button == cancel_button:
            return False
        if clicked_button == keep_button:
            self._restore_hardware_identity(saved_identity)
            return True

        serials_changed = any(
            str(saved_identity[key] or "").strip()
            != str(current_identity[key] or "").strip()
            for key in ("Main board serial", "Switch serial")
        )
        rename_files = QMessageBox.No
        if serials_changed:
            rename_files = QMessageBox.question(
                self,
                "Rename run files?",
                "Rename the run folder, CSV, JSON, and COC workbook to match "
                "the updated serial numbers?\n\n"
                "The original run timestamp will be preserved.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
        new_metadata = dict(self.run_data.metadata)
        new_metadata.update(current_identity)
        try:
            if rename_files == QMessageBox.Yes:
                if self.run_recorder is None:
                    self.run_recorder = self.run_repository.recorder_from_existing(
                        self.run_data.source_path,
                        metadata=self.run_data.metadata,
                        limit=self.limit_spin.value(),
                        criteria_snapshot=self.run_data.criteria_snapshot,
                        measurement_attempts=self.run_data.measurement_attempts,
                        replacement_analysis=self.run_data.replacement_analysis,
                        completed_replacements=self.run_data.completed_replacements,
                    )
                new_metadata = self.run_recorder.rename_for_metadata(new_metadata)
                self.run_data.source_path = self.run_recorder.csv_path
            else:
                self.run_data.metadata = new_metadata
                self.persist_run_metadata()
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.critical(
                self,
                "Could not update run information",
                str(error),
            )
            return False

        self.run_data.metadata = new_metadata
        if self.run_recorder is not None:
            self.run_recorder.metadata = dict(new_metadata)
        self.file_label.setText(str(self.run_data.source_path))
        self.metadata_labels["Source file"].setText(self.run_data.source_path.name)
        self.metadata_labels["Part number"].setText(
            new_metadata.get("Part number") or "Not recorded"
        )
        self.metadata_labels["Main board serial"].setText(
            new_metadata.get("Main board serial") or "Not recorded"
        )
        self.metadata_labels["Switch serial"].setText(
            new_metadata.get("Switch serial") or "Not recorded"
        )
        self.metadata_labels["Tested by"].setText(
            new_metadata.get("Tested by") or "Not recorded"
        )
        if rename_files == QMessageBox.Yes:
            self.persist_run_metadata()
        self.statusBar().showMessage("Loaded run information updated.")
        return True

    def start_hardware(self, channels=None, retest=False):
        if self.hardware_run_active:
            return
        if not self._authorize_hardware_start(retest=retest):
            return
        confirmation = QMessageBox.question(
            self,
            "Start real hardware run",
            "This will use the connected measurement hardware and optical "
            "switch, and it will move the switch. "
            "Start the hardware run?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return

        run_mode = "new"
        if not retest and self.run_data is not None:
            run_mode = self.choose_hardware_run_mode()
            if run_mode is None:
                return
        if run_mode == "continue" and not self.confirm_existing_run_identity():
            return

        selected_identity = self._current_hardware_identity()
        selected_run_number = self.hardware_run_number.value()
        selected_unit_directory = self.unit_repository.unit_directory_for_metadata(
            DEFAULT_RUN_ROOT,
            selected_identity,
        )
        if not retest and run_mode == "new":
            if selected_run_number in self.unit_repository.available_run_numbers(
                selected_unit_directory
            ):
                QMessageBox.warning(
                    self,
                    "Run already exists",
                    "Run %d already exists for this unit. Load it to continue, "
                    "or choose a different run number."
                    % selected_run_number,
                )
                return
            target_csv = self.run_repository.run_csv_for_number(
                selected_unit_directory,
                selected_run_number,
                selected_identity.get("Switch serial", ""),
            )
            if target_csv.is_file():
                QMessageBox.warning(
                    self,
                    "Run already exists",
                    "Run %d already exists for this unit. Load it or choose a "
                    "different run number before starting."
                    % selected_run_number,
                )
                return

        continuing_existing = run_mode == "continue"
        if continuing_existing or retest:
            profile = self._profile_for_current_run()
        else:
            if self.limit_profile_error:
                QMessageBox.warning(
                    self,
                    "Limit profiles unavailable",
                    "The configured limit profiles could not be loaded:\n%s" % self.limit_profile_error,
                )
                return
            model = self._connected_switch_model()
            profile = self.limit_profiles.get(model)
            if profile is None:
                QMessageBox.warning(
                    self,
                    "Unsupported switch model",
                    "No limit profile is configured for the connected switch model: %s" % model,
                )
                return
        self._set_active_limit_profile(profile)
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "run.criteria_snapshot_resolved",
            switch_model=profile.model,
            criteria_profile=profile.profile_name,
            criteria_revision=profile.revision,
            too_good_limit_db=profile.too_good_below_db,
            fail_limit_db=profile.fail_above_db,
            warning_enabled=profile.warning_enabled,
            criteria_snapshot=profile.as_dict(),
            status="success",
        )
        try:
            preparation = prepare_hardware_run(
                retest=retest,
                requested_channels=channels,
                channel_mode=self.hardware_channel_mode.currentText(),
                single_channel=self.hardware_single_channel.value(),
                channel_ranges=self.hardware_channel_ranges.text(),
                manual_channel_order=self.manual_channel_order_checkbox.isChecked(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Invalid channel selection", str(error))
            return

        channels = preparation.channels

        owner_token = object()
        self.current_run_workflow = self._new_workflow("hardware_run")
        workflow_id = (
            self.current_run_workflow.workflow_id
            if self.current_run_workflow
            else ""
        )
        meter = self._meter_proxy_for_workflow(
            owner_token,
            "Hardware run",
            self.current_run_workflow,
            connect_if_needed=False,
        )
        switch = self._switch_proxy_for_workflow(
            owner_token,
            "Hardware run",
            self.current_run_workflow,
            connect_if_needed=False,
        )
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "run.started",
            workflow_id=workflow_id,
            workflow_type="hardware_run",
            run_number=selected_run_number,
            unit_serial=selected_identity.get("Main board serial"),
            switch_serial=selected_identity.get("Switch serial"),
            operator_initials=self.hardware_tested_by.text().strip(),
            retest=retest,
            live_write_mode=self.live_write_mode_enabled,
            status="started",
        )

        self.hardware_session.begin(
            retest=retest,
            plan=preparation.plan,
        )
        self.active_run_reference_snapshot = dict(
            self.reference_session.snapshot.as_dict()
        )
        if not retest and run_mode == "new":
            self.run_data = RunData(
                self.unit_repository.run_directory_for_number(
                    selected_unit_directory,
                    selected_run_number,
                    selected_identity.get("Switch serial", ""),
                ),
                [],
                {
                    "Mode": "Real hardware",
                    "Part number": self.hardware_part_number.currentText().strip(),
                    "Main board serial": self.hardware_main_board_serial.text().strip(),
                    "Switch serial": self.hardware_switch_serial.text().strip(),
                    "Operating band": self.hardware_operating_band.currentText().strip() or "O band",
                    "Tested by": self.hardware_tested_by.text().strip(),
                    "Run number": str(selected_run_number),
                },
                criteria_snapshot=profile.as_dict(),
            )
            self._load_unit_state(selected_unit_directory)
            self.run_recorder = self.run_repository.new_recorder(
                metadata=self.run_data.metadata,
                limit=self.limit_spin.value(),
                criteria_snapshot=profile.as_dict(),
                directory=self.run_data.source_path,
            )
            self.switch_test_timer = SwitchTestTimer(
                self.run_data.metadata,
                self.run_data.switch_test_sessions,
            )
            self.replacement_analysis = None
            self.run_data.replacement_analysis = None
            self.run_data.completed_replacements = list(self.completed_replacements)
            self.run_data.source_path = self.run_recorder.csv_path
        elif not retest:
            if self.run_recorder is None:
                self.run_recorder = self.run_repository.recorder_from_existing(
                    self.run_data.source_path,
                    metadata=self.run_data.metadata,
                    limit=self.limit_spin.value(),
                    criteria_snapshot=self.run_data.criteria_snapshot,
                    measurement_attempts=self.run_data.measurement_attempts,
                    replacement_analysis=self.run_data.replacement_analysis,
                    switch_test_sessions=self.run_data.switch_test_sessions,
                    completed_replacements=self.run_data.completed_replacements,
                )
            self.run_data.source_path = self.run_recorder.csv_path
            self.replacement_analysis = self.run_data.replacement_analysis
            if self.unit_directory is None:
                self._load_unit_state(selected_unit_directory)
            self.run_data.completed_replacements = list(self.completed_replacements)

        if continuing_existing:
            self.file_label.setText(str(self.run_data.source_path))
            self.metadata_labels["Source file"].setText(
                self.run_data.source_path.name
            )
        else:
            self.file_label.setText("Hardware run - not yet saved")
            self.metadata_labels["Source file"].setText("Hardware run")
        self.metadata_labels["Part number"].setText(
            self.run_data.metadata.get("Part number", "Not recorded")
        )
        self.metadata_labels["Main board serial"].setText(
            self.run_data.metadata.get("Main board serial", "Connected instrument")
        )
        self.metadata_labels["Switch serial"].setText(
            self.run_data.metadata.get("Switch serial", "Connected instrument")
        )
        self.metadata_labels["Operating band"].setText(
            self.run_data.metadata.get("Operating band", "O band")
        )
        self.metadata_labels["Tested by"].setText(
            self.run_data.metadata.get("Tested by", "Not recorded")
        )
        self.metadata_labels["Run number"].setText(
            self.run_data.metadata.get("Run number", str(selected_run_number))
        )
        self.refresh_analysis()

        request = build_hardware_run_request(
            preparation,
            meter=meter,
            switch=switch,
            reference_powers={
                1310: self.reference_session.snapshot.reference_1310_dbm,
                1550: self.reference_session.snapshot.reference_1550_dbm,
            },
            existing_channels=(
                [record.channel for record in self.run_data.measurements]
                if continuing_existing
                else None
            ),
            resume_existing=continuing_existing,
            live_write_mode=self.live_write_mode_enabled,
            support_logger=self.support_logger,
            workflow_id=workflow_id,
            reference_snapshot=self.active_run_reference_snapshot,
        )
        try:
            self.hardware_controller.start(request)
        except (RuntimeError, OSError) as error:
            self._record_support(
                SupportEventCategory.WORKFLOW,
                "run.start_failed",
                level=SupportLogLevel.ERROR,
                workflow_id=workflow_id,
                error_type=type(error).__name__,
                error_message=str(error),
                status="error",
            )
            QMessageBox.critical(self, "Hardware unavailable", str(error))
            return
        self.hardware_thread = self.hardware_controller.thread
        self.hardware_worker = self.hardware_controller.worker
        self.live_write_mode_action.setEnabled(False)
        self.start_hardware_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(True)
        self.set_open_csv_available(False)
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.retest_button.setEnabled(False)
        self.statusBar().showMessage("Starting hardware run...")
        self.begin_switch_test_session()
        self._update_hardware_readiness_controls()

    def _run_start_preflight(self):
        """Collect current UI state and validate it without side effects."""
        reference = self.reference_session.snapshot
        return validate_run_preflight(
            admin_mode=self.admin_session.is_active,
            metadata=self._current_hardware_identity(),
            run_number=self.hardware_run_number.value(),
            channel_mode=self.hardware_channel_mode.currentText(),
            single_channel=self.hardware_single_channel.value(),
            channel_ranges=self.hardware_channel_ranges.text(),
            manual_channel_order=self.manual_channel_order_checkbox.isChecked(),
            hardware_ready=self.hardware_connection_manager.run_ready,
            reference_valid=self.reference_session.is_valid,
            reference_state=self.reference_session.state,
            reference_method=reference.method if reference is not None else "",
            reference_hardware_matches=(
                self._reference_hardware_matches_snapshot()
                if reference is not None
                else False
            ),
        )

    @staticmethod
    def _preflight_issue_details(issues):
        """Format structured issues for a technician-friendly popup."""
        lines = []
        seen = set()
        for issue in issues:
            detail = issue.label
            if issue.category is not RunPreflightIssueCategory.METADATA:
                detail = "%s: %s" % (issue.label, issue.message)
            if detail not in seen:
                lines.append("- " + detail)
                seen.add(detail)
        return "\n".join(lines)

    def _focus_preflight_issue(self, issues):
        focus_widgets = {
            "main_board_serial": self.hardware_main_board_serial,
            "switch_serial": self.hardware_switch_serial,
            "part_number": self.hardware_part_number,
            "operating_band": self.hardware_operating_band,
            "tested_by": self.hardware_tested_by,
            "run_number": self.hardware_run_number,
            "channel_mode": self.hardware_channel_mode,
            "single_channel": self.hardware_single_channel,
            "channel_ranges": self.hardware_channel_ranges,
            "reference_1310": self.reference_1310_spin,
            "hardware": self.connect_hardware_button,
        }
        for issue in issues:
            widget = focus_widgets.get(issue.field_id)
            if widget is not None:
                widget.setFocus()
                break

    def _show_preflight_blocked(self, result):
        issues = result.issues
        reference_only = all(
            issue.category is RunPreflightIssueCategory.REFERENCE
            for issue in issues
        )
        hardware_only = all(
            issue.category is RunPreflightIssueCategory.HARDWARE
            for issue in issues
        )
        if reference_only:
            title = "Reference required"
            intro = "Calculate an authorized reference before starting the run:"
        elif hardware_only:
            title = "Hardware not ready"
            intro = "Connect the required hardware before starting the run:"
        else:
            title = "Hardware test setup incomplete"
            intro = "Complete the following before starting the run:"
        QMessageBox.warning(
            self,
            title,
            "%s\n\n%s" % (intro, self._preflight_issue_details(issues)),
            QMessageBox.Ok,
        )
        self._focus_preflight_issue(issues)

    def _authorize_hardware_start(self, *, retest=False):
        """Apply role policy to one production start before any side effect."""
        result = self._run_start_preflight()
        issue_codes = ", ".join(issue.code for issue in result.issues)
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "run.preflight_started",
            admin_mode=self.admin_session.is_active,
            run_number=self.hardware_run_number.value(),
            channel_mode=self.hardware_channel_mode.currentText(),
            retest=retest,
            details=issue_codes,
            status="started",
        )

        if result.non_metadata_issues:
            self._record_support(
                SupportEventCategory.WORKFLOW,
                "run.preflight_blocked",
                admin_mode=self.admin_session.is_active,
                run_number=self.hardware_run_number.value(),
                channel_mode=self.hardware_channel_mode.currentText(),
                retest=retest,
                details=issue_codes,
                status="blocked",
            )
            self._show_preflight_blocked(result)
            return False

        if result.metadata_issues:
            if not self.admin_session.is_active:
                self._record_support(
                    SupportEventCategory.WORKFLOW,
                    "run.preflight_blocked",
                    admin_mode=False,
                    run_number=self.hardware_run_number.value(),
                    channel_mode=self.hardware_channel_mode.currentText(),
                    retest=retest,
                    details=issue_codes,
                    status="blocked",
                )
                self._show_preflight_blocked(result)
                return False
            if not self.confirm_hardware_setup_complete(result.metadata_issues):
                self._record_support(
                    SupportEventCategory.WORKFLOW,
                    "run.preflight_blocked",
                    admin_mode=True,
                    run_number=self.hardware_run_number.value(),
                    channel_mode=self.hardware_channel_mode.currentText(),
                    retest=retest,
                    details=issue_codes,
                    status="blocked",
                )
                return False

        self._record_support(
            SupportEventCategory.WORKFLOW,
            "run.preflight_passed",
            admin_mode=self.admin_session.is_active,
            run_number=self.hardware_run_number.value(),
            channel_mode=self.hardware_channel_mode.currentText(),
            retest=retest,
            details=issue_codes,
            status="success",
        )
        return True

    def confirm_hardware_setup_complete(self, metadata_issues=None):
        """Offer the metadata-only bypass to an authenticated administrator."""
        if metadata_issues is None:
            result = self._run_start_preflight()
            metadata_issues = result.metadata_issues
        if not metadata_issues:
            return True
        if not self.admin_session.is_active:
            return False

        missing_metadata = [issue.label for issue in metadata_issues]
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "run.admin_metadata_warning_shown",
            admin_mode=True,
            details=", ".join(missing_metadata),
            status="shown",
        )
        choice = QMessageBox(self)
        choice.setWindowTitle("Hardware test setup incomplete")
        choice.setText("The following metadata is missing:")
        choice.setInformativeText("\n".join("- %s" % item for item in missing_metadata))
        return_button = choice.addButton(
            "Return to Setup",
            QMessageBox.RejectRole,
        )
        continue_button = choice.addButton(
            "Continue Without Metadata",
            QMessageBox.AcceptRole,
        )
        choice.setDefaultButton(return_button)
        choice.exec_()
        if choice.clickedButton() != continue_button:
            self._record_support(
                SupportEventCategory.WORKFLOW,
                "run.admin_returned_to_setup",
                admin_mode=True,
                details=", ".join(missing_metadata),
                status="blocked",
            )
            return False
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "run.admin_continued_without_metadata",
            admin_mode=True,
            choice="continue_without_metadata",
            details=", ".join(missing_metadata),
            status="accepted",
        )
        return True

    def begin_switch_test_session(self):
        """Start timing one real switch-test session."""
        if self.run_data is None:
            return
        if (
            self.switch_test_timer is None
            or self.switch_test_timer.metadata is not self.run_data.metadata
        ):
            self.switch_test_timer = SwitchTestTimer(
                self.run_data.metadata,
                self.run_data.switch_test_sessions,
            )
        self.switch_test_timer.start_session()
        self.run_data.switch_test_sessions = self.switch_test_timer.sessions
        self.persist_run_metadata()

    def finish_switch_test_session(self):
        """Stop timing the current real switch-test session and save it."""
        if self.switch_test_timer is None or not self.switch_test_timer.active:
            return
        self.switch_test_timer.stop_session()
        self.run_data.switch_test_sessions = self.switch_test_timer.sessions
        try:
            self.persist_run_metadata()
        except (OSError, ValueError, TypeError) as error:
            self.statusBar().showMessage(
                "Switch timing updated in memory but could not be saved: %s" % error
            )

    def hardware_channel_configuration_ready(self, channel_count):
        self.hardware_session.set_configured_channel_count(channel_count)

    def hardware_continuation_selection_required(
        self,
        channel_count,
        completed_channels,
        default_channel,
    ):
        """Choose where a loaded full-pass run should resume."""
        if self.hardware_worker is None:
            return
        channel, accepted = QInputDialog.getInt(
            self,
            "Continue Existing Run",
            (
                "%d of %d channels already have saved readings.\n"
                "Choose the first channel to measure or retest:"
                % (len(completed_channels), channel_count)
            ),
            default_channel,
            1,
            channel_count,
            1,
        )
        if accepted:
            self._hardware_command("select_resume_channel", channel)
        else:
            self._hardware_command("stop")

    def hardware_channel_selection_required(self, channel_count, completed_channels):
        """Ask for the next channel during an optional manual-order pass."""
        if self.hardware_worker is None:
            return

        completed_count = len(completed_channels)
        if completed_count >= channel_count:
            prompt = (
                "All configured channels have been tested. Enter a channel "
                "to retest, or click Cancel to finish the pass."
            )
        else:
            prompt = (
                "Choose the next channel to test.\n"
                "%d of %d channels have been tested; repeated channels are "
                "allowed."
                % (completed_count, channel_count)
            )

        channel, accepted = QInputDialog.getInt(
            self,
            "Choose next channel",
            prompt,
            1,
            1,
            channel_count,
            1,
        )
        if accepted:
            self._hardware_command("select_next_channel", channel)
        elif completed_count >= channel_count:
            self._hardware_command("finish_manual_pass")
        else:
            self._hardware_command("stop")

    def change_hardware_channel(self):
        """Replace the current uncommitted hardware step with another channel."""
        if self.hardware_worker is None:
            return

        maximum_channel = self.hardware_configured_channel_count or 256
        current_channel = self.hardware_pending_channel or 1
        channel, accepted = QInputDialog.getInt(
            self,
            "Change Channel",
            "Enter the channel to measure next:",
            current_channel,
            1,
            maximum_channel,
            1,
        )
        if not accepted:
            return

        resume_interrupted = False
        if self.hardware_full_pass and not self.hardware_manual_channel_order:
            choice = QMessageBox(self)
            choice.setWindowTitle("After the channel change")
            choice.setText(
                "After channel %d is written, how should the full pass continue?"
                % channel
            )
            choice.setInformativeText(
                "Continue sequentially from the selected channel, or return to "
                "the channel that was interrupted?"
            )
            sequential_button = choice.addButton(
                "Continue sequentially",
                QMessageBox.AcceptRole,
            )
            resume_button = choice.addButton(
                "Resume interrupted channel",
                QMessageBox.ActionRole,
            )
            cancel_button = choice.addButton(QMessageBox.Cancel)
            choice.setDefaultButton(sequential_button)
            choice.exec_()
            clicked_button = choice.clickedButton()
            if clicked_button is None or clicked_button == cancel_button:
                return
            resume_interrupted = clicked_button == resume_button

        self.hardware_session.clear_pending()
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.clear_current_reading(channel, "Changing to channel %d..." % channel)
        self.refresh_table()
        self.demo_channel_label.setText(
            "Changing to channel %d without stopping the run" % channel
        )
        self._record_support(
            SupportEventCategory.OPERATOR,
            "run.channel_change_requested",
            workflow_id=(
                self.current_run_workflow.workflow_id
                if self.current_run_workflow
                else ""
            ),
            logical_channel=channel,
            choice=(
                "resume_interrupted"
                if resume_interrupted
                else "continue_sequentially"
            ),
            status="requested",
        )
        self._hardware_command("change_channel", channel, resume_interrupted)

    def hardware_operator_required(self, channel, physical_port):
        self.hardware_session.set_pending_channel(channel, physical_port)
        self.pending_reading_validation = None
        self.hardware_live_indicator.setVisible(self.live_write_mode_enabled)
        self.clear_current_reading(
            channel,
            "Move cable to this channel; live reading is active"
            if self.live_write_mode_enabled
            else "Move cable, then read values",
        )
        self.continue_hardware_button.setEnabled(
            not self.live_write_mode_enabled
        )
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(True)
        self.refresh_table()
        self.demo_channel_label.setText(
            "Channel %d routed to physical port %d - move cable, then %s"
            % (
                channel,
                physical_port,
                "live reading is active"
                if self.live_write_mode_enabled
                else "read",
            )
        )

    def continue_hardware(self):
        if (
            self.hardware_worker is not None
            and self.continue_hardware_button.isEnabled()
        ):
            self.continue_hardware_button.setEnabled(False)
            self.change_hardware_channel_button.setEnabled(False)
            if self.hardware_pending_reading is None:
                self._record_support(
                    SupportEventCategory.OPERATOR,
                    "measurement.read_requested",
                    workflow_id=(
                        self.current_run_workflow.workflow_id
                        if self.current_run_workflow
                        else ""
                    ),
                    logical_channel=self.hardware_pending_channel,
                    status="requested",
                )
                self._hardware_command("continue_current")
            else:
                self._record_support(
                    SupportEventCategory.OPERATOR,
                    "measurement.repeat_requested",
                    workflow_id=(
                        self.current_run_workflow.workflow_id
                        if self.current_run_workflow
                        else ""
                    ),
                    logical_channel=self.hardware_pending_channel,
                    repeated_reading=True,
                    status="requested",
                )
                self._hardware_command("read_current")

    def write_hardware(self):
        if self.hardware_pending_reading is not None:
            validation = validate_insertion_loss(
                {
                    1310: self.hardware_pending_reading[2],
                    1550: self.hardware_pending_reading[3],
                }
            )
            if not validation.valid:
                self._record_negative_loss_write_attempt(validation)
                QMessageBox.warning(
                    self,
                    "Invalid insertion-loss reading",
                    self._negative_loss_message(validation),
                )
                self.write_hardware_button.setEnabled(False)
                return False
        return self._commit_and_advance_hardware()

    def _commit_and_advance_hardware(self):
        """Save a pending reading and let the worker continue to the next step."""
        if self.hardware_worker is None or self.hardware_pending_reading is None:
            return False
        try:
            committed = self.commit_hardware_reading()
        except Exception as error:
            QMessageBox.critical(
                self,
                "Could not save reading",
                "The reading was not committed to the run:\n%s\n\n"
                "Correct the storage problem and take the reading again." % error,
            )
            self.write_hardware_button.setEnabled(True)
            return False
        if not committed:
            return False
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self._hardware_command("write_current")
        return True

    def _hardware_command(self, command, *args):
        """Send a worker command through the controller when it owns the run.

        The fallback preserves lightweight UI tests and compatibility with
        older callers that inject a fake worker directly.
        """
        if self.hardware_controller.is_active:
            return getattr(self.hardware_controller, command)(*args)
        if self.hardware_worker is not None:
            return getattr(self.hardware_worker, command)(*args)
        return None

    def commit_hardware_reading(self):
        channel, physical_port, loss_1310, loss_1550 = self.hardware_pending_reading
        if self.run_data is None:
            return False
        validation = validate_insertion_loss(
            {1310: loss_1310, 1550: loss_1550}
        )
        if not validation.valid:
            self._record_negative_loss_write_attempt(validation)
            return False
        record = MeasurementRecord(
            channel,
            loss_1310,
            loss_1550,
            physical_port,
            dict(self.active_run_reference_snapshot)
            if self.active_run_reference_snapshot
            else None,
        )
        attempt = self._accept_measurement_record(record)
        self._record_support(
            SupportEventCategory.MEASUREMENT,
            "measurement.written",
            workflow_id=(
                self.current_run_workflow.workflow_id
                if self.current_run_workflow
                else ""
            ),
            run_number=self.run_data.metadata.get("Run number"),
            unit_serial=self.run_data.metadata.get("Main board serial"),
            switch_serial=self.run_data.metadata.get("Switch serial"),
            operator_initials=self.run_data.metadata.get("Tested by"),
            logical_channel=channel,
            physical_port=physical_port,
            loss_1310_db=loss_1310,
            loss_1550_db=loss_1550,
            attempt_id=attempt.attempt_id,
            attempt_number=attempt.attempt_number,
            replaces_attempt_id=attempt.replaces_attempt_id,
            retest=attempt.attempt_number > 1,
            reading_state="written",
            both_wavelengths_complete=True,
            measurement_count=len(self.run_data.measurements),
            status="success",
        )
        self.hardware_session.clear_pending()
        self.refresh_analysis()
        self.scroll_to_channel(channel)
        return True

    def _accept_measurement_record(self, record, *, write_context="initial"):
        """Append one accepted reading and atomically save its latest projection."""
        if self.run_data is None:
            raise ValueError("No run is loaded.")
        prior = latest_attempt_for_channel(
            self.run_data.measurement_attempts,
            record.channel,
        )
        attempt = new_measurement_attempt(
            record,
            prior=prior,
            operator_initials=self.run_data.metadata.get("Tested by", ""),
            write_context=write_context,
            run_id=(
                self.run_recorder.run_id
                if self.run_recorder is not None
                else str(Path(self.run_data.source_path).resolve())
            ),
        )
        updated_measurements = [
            existing
            for existing in self.run_data.measurements
            if existing.channel != record.channel
        ]
        updated_measurements.append(record)
        updated_measurements.sort(key=lambda existing: existing.channel)
        updated_attempts = [
            existing
            for existing in self.run_data.measurement_attempts
        ]
        updated_attempts.append(attempt)
        if self.run_recorder is not None:
            self.run_recorder.save(
                updated_measurements,
                measurement_attempts=updated_attempts,
            )
        self.run_data.measurements = updated_measurements
        self.run_data.measurement_attempts = updated_attempts
        self.run_data.attempts = [attempt.as_dict() for attempt in updated_attempts]
        return attempt

    def show_keybind_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Keybinds")
        layout = QGridLayout(dialog)
        layout.addWidget(QLabel("Read IL Values:"), 0, 0)
        read_edit = QKeySequenceEdit(self.continue_shortcut.key())
        layout.addWidget(read_edit, 0, 1)
        layout.addWidget(QLabel("Write IL Values:"), 1, 0)
        write_edit = QKeySequenceEdit(self.write_shortcut.key())
        layout.addWidget(write_edit, 1, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons, 2, 0, 1, 2)
        if dialog.exec_() == QDialog.Accepted:
            self.settings.setValue("continue_key", read_edit.keySequence().toString())
            self.settings.setValue("write_key", write_edit.keySequence().toString())
            self.update_shortcuts()

    def update_shortcuts(self):
        """Apply and persist the operator-configured action shortcuts."""
        # Clear each Python reference before scheduling Qt's deferred object
        # deletion. In particular, the keypad-Enter alias is only recreated
        # for the Return binding; retaining its old wrapper caused a crash
        # when a user changed Return -> - -> Enter across dialog saves.
        old_continue_shortcut = self.continue_shortcut
        self.continue_shortcut = None
        if old_continue_shortcut is not None:
            old_continue_shortcut.deleteLater()

        old_keypad_shortcut = self.keypad_enter_shortcut
        self.keypad_enter_shortcut = None
        if old_keypad_shortcut is not None:
            old_keypad_shortcut.deleteLater()

        old_write_shortcut = getattr(self, "write_shortcut", None)
        self.write_shortcut = None
        if old_write_shortcut is not None:
            old_write_shortcut.deleteLater()

        continue_key = self.settings.value(
            "continue_key",
            DEFAULT_READ_SHORTCUT,
        )
        # Older builds used the Qt keypad-Enter name as the default. Treat
        # that exact saved value as the normal keyboard Enter/Return shortcut
        # so existing users receive the corrected binding automatically.
        if continue_key == KEYPAD_ENTER_SHORTCUT:
            continue_key = DEFAULT_READ_SHORTCUT
            self.settings.setValue("continue_key", continue_key)

        self.continue_shortcut = QShortcut(
            QKeySequence(continue_key),
            self,
        )
        self.continue_shortcut.setContext(Qt.ApplicationShortcut)
        self.continue_shortcut.activated.connect(self.continue_hardware)
        # Keep keypad Enter useful when the configured read shortcut is the
        # normal keyboard Enter/Return key.
        if QKeySequence(continue_key) == QKeySequence(DEFAULT_READ_SHORTCUT):
            self.keypad_enter_shortcut = QShortcut(
                QKeySequence(KEYPAD_ENTER_SHORTCUT),
                self,
            )
            self.keypad_enter_shortcut.setContext(Qt.ApplicationShortcut)
            self.keypad_enter_shortcut.activated.connect(self.continue_hardware)
        self.write_shortcut = QShortcut(
            QKeySequence(self.settings.value("write_key", "+")),
            self,
        )
        self.write_shortcut.setContext(Qt.ApplicationShortcut)
        self.write_shortcut.activated.connect(self.write_hardware)
        self.write_shortcut.setEnabled(True)
        self.settings.setValue(
            "continue_key",
            self.continue_shortcut.key().toString(),
        )
        self.settings.setValue(
            "write_key",
            self.write_shortcut.key().toString(),
        )
        self.continue_hardware_button.set_shortcut(self.continue_shortcut.key())
        self.write_hardware_button.set_shortcut(self.write_shortcut.key())
        self._apply_run_mode_controls()

    def hardware_reading_ready(self, channel, _physical_port, loss_1310, loss_1550):
        self.hardware_session.set_pending_reading(
            channel,
            _physical_port,
            loss_1310,
            loss_1550,
        )
        validation = validate_insertion_loss({1310: loss_1310, 1550: loss_1550})
        self.pending_reading_validation = validation
        self._record_support(
            SupportEventCategory.MEASUREMENT,
            "measurement.presented",
            workflow_id=(
                self.current_run_workflow.workflow_id
                if self.current_run_workflow
                else ""
            ),
            logical_channel=channel,
            physical_port=_physical_port,
            loss_1310_db=loss_1310,
            loss_1550_db=loss_1550,
            reading_state="temporary",
            both_wavelengths_complete=True,
            validation_reason=validation.reason,
            invalid_wavelength=",".join(
                str(value) for value in validation.invalid_wavelengths
            ),
            status="success" if validation.valid else "warning",
        )
        self.set_current_reading_channel(channel)
        self.current_loss_1310 = loss_1310
        self.current_loss_1550 = loss_1550
        self.refresh_current_reading()
        if not validation.valid:
            self.reading_status_label.setText(
                "Invalid negative loss - check the reference or current connection"
            )
            self._refresh_reading_status_color()
        self.demo_1310_label.setText("1310 nm: %.4f dB" % loss_1310)
        self.demo_1550_label.setText("1550 nm: %.4f dB" % loss_1550)
        self.continue_hardware_button.setEnabled(not self.live_write_mode_enabled)
        self.write_hardware_button.setEnabled(validation.valid)
        self.change_hardware_channel_button.setEnabled(True)
        self.hardware_live_indicator.setVisible(self.live_write_mode_enabled)
        if validation.valid:
            self.demo_channel_label.setText(
                "Channel %d live reading - write when ready" % channel
                if self.live_write_mode_enabled
                else "Channel %d measured - read again or write values" % channel
            )
        else:
            self.demo_channel_label.setText(
                "Invalid negative loss - check the reference or current connection"
            )
        self.refresh_table()
        # In Live Write Mode the table may receive many readings before the
        # operator accepts one. Keep the operator's current scroll position
        # until Write IL commits the pending reading.
        if not self.live_write_mode_enabled:
            self.scroll_to_channel(channel)

    @staticmethod
    def _negative_loss_message(validation):
        details = []
        if validation.rounded_losses:
            for wavelength in validation.invalid_wavelengths:
                details.append(
                    "%d nm insertion loss: %.4f dB"
                    % (wavelength, validation.rounded_losses[wavelength])
                )
        return (
            "Negative insertion loss was detected. This indicates that the "
            "reference or the current measurement may be incorrect.\n\n%s\n\n"
            "Check the cable connection and reference, then retest."
            % ("\n".join(details) or "Check both wavelength values.")
        )

    def _record_negative_loss_write_attempt(self, validation):
        self._record_support(
            SupportEventCategory.OPERATOR,
            "measurement.write_rejected_negative_loss",
            workflow_id=(
                self.current_run_workflow.workflow_id
                if self.current_run_workflow
                else ""
            ),
            logical_channel=self.hardware_pending_channel,
            physical_port=self.hardware_pending_physical_port,
            validation_reason=validation.reason,
            invalid_wavelength=",".join(
                str(value) for value in validation.invalid_wavelengths
            ),
            status="rejected",
        )
    def hardware_progress_changed(self, current, total):
        if self.hardware_manual_channel_order:
            self.demo_channel_label.setText(
                "Manual pass: %d of %d unique channels complete"
                % (current, total)
            )
        else:
            self.demo_channel_label.setText(
                "Hardware channel %d of %d saved" % (current, total)
            )

    def hardware_completed(self):
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "run.completed",
            workflow_id=(
                self.current_run_workflow.workflow_id
                if self.current_run_workflow
                else ""
            ),
            measurement_count=(len(self.run_data.measurements) if self.run_data else 0),
            status="success",
        )
        self.finish_switch_test_session()
        self.hardware_live_indicator.setVisible(False)
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(False)
        self.retest_button.setEnabled(True)
        self.active_run_reference_snapshot = None
        self.statusBar().showMessage("Hardware run complete. CSV and JSON are saved.")

    def hardware_stopped(self):
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "run.stopped",
            workflow_id=(
                self.current_run_workflow.workflow_id
                if self.current_run_workflow
                else ""
            ),
            measurement_count=(len(self.run_data.measurements) if self.run_data else 0),
            status="stopped",
        )
        self.finish_switch_test_session()
        self.hardware_live_indicator.setVisible(False)
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(False)
        self.retest_button.setEnabled(bool(self.run_data and self.run_data.measurements))
        self.active_run_reference_snapshot = None
        self.statusBar().showMessage("Hardware run stopped. Completed readings remain visible.")

    def hardware_failed(self, message):
        self._record_support(
            SupportEventCategory.WORKFLOW,
            "run.failed",
            level=SupportLogLevel.ERROR,
            workflow_id=(
                self.current_run_workflow.workflow_id
                if self.current_run_workflow
                else ""
            ),
            error_message=message,
            measurement_count=(len(self.run_data.measurements) if self.run_data else 0),
            status="error",
        )
        self.finish_switch_test_session()
        self.hardware_live_indicator.setVisible(False)
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(False)
        self.active_run_reference_snapshot = None
        QMessageBox.critical(self, "Hardware run stopped", message)

    def stop_hardware(self):
        if self.hardware_controller.is_active:
            self.hardware_controller.stop()
        elif self.hardware_worker is not None:
            self.hardware_worker.stop()

    def hardware_thread_finished(self):
        # This is a fallback for shutdown paths where the worker's queued
        # stopped/failed signal cannot be delivered before the thread closes.
        self.finish_switch_test_session()
        # The worker belongs to the worker thread. Calling worker.deleteLater()
        # from this main-thread slot after the event loop has stopped can race
        # with Qt's deferred-delete handling and trigger a native Qt abort.
        # The worker is therefore left to Qt/Python ownership after the thread
        # has fully finished; only the main-thread QThread wrapper is deferred.
        finished_thread = self.hardware_thread
        self.hardware_thread = None
        self.hardware_worker = None
        self.active_run_reference_snapshot = None
        if finished_thread is not None:
            finished_thread.deleteLater()
        self._update_hardware_readiness_controls()
        self.live_write_mode_action.setEnabled(True)
        self.hardware_live_indicator.setVisible(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.set_open_csv_available(True)

    def set_open_csv_available(self, available):
        """Keep CSV loading disabled while a hardware run owns the UI."""
        self.open_csv_button.setEnabled(available)
        self.open_csv_action.setEnabled(available)
        self.load_run_button.setEnabled(available)

    def closeEvent(self, event):
        if hasattr(self, "support_log_size_timer"):
            self.support_log_size_timer.stop()
        self._record_support(
            SupportEventCategory.APPLICATION,
            "application.close_requested",
            status="requested",
        )
        if self.reference_worker is not None and self.reference_thread is not None:
            if not self.reference_controller.stop_and_wait():
                QMessageBox.warning(
                    self,
                    "Reference calculation",
                    "The reference meter is still disconnecting. "
                    "Please try closing the application again shortly.",
                )
                event.ignore()
                return
            self._close_reference_progress()
            self._update_hardware_readiness_controls()
        if self.hardware_run_active:
            if self.hardware_controller.is_active:
                if not self.hardware_controller.stop_and_wait():
                    QMessageBox.warning(
                        self,
                        "Hardware run",
                        "The hardware run is still stopping. "
                        "Please try closing the application again shortly.",
                    )
                    event.ignore()
                    return
            elif self.hardware_worker is not None and self.hardware_thread is not None:
                self.hardware_worker.stop()
                self.hardware_thread.quit()
                if not self.hardware_thread.wait(5000):
                    QMessageBox.warning(
                        self,
                        "Hardware run",
                        "The hardware run is still stopping. "
                        "Please try closing the application again shortly.",
                    )
                    event.ignore()
                    return
            self.finish_switch_test_session()
        try:
            self._record_support(
                SupportEventCategory.CONNECTION,
                "connection.application_cleanup_requested",
                status="requested",
            )
            self.hardware_connection_manager.close_all()
        except Exception as error:
            QMessageBox.warning(
                self,
                "Hardware disconnect",
                "Light Workbench could not safely disconnect all hardware:\n%s"
                % error,
            )
            event.ignore()
            return
        if hasattr(self, "part_lookup_controller"):
            self.part_lookup_controller.close()
        self._record_support(
            SupportEventCategory.APPLICATION,
            "application.close_completed",
            status="success",
        )
        if self.support_logger is not None:
            self.support_logger.flush(0.5)
        event.accept()

    def refresh_analysis(self):
        if self.run_data is None:
            return
        profile = self._profile_for_current_run()
        self._set_active_limit_profile(profile)
        summary = self.run_data.analysis_with_profile(profile)
        for key, label in self.metric_labels.items():
            if key in ("over_1310", "over_1550", "over_both"):
                label.setText(format_channel_summary(summary[key + "_channels"]))
            else:
                label.setText(str(summary[key]))
        self.refresh_current_reading()
        self.refresh_table()
        self.refresh_replacement_summary()
        self.refresh_coc_controls()

    def refresh_replacement_summary(self):
        """Refresh the replacement-analysis status shown beside the table."""
        has_measurements = bool(self.run_data and self.run_data.measurements)
        self.replacement_analysis_button.setEnabled(has_measurements)
        self.record_replacements_button.setEnabled(
            has_measurements or self.unit_directory is not None
        )
        self.copy_replacement_notes_button.setEnabled(
            bool(self.completed_replacements)
        )
        if self.completed_replacements:
            lines = [
                "Completed replacements: %d" % len(self.completed_replacements)
            ]
            lines.extend(
                "Current Port %d -> Replacement Port %d"
                % (
                    record["current_port"],
                    record["replacement_port"],
                )
                for record in self.completed_replacements
            )
        else:
            lines = ["No completed replacements recorded"]
        lines.append(
            "Designated spare ports: %s"
            % (
                ", ".join(str(port) for port in self.designated_spares)
                if self.designated_spares
                else "none"
            )
        )
        self.completed_replacements_label.setText("\n".join(lines))
        result = self.replacement_analysis
        if not result:
            self.replacement_summary_label.setText("Not run")
            return
        if not result.get("applicable"):
            self.replacement_summary_label.setText(result.get("status", "Not applicable"))
            return

        recommendations = result.get("recommendations", [])
        required_recommendations = [
            item
            for item in recommendations
            if recommendation_category(item, result.get("warning_limit_db")) == "required"
        ]
        optional_recommendations = [
            item
            for item in recommendations
            if recommendation_category(item, result.get("warning_limit_db")) == "optional"
        ]
        spare_ports = [
            str(spare["physical_port"])
            for spare in result.get("bottom_spares", [])
        ]
        too_good_spares = [
            str(spare["physical_port"])
            for spare in result.get("bottom_spares", [])
            if spare.get("too_good")
        ]
        lines = [
            "Required replacements: %d" % len(required_recommendations),
            "Optional Replacements: %d" % len(optional_recommendations),
            "Recommended designated spares: %s"
            % (", ".join(spare_ports) if spare_ports else "none"),
        ]
        if too_good_spares:
            lines.append(
                "Too-good spare warning: %s"
                % ", ".join(too_good_spares)
            )
        for title, categorized in (
            ("Required replacements", required_recommendations),
            ("Optional Replacements", optional_recommendations),
        ):
            if categorized:
                lines.append(title + ":")
                for recommendation in categorized:
                    lines.append(
                        "Logical %d: physical %d -> %d (improve %.4f dB)"
                        % (
                            recommendation["logical_channel"],
                            recommendation["current_physical_port"],
                            recommendation["candidate_physical_port"],
                            recommendation["improvement_db"],
                        )
                    )
        self.replacement_summary_label.setText("\n".join(lines))

    def show_completed_replacements(self):
        """Record manually completed replacements without using switch queries."""
        identity = self._current_hardware_identity()
        if not any(
            str(identity.get(key) or "").strip()
            for key in ("Main board serial", "Part number")
        ):
            QMessageBox.information(
                self,
                "Unit information required",
                "Enter a main board serial or part number before recording replacements.",
            )
            return
        if self.unit_directory is None:
            self.ensure_unit_state_for_current_fields()
        if self.unit_directory is None:
            QMessageBox.information(
                self,
                "Unit information required",
                "Enter a main board serial or load a unit before recording replacements.",
            )
            return

        recommendations = []
        if self.replacement_analysis:
            recommendations = self.replacement_analysis.get("recommendations", [])
        dialog = CompletedReplacementDialog(
            self.completed_replacements,
            recommendations,
            self.designated_spares,
            history=self.replacement_history,
            operator=self.hardware_tested_by.text().strip(),
            context={
                "source_run_number": (
                    self.run_data.metadata.get("Run number")
                    if self.run_data is not None
                    else None
                ),
                "main_board_serial": self.hardware_main_board_serial.text().strip(),
                "switch_serial": self.hardware_switch_serial.text().strip(),
            },
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        self.replacement_history = list(dialog.history)
        self.completed_replacements = effective_replacements(self.replacement_history)
        self.designated_spares = list(dialog.designated_spares)
        if self.run_data is not None:
            self.run_data.completed_replacements = list(self.completed_replacements)
        self.persist_unit_record()
        self._record_support(
            SupportEventCategory.OPERATOR,
            "replacement.records_saved",
            run_number=(
                self.run_data.metadata.get("Run number")
                if self.run_data is not None
                else None
            ),
            unit_serial=(
                self.run_data.metadata.get("Main board serial")
                if self.run_data is not None
                else self.hardware_main_board_serial.text().strip()
            ),
            measurement_count=len(self.completed_replacements),
            details="%d active replacement(s); %d designated spare(s)."
            % (len(self.completed_replacements), len(self.designated_spares)),
            status="success",
        )
        self.refresh_replacement_summary()
        self.statusBar().showMessage(
            "Completed replacements and designated spares saved to the unit record."
        )

    def copy_replacement_notes(self):
        """Copy completed physical-port swaps for pasting into Unit Editor."""
        if not self.completed_replacements:
            return
        lines = []
        for record in self.completed_replacements:
            line = "%d \u2192 %d" % (
                record["current_port"],
                record["replacement_port"],
            )
            if record.get("reason") or record.get("operator"):
                line += " - %s - %s - %s" % (
                    record.get("reason") or "Reason not recorded",
                    record.get("operator") or "Operator not recorded",
                    (record.get("recorded_at_utc") or "Date not recorded"),
                )
            lines.append(line)
        notes = "Port replacements completed:\n" + "\n".join(lines)
        QApplication.clipboard().setText(notes)
        self.statusBar().showMessage(
            "Replacement notes copied. Paste them into the Unit Editor notes."
        )

    def copy_raw_data(self):
        """Copy accepted readings from the active run as Excel-compatible TSV."""
        if self.run_data is None or not self.run_data.measurements:
            QMessageBox.information(
                self,
                "No raw data",
                "There are no completed readings to copy from this run.",
            )
            return

        try:
            raw_data = format_raw_measurements(self.run_data.measurements)
        except ValueError as error:
            QMessageBox.information(self, "No raw data", str(error))
            return

        QApplication.clipboard().setText(raw_data)
        self._record_support(
            SupportEventCategory.EXPORT,
            "export.raw_data_copied",
            file_type="clipboard_tsv",
            measurement_count=len(self.run_data.measurements),
            run_number=self.run_data.metadata.get("Run number"),
            unit_serial=self.run_data.metadata.get("Main board serial"),
            status="success",
        )
        self.statusBar().showMessage(
            "%d completed channel reading(s) copied to clipboard."
            % len(self.run_data.measurements)
        )

    def show_replacement_analysis(self):
        """Collect measured extra ports, calculate recommendations, and save them."""
        if self.run_data is None or not self.run_data.measurements:
            QMessageBox.information(
                self,
                "No measurements",
                "Complete or load a run before analyzing replacement ports.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Analyze replacement ports")
        dialog.setMinimumWidth(600)
        layout = QFormLayout(dialog)

        maximum_channel = max(record.channel for record in self.run_data.measurements)
        designed_count = QSpinBox()
        designed_count.setRange(1, 256)
        designed_count.setValue(maximum_channel)
        designed_count.setToolTip(
            "The number of logical channels the finished switch is designed to use."
        )
        layout.addRow("Designed channel count:", designed_count)

        minimum_improvement = QDoubleSpinBox()
        minimum_improvement.setRange(0.0, 100.0)
        minimum_improvement.setDecimals(4)
        minimum_improvement.setSingleStep(0.01)
        minimum_improvement.setValue(0.05)
        minimum_improvement.setSuffix(" dB")
        minimum_improvement.setToolTip(
            "A spare must improve the target channel's worse wavelength by at least this amount."
        )
        layout.addRow("Minimum worthwhile improvement:", minimum_improvement)

        bottom_spare_count = QSpinBox()
        bottom_spare_count.setRange(0, 20)
        bottom_spare_count.setValue(2)
        layout.addRow("Recommended designated spares:", bottom_spare_count)

        detected_extras_label = QLabel()
        detected_extras_label.setWordWrap(True)
        layout.addRow("Measured extra ports:", detected_extras_label)

        def update_detected_extras(value):
            ports = [
                record.physical_port
                if record.physical_port is not None
                else record.channel
                for record in self.run_data.measurements
                if record.channel > value
            ]
            detected_extras_label.setText(
                ", ".join(str(port) for port in sorted(ports))
                if ports
                else "None detected; analysis will be not applicable."
            )

        designed_count.valueChanged.connect(update_detected_extras)
        update_detected_extras(designed_count.value())
        layout.addRow(
            QLabel(
                "A full pass supplies these readings automatically. The minimum "
                "improvement prevents small, impractical swaps from being recommended."
            )
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        while dialog.exec_() == QDialog.Accepted:
            try:
                production_records = [
                    record
                    for record in self.run_data.measurements
                    if record.channel <= designed_count.value()
                ]
                readings = [
                    ReplacementReading(
                        record.physical_port
                        if record.physical_port is not None
                        else record.channel,
                        record.loss_1310,
                        record.loss_1550,
                    )
                    for record in self.run_data.measurements
                    if record.channel > designed_count.value()
                ]
                result = analyze_replacements(
                    production_records,
                    readings,
                    designed_count.value(),
                    self.active_limit_profile.warning_above_db
                    if self.active_limit_profile.warning_enabled
                    else self.active_limit_profile.fail_above_db,
                    minimum_improvement.value(),
                    bottom_spare_count.value(),
                    fail_limit=self.active_limit_profile.fail_above_db,
                    model=self.active_limit_profile.model,
                    too_good_limit=self.active_limit_profile.too_good_below_db,
                )
                self.apply_replacement_analysis(result)
                return
            except (OSError, ValueError, TypeError) as error:
                QMessageBox.warning(dialog, "Invalid replacement analysis", str(error))

    def apply_replacement_analysis(self, result):
        """Display calculated recommendations without storing derived results."""
        if self.run_data is None:
            return
        self.replacement_analysis = result
        self.run_data.replacement_analysis = result
        self.refresh_replacement_summary()
        self.statusBar().showMessage(
            "Replacement analysis calculated for the current run."
        )

    def refresh_coc_controls(self):
        """Enable current-run and persisted-unit outputs independently."""
        current_readings = bool(self.run_data and self.run_data.measurements)
        history_available = bool(
            self.run_data and self.run_data.measurement_attempts
        )
        self.view_history_button.setEnabled(history_available)
        persisted_readings = bool(
            current_readings
            and self.run_data is not None
            and Path(self.run_data.source_path).is_file()
        )
        if self.unit_directory is not None:
            try:
                persisted_readings = persisted_readings or bool(
                    self.unit_repository.available_run_numbers(self.unit_directory)
                )
            except OSError:
                pass
        self.write_coc_button.setEnabled(persisted_readings)
        self.copy_raw_data_button.setEnabled(current_readings)
        self.write_coc_action.setEnabled(persisted_readings)

    def show_reading_history(self):
        """Open the read-only accepted-reading history for the active run."""
        if self.run_data is None or not self.run_data.measurement_attempts:
            QMessageBox.information(
                self,
                "Reading History",
                "This run has no accepted readings to display.",
            )
            return
        dialog = ReadingHistoryDialog(self.run_data.measurement_attempts, self)
        dialog.exec_()

    def persist_run_metadata(self):
        """Save metadata changes without changing the current measurement rows."""
        if self.run_data is None:
            return
        if self.run_recorder is None:
            self.run_recorder = self.run_repository.recorder_from_existing(
                self.run_data.source_path,
                metadata=self.run_data.metadata,
                limit=self.limit_spin.value(),
                measurement_attempts=self.run_data.measurement_attempts,
                replacement_analysis=self.run_data.replacement_analysis,
                switch_test_sessions=self.run_data.switch_test_sessions,
                completed_replacements=self.completed_replacements,
            )
        else:
            self.run_recorder.metadata = dict(self.run_data.metadata)
            self.run_recorder.limit = self.limit_spin.value()
            self.run_recorder.criteria_snapshot = self.run_data.criteria_snapshot
            self.run_recorder.measurement_attempts = list(
                self.run_data.measurement_attempts
            )
            self.run_recorder.replacement_analysis = self.run_data.replacement_analysis
            self.run_recorder.completed_replacements = list(
                self.completed_replacements
            )
            self.run_recorder.switch_test_sessions = list(
                self.run_data.switch_test_sessions
            )
        self.run_recorder.save(self.run_data.measurements)
        self.persist_unit_record()

    def _coc_run_options(self):
        """Return persisted runs for the active unit, including legacy context."""
        options = []
        if self.unit_directory is not None:
            options = self.coc_workflow.available_runs(self.unit_directory)
        current_path = Path(self.run_data.source_path) if self.run_data else None
        if current_path is not None and current_path.is_file():
            known_paths = {option.source.source_path.resolve() for option in options}
            if current_path.resolve() not in known_paths:
                try:
                    source = self.coc_workflow.load_source(
                        current_path,
                        fallback_run_number=int(
                            self.run_data.metadata.get("Run number", 1)
                        ),
                    )
                except (OSError, ValueError, TypeError, KeyError):
                    source = None
                if source is not None and source.measurements:
                    options.append(CocRunOption(source))
                    options.sort(key=lambda option: option.source.run_number)
        return options

    def _default_coc_channel_count(self, options):
        part_number = self.hardware_part_number.currentText().strip()
        if not part_number and self.run_data is not None:
            part_number = self.run_data.metadata.get("Part number", "")
        inferred = infer_front_panel_channel_count(part_number)
        if inferred is not None:
            return inferred
        available = {
            record.channel
            for option in options
            for record in option.source.measurements
            if 1 <= record.channel <= 48
        }
        contiguous = 0
        while contiguous + 1 in available:
            contiguous += 1
        return contiguous or 1

    def _confirm_coc_optimization(self, result):
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Warning)
        message.setWindowTitle("COC optimization available")
        message.setText(format_optimization_warning(result))
        return_button = message.addButton("Return to Run", QMessageBox.RejectRole)
        write_button = message.addButton("Write COC Anyway", QMessageBox.AcceptRole)
        message.setDefaultButton(return_button)
        message.exec_()
        return message.clickedButton() is write_button

    def _select_coc_template(self, front_panel_channel_count):
        template = self.coc_template_path(front_panel_channel_count)
        required_capacity = 45 if front_panel_channel_count <= 45 else 48
        if template.is_file():
            try:
                capacity = self.coc_exporter.inspect_template_capacity(template)
            except (OSError, RuntimeError, ValueError):
                capacity = None
            if capacity == required_capacity:
                return template

        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select %d-channel XLSX COC template" % required_capacity,
            str(template.parent),
            "Excel workbooks (*.xlsx)",
        )
        if not selected:
            return None
        capacity = self.coc_exporter.inspect_template_capacity(selected)
        if capacity != required_capacity:
            raise ValueError(
                "The selected template supports %d channels; a %d-channel template is required."
                % (capacity, required_capacity)
            )
        self.settings.setValue(
            "coc_template_%d_path" % required_capacity,
            selected,
        )
        return Path(selected)

    def _persist_coc_export_metadata(self, base_run, metadata):
        """Persist report provenance without changing accepted measurements."""
        payload = {}
        json_path = self.run_repository.find_json_path(base_run.source_path)
        if json_path.is_file():
            try:
                payload = self.run_repository.load_json(json_path)
            except (OSError, ValueError, TypeError, KeyError):
                payload = {}
        criteria = dict(base_run.criteria or {}) or None
        warning_limit = (
            criteria.get("warning_above_db")
            if criteria and criteria.get("warning_above_db") is not None
            else criteria.get("fail_above_db", 2.5) if criteria else 2.5
        )
        recorder = self.run_repository.recorder_from_existing(
            base_run.source_path,
            metadata=metadata,
            limit=float(warning_limit),
            criteria_snapshot=criteria,
            measurement_attempts=payload.get(
                "measurement_attempts",
                payload.get("attempts", []),
            ),
            run_id=payload.get("run_id"),
            switch_test_sessions=payload.get("switch_test_sessions", []),
            completed_replacements=payload.get("completed_replacements", []),
        )
        recorder.save(list(base_run.measurements))

    def _new_coc_attempt_id(self):
        """Create a support-log correlation ID for one explicit COC attempt."""
        try:
            if self.support_logger is not None:
                return self.support_logger.new_operation_id("coc")
        except Exception:
            pass
        return "coc-" + uuid.uuid4().hex

    def _record_coc_event(
        self,
        event,
        attempt_id,
        *,
        level=SupportLogLevel.INFO,
        **fields,
    ):
        """Record a COC event with the attempt ID as its operation correlation."""
        fields["coc_attempt_id"] = attempt_id
        return self._record_support(
            SupportEventCategory.EXPORT,
            event,
            level=level,
            operation_id=attempt_id,
            **fields,
        )

    def _record_coc_terminal(self, attempt_id, outcome, stage, **fields):
        """Record the one canonical terminal outcome for a COC attempt."""
        level = (
            SupportLogLevel.ERROR
            if outcome == "failed"
            else SupportLogLevel.WARNING
            if outcome in ("blocked", "partial_success")
            else SupportLogLevel.INFO
        )
        self._record_coc_event(
            "export.coc_attempt_completed",
            attempt_id,
            level=level,
            outcome=outcome,
            failure_stage=stage,
            **fields,
        )

    @staticmethod
    def _bounded_coc_text(value, limit=3000):
        """Keep validation details useful without allowing unbounded log text."""
        return str(value or "")[:limit]

    def _coc_result_log_fields(self, result):
        """Return bounded, structured validation evidence for support logging."""
        failure_details = [
            "channel=%d,wavelength=%d,value=%.4f,run=%d,physical_port=%d"
            % (
                failure.channel,
                failure.wavelength_nm,
                failure.value_db,
                failure.source_run_number,
                failure.physical_port,
            )
            for failure in result.failures[:50]
        ]
        issues = list(result.invalid_readings) + list(result.validation_issues)
        return {
            "run_number": result.base_run_number,
            "supplemental_run_number": result.supplemental_run_number,
            "front_panel_channel_count": result.front_panel_channel_count,
            "template_capacity": result.template_capacity,
            "measurement_count": len(result.measurements),
            "missing_channels": ",".join(
                str(channel) for channel in result.missing_channels[:48]
            ),
            "failure_details": self._bounded_coc_text("; ".join(failure_details)),
            "validation_issue_codes": self._bounded_coc_text(
                ",".join(issue.code for issue in issues[:50])
            ),
            "validation_issue_details": self._bounded_coc_text(
                "; ".join(
                    "%s: %s" % (issue.code, issue.message)
                    for issue in issues[:50]
                )
            ),
        }

    def _coc_failure_message(self, stage, error):
        """Format a technician-friendly export error with technical details."""
        if isinstance(error, PermissionError):
            guidance = "Close any open workbook and verify write permissions."
        elif isinstance(error, FileNotFoundError):
            guidance = "Verify that the selected template and output folder still exist."
        elif stage == "template_selection":
            guidance = "Select a valid template with the required channel capacity."
        else:
            guidance = "Verify the template, output folder, and available disk space."
        technical_error = "%s: %s" % (type(error).__name__, error)
        return (
            "The COC operation could not continue during %s.\n\n"
            "Reason: %s\n\n"
            "Suggested action: %s\n\n"
            "Technical error: %s"
            % (stage.replace("_", " "), technical_error, guidance, technical_error)
        )

    def write_coc(self):
        """Prepare, validate, and write a complete COC from persisted runs."""
        attempt_id = self._new_coc_attempt_id()
        if self.run_data is None:
            self._record_coc_terminal(
                attempt_id,
                "blocked",
                "precondition",
                reason_code="no_run_loaded",
                reason="Load or start a run before preparing a COC.",
            )
            QMessageBox.information(self, "No run loaded", "Load or start a run first.")
            return
        try:
            options = self._coc_run_options()
        except Exception as error:
            self._record_coc_terminal(
                attempt_id,
                "failed",
                "source_discovery",
                reason_code="source_discovery_failed",
                error_type=type(error).__name__,
                error_message=str(error),
            )
            QMessageBox.critical(
                self,
                "Could not prepare COC",
                self._coc_failure_message("source_discovery", error),
            )
            return
        if not options:
            self._record_coc_terminal(
                attempt_id,
                "blocked",
                "precondition",
                reason_code="no_persisted_written_data",
                reason=(
                    "No persisted run with written readings is available "
                    "for this unit."
                ),
            )
            QMessageBox.information(
                self,
                "No written run data",
                "No persisted run with written readings is available for this unit.",
            )
            return

        self._record_coc_event(
            "export.coc_preparation_started",
            attempt_id,
            measurement_count=sum(len(option.source.measurements) for option in options),
            source_runs=",".join(
                str(option.source.run_number) for option in options[:50]
            ),
            status="started",
        )

        def prepare(base, count, supplemental):
            return self.coc_workflow.prepare(
                base,
                count,
                supplemental_run=supplemental,
                completed_replacements=self.completed_replacements,
                designated_spares=self.designated_spares,
            )

        def record_blocked_validation(result):
            self._record_coc_event(
                "export.coc_validation_blocked",
                attempt_id,
                **self._coc_result_log_fields(result),
                status="blocked",
            )

        try:
            dialog = CocExportDialog(
                options,
                prepare,
                initial_channel_count=self._default_coc_channel_count(options),
                current_run_path=self.run_data.source_path,
                validation_blocked_callback=record_blocked_validation,
                parent=self,
            )
        except Exception as error:
            self._record_coc_terminal(
                attempt_id,
                "failed",
                "preparation",
                reason_code="preparation_dialog_failed",
                error_type=type(error).__name__,
                error_message=str(error),
            )
            QMessageBox.critical(
                self,
                "Could not prepare COC",
                self._coc_failure_message("preparation", error),
            )
            return
        try:
            dialog_result = dialog.exec_()
        except Exception as error:
            self._record_coc_terminal(
                attempt_id,
                "failed",
                "preparation",
                reason_code="preparation_dialog_failed",
                error_type=type(error).__name__,
                error_message=str(error),
            )
            QMessageBox.critical(
                self,
                "Could not prepare COC",
                self._coc_failure_message("preparation", error),
            )
            return
        if dialog_result != QDialog.Accepted:
            preparation_error = getattr(dialog, "preparation_error", None)
            if preparation_error is not None:
                error = preparation_error
                self._record_coc_terminal(
                    attempt_id,
                    "failed",
                    "preparation",
                    reason_code="preparation_failed",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                QMessageBox.critical(
                    self,
                    "Could not prepare COC",
                    self._coc_failure_message("preparation", error),
                )
                return
            self._record_coc_event(
                "export.coc_preparation_canceled",
                attempt_id,
                operator_choice="cancel",
                status="canceled",
            )
            self._record_coc_terminal(
                attempt_id,
                "canceled",
                "preparation",
                reason_code="operator_canceled",
                operator_choice="cancel",
            )
            return
        result = dialog.preparation_result
        base_run = dialog.base_run
        if result is None or base_run is None:
            self._record_coc_terminal(
                attempt_id,
                "failed",
                "preparation",
                reason_code="missing_preparation_result",
            )
            QMessageBox.critical(
                self,
                "Could not prepare COC",
                (
                    "The COC preparation did not produce a complete result. "
                    "Review the saved run data and try again."
                ),
            )
            return
        if not result.eligible:
            self._record_coc_terminal(
                attempt_id,
                "blocked",
                "validation",
                reason_code="preparation_not_eligible",
                **self._coc_result_log_fields(result),
            )
            QMessageBox.warning(
                self,
                "COC cannot be written",
                "The selected COC data is not eligible for export.",
            )
            return

        if result.optimization_recommendations:
            self._record_coc_event(
                "export.coc_optimization_confirmation_shown",
                attempt_id,
                **self._coc_result_log_fields(result),
                recommendation_count=len(result.optimization_recommendations),
                status="warning",
            )
            if not self._confirm_coc_optimization(result):
                self._record_coc_event(
                    "export.coc_preparation_canceled",
                    attempt_id,
                    operator_choice="return_to_run",
                    status="canceled",
                )
                self._record_coc_terminal(
                    attempt_id,
                    "canceled",
                    "optimization_confirmation",
                    reason_code="operator_returned_to_run",
                    operator_choice="return_to_run",
                    **self._coc_result_log_fields(result),
                )
                return

        serial = str(base_run.metadata.get("Main board serial") or "").strip()
        part_number = str(base_run.metadata.get("Part number") or "").strip()
        tested_by = str(base_run.metadata.get("Tested by") or "").strip()
        if not part_number and serial:
            try:
                part_number = self.coc_exporter.find_part_number(
                    serial,
                    str(DEFAULT_PART_LOOKUP_ROOT),
                )
            except (OSError, LookupError, ValueError):
                pass

        template = None
        output_path = None
        try:
            template = self._select_coc_template(
                result.front_panel_channel_count
            )
            if template is None:
                self._record_coc_event(
                    "export.coc_preparation_canceled",
                    attempt_id,
                    operator_choice="template_selection_cancel",
                    status="canceled",
                )
                self._record_coc_terminal(
                    attempt_id,
                    "canceled",
                    "template_selection",
                    reason_code="operator_canceled_template_selection",
                    operator_choice="cancel",
                    **self._coc_result_log_fields(result),
                )
                return
            self._record_coc_event(
                "export.coc_started",
                attempt_id,
                run_number=result.base_run_number,
                measurement_count=len(result.measurements),
                destination=base_run.source_path.parent,
                template_path=template,
                front_panel_channel_count=result.front_panel_channel_count,
                template_capacity=result.template_capacity,
                supplemental_run_number=result.supplemental_run_number,
                status="started",
            )
            output_path = self.coc_exporter.export(
                template,
                base_run.source_path.parent,
                list(result.measurements),
                part_number,
                serial,
                tested_by=tested_by,
                front_panel_channel_count=result.front_panel_channel_count,
                coc_attempt_id=attempt_id,
            )
            override_text = "; ".join(
                "Channel %d = Run %d / Physical Port %d"
                % (
                    channel.record.channel,
                    channel.source_run_number,
                    channel.physical_port,
                )
                for channel in result.overridden_channels
            ) or "None"
            source_runs = ["Run %d" % result.base_run_number]
            if result.supplemental_run_number is not None:
                source_runs.append("Run %d" % result.supplemental_run_number)
            metadata = dict(base_run.metadata)
            metadata.update(
                {
                    "Part number": part_number,
                    "Main board serial": self.coc_exporter.normalise_serial(serial),
                    "Tested by": tested_by,
                    "COC output file": output_path.name,
                    "COC output path": str(output_path),
                    "COC exported at": datetime.now().isoformat(timespec="seconds"),
                    "COC template": str(template),
                    "COC front panel channels": str(result.front_panel_channel_count),
                    "COC base run": "Run %d" % result.base_run_number,
                    "COC supplemental run": (
                        "Run %d" % result.supplemental_run_number
                        if result.supplemental_run_number is not None
                        else "None"
                    ),
                    "COC source runs": ", ".join(source_runs),
                    "COC supplemental overrides": override_text,
                }
            )
            self._persist_coc_export_metadata(base_run, metadata)
            if Path(self.run_data.source_path).resolve() == base_run.source_path.resolve():
                self.run_data.metadata.update(metadata)
                if self.run_recorder is not None:
                    self.run_recorder.metadata = dict(metadata)
        except Exception as error:
            error_fields = {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "destination": output_path or base_run.source_path.parent,
                "template_path": template or "",
                "status": "error",
                **self._coc_result_log_fields(result),
            }
            if output_path is not None and Path(output_path).is_file():
                self._record_coc_event(
                    "export.coc_metadata_persistence_failed",
                    attempt_id,
                    level=SupportLogLevel.ERROR,
                    **error_fields,
                )
                self._record_coc_terminal(
                    attempt_id,
                    "partial_success",
                    "metadata_persistence",
                    reason_code="metadata_persistence_failed",
                    partial_success=True,
                    **error_fields,
                )
                QMessageBox.warning(
                    self,
                    "COC partially saved",
                    (
                        "The COC workbook was created here:\n%s\n\n"
                        "However, the COC provenance metadata could not be saved. "
                        "Keep this file and contact engineering support.\n\n"
                        "Technical error: %s"
                    ) % (output_path, error_fields["error_message"]),
                )
            else:
                self._record_coc_event(
                    "export.coc_failed",
                    attempt_id,
                    level=SupportLogLevel.ERROR,
                    **error_fields,
                )
                failure_stage = (
                    "template_selection" if template is None else "workbook_export"
                )
                self._record_coc_terminal(
                    attempt_id,
                    "failed",
                    failure_stage,
                    reason_code="coc_export_failed",
                    **error_fields,
                )
                QMessageBox.critical(
                    self,
                    "Could not write COC",
                    self._coc_failure_message(failure_stage, error),
                )
            return

        self._record_coc_terminal(
            attempt_id,
            "success",
            "completed",
            destination=output_path,
            template_path=template,
            **self._coc_result_log_fields(result),
        )
        QMessageBox.information(
            self,
            "COC written",
            "The COC was written here:\n%s" % output_path,
        )
        self.statusBar().showMessage("COC written: %s" % output_path.name)

    def set_current_reading_channel(self, channel):
        """Identify the channel associated with the displayed readings."""
        self.current_reading_channel = channel
        if channel is None:
            self.current_channel_label.setText("Channel: -")
        else:
            self.current_channel_label.setText("Channel: %d" % channel)

    def _refresh_reading_status_color(self):
        """Keep the live-reading status readable in either theme."""
        if self.current_loss_1310 is None or self.current_loss_1550 is None:
            color = "#b3bbc5" if self.dark_mode_enabled else "#587073"
        elif self.pending_reading_validation is not None and not self.pending_reading_validation.valid:
            color = "#ff8f86" if self.dark_mode_enabled else "#a33b2f"
        else:
            assessment = self._profile_for_current_run().classify(
                self.current_loss_1310, self.current_loss_1550
            )
            if assessment.is_fail:
                color = "#ff8f86" if self.dark_mode_enabled else "#a33b2f"
            else:
                color = "#72d19a" if self.dark_mode_enabled else "#28704a"
        self.reading_status_label.setStyleSheet("color: %s;" % color)

    def clear_current_reading(self, channel=None, status="No reading yet"):
        """Clear stale values while optionally showing the routed channel."""
        self.set_current_reading_channel(channel)
        self.current_loss_1310 = None
        self.current_loss_1550 = None
        self.pending_reading_validation = None
        self.demo_1310_label.setText("1310 nm: -")
        self.demo_1550_label.setText("1550 nm: -")
        self.reading_status_label.setText(status)
        self._refresh_reading_status_color()

    def refresh_current_reading(self):
        if self.current_loss_1310 is None or self.current_loss_1550 is None:
            return
        assessment = self._profile_for_current_run().classify(
            self.current_loss_1310, self.current_loss_1550
        )
        if assessment.is_fail:
            status = "FAIL at %s" % ", ".join(
                "%d nm" % wavelength for wavelength in assessment.fail_wavelengths
            )
        elif assessment.is_too_good and assessment.is_optimization:
            status = "Too good to verify; optimization warning"
        elif assessment.is_too_good:
            status = "Too good to verify"
        elif assessment.is_optimization:
            status = "Optimization warning"
        else:
            status = "Within configured limit"
        self.reading_status_label.setText(status)
        self._refresh_reading_status_color()

    def scroll_to_channel(self, channel):
        for row_index in range(self.table.rowCount()):
            item = self.table.item(row_index, 0)
            if item is not None and item.text() == str(channel):
                QTimer.singleShot(
                    0,
                    lambda target=item: self.table.scrollToItem(
                        target,
                        QAbstractItemView.PositionAtBottom,
                    ),
                )
                return

    def record_matches_filter(self, record, limit):
        """Return whether a saved record belongs in the selected table view."""
        filter_index = self.reading_filter.currentIndex()
        profile = self._profile_for_current_run()
        assessment = profile.classify(record.loss_1310, record.loss_1550)
        over_1310 = 1310 in assessment.fail_wavelengths
        over_1550 = 1550 in assessment.fail_wavelengths
        if filter_index == FILTER_WITHIN_LIMIT:
            return not over_1310 and not over_1550
        if filter_index == FILTER_ANY_OVER_LIMIT:
            return over_1310 or over_1550
        if filter_index == FILTER_1310_OVER_LIMIT:
            return over_1310
        if filter_index == FILTER_1550_OVER_LIMIT:
            return over_1550
        if filter_index == FILTER_BOTH_OVER_LIMIT:
            return over_1310 and over_1550
        return True

    def refresh_table(self):
        if self.run_data is None:
            return
        profile = self._profile_for_current_run()
        comparison_records = {}
        if self.comparison_run_data is not None:
            comparison_records = index_measurements(
                self.comparison_run_data.measurements
            )
        headers = [
            "Channel",
            "1310 nm IL (dB)",
            "1550 nm IL (dB)",
            "Status",
        ]
        if self.comparison_run_data is not None:
            run_label = (
                "Run %s"
                % (
                    self.comparison_run_number
                    if self.comparison_run_number is not None
                    else "comparison"
                )
            )
            headers.extend(
                [
                    "%s 1310 nm IL (dB)" % run_label,
                    "%s 1550 nm IL (dB)" % run_label,
                ]
            )
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        records = list(self.run_data.measurements)
        pending_channel = self.hardware_pending_channel
        records = [
            record
            for record in records
            if record.channel == pending_channel
            or self.record_matches_filter(record, profile.fail_above_db)
        ]
        if pending_channel is not None and all(
            record.channel != pending_channel for record in records
        ):
            records.append(MeasurementRecord(pending_channel, 0.0, 0.0))
        self.displayed_records = records
        self.table.setRowCount(len(records))
        for row_index, record in enumerate(records):
            is_pending = record.channel == self.hardware_pending_channel
            comparison_display_values = comparison_values(
                comparison_records,
                record.channel,
            )
            if is_pending:
                values = [str(record.channel), "-", "-", "Taking measurement"]
                values.extend(comparison_display_values)
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 0:
                        item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row_index, column, item)
                continue
            assessment = profile.classify(record.loss_1310, record.loss_1550)
            flagged = assessment.is_fail
            status_parts = []
            if assessment.is_fail:
                status_parts.append(
                    "FAIL at " + ", ".join("%d nm" % wavelength for wavelength in assessment.fail_wavelengths)
                )
            if assessment.is_too_good:
                status_parts.append("Too good to verify")
            if assessment.is_optimization and not assessment.is_fail:
                status_parts.append("Optimization warning")
            status = "; ".join(status_parts) if status_parts else "Within configured limit"
            values = [
                str(record.channel),
                "%.4f" % record.loss_1310,
                "%.4f" % record.loss_1550,
                status,
            ]
            values.extend(comparison_display_values)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                if flagged and column < 4:
                    item.setBackground(DARK_DANGER if self.dark_mode_enabled else DANGER)
                    if self.dark_mode_enabled:
                        item.setForeground(DARK_DANGER_TEXT)
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()

    def select_over_limit(self):
        if self.run_data is None:
            return
        profile = self._profile_for_current_run()
        self.reading_filter.setCurrentIndex(FILTER_ANY_OVER_LIMIT)
        self.table.clearSelection()
        selected = 0
        for row_index, record in enumerate(self.displayed_records):
            if (
                record.channel != self.hardware_pending_channel
                and profile.classify(record.loss_1310, record.loss_1550).is_fail
            ):
                index = self.table.model().index(row_index, 0)
                self.table.selectionModel().select(
                    index,
                    QItemSelectionModel.Select | QItemSelectionModel.Rows,
                )
                selected += 1
        self.statusBar().showMessage(
            "%d failed channel(s) selected for retest." % selected
        )

    def _show_degraded_logging_warning(self):
        if self.support_logger is None:
            return
        status = self.support_logger.status()
        if not status.fallback_active:
            return
        self.statusBar().showMessage(
            "Support logging is degraded. Testing can continue; see Help > "
            "Support Logs > Logging Status for details.",
            12000,
        )

    def _warn_if_support_logs_exceed_limit(self):
        """Ask the operator to archive or delete logs without auto-deleting."""
        if self.support_logger is None or self._support_log_size_warning_shown:
            return
        status = self.support_logger.status()
        if not status.over_size_limit:
            return
        self._support_log_size_warning_shown = True
        QMessageBox.warning(
            self,
            "Support logs exceed 500 MB",
            "The Light Workbench support logs now exceed 500 MB.\n\n"
            "Logs are retained indefinitely. Please use Open Logs Folder or "
            "Export Support Bundle to archive the logs, then delete older log "
            "files when appropriate.",
        )

    def _support_log_folder(self):
        if self.support_logger is None:
            return DEFAULT_PATHS.support_log_root
        status = self.support_logger.status()
        return Path(status.active_folder)

    def open_support_logs_folder(self):
        folder = self._support_log_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.warning(
                self,
                "Support Logs",
                "The support log folder could not be created:\n%s" % error,
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            QMessageBox.warning(
                self,
                "Support Logs",
                "The support log folder could not be opened:\n%s" % folder,
            )
            return
        self._record_support(
            SupportEventCategory.OPERATOR,
            "support_logs.folder_opened",
            destination=folder,
            status="success",
        )

    def copy_support_logs_path(self):
        folder = self._support_log_folder()
        QApplication.clipboard().setText(str(folder))
        self.statusBar().showMessage("Support logs folder path copied.", 5000)
        self._record_support(
            SupportEventCategory.OPERATOR,
            "support_logs.path_copied",
            destination=folder,
            status="success",
        )

    def show_logging_status(self):
        if self.support_logger is None:
            QMessageBox.information(
                self,
                "Support Logging Status",
                "Support logging was not initialized for this application session.",
            )
            return
        LoggingStatusDialog(self.support_logger.status(), self).exec_()

    def export_support_bundle_dialog(self):
        if self.support_logger is None:
            QMessageBox.warning(
                self,
                "Export Support Bundle",
                "Support logging is not available in this session.",
            )
            return
        dialog = SupportBundleDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        suggested = "LightWorkbench-Support-%s.zip" % datetime.now().strftime(
            "%Y%m%d-%H%M%S"
        )
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Support Bundle",
            str(Path.home() / "Documents" / suggested),
            "ZIP archives (*.zip)",
        )
        if not selected:
            return
        self.support_logger.flush(2.0)
        try:
            try:
                dependency_report = collect_dependency_report().as_text()
            except Exception as error:
                dependency_report = "Dependency report unavailable: %s" % error
            status = self.support_logger.status()
            result = export_support_bundle(
                selected,
                log_root=status.active_folder,
                start_date=dialog.start_date,
                end_date=dialog.end_date,
                application_name=APP_NAME,
                application_version=APP_VERSION,
                dependency_report=dependency_report,
                configuration_summary={
                    "application_version": APP_VERSION,
                    "dark_mode": bool(self.dark_mode_enabled),
                    "live_write_mode": bool(self.live_write_mode_enabled),
                    "run_root": str(DEFAULT_RUN_ROOT),
                    "support_log_root": status.active_folder,
                    "support_log_fallback_active": status.fallback_active,
                },
            )
        except Exception as error:
            self._record_support(
                SupportEventCategory.EXPORT,
                "export.support_bundle_failed",
                level=SupportLogLevel.ERROR,
                error_type=type(error).__name__,
                error_message=str(error),
                status="error",
            )
            QMessageBox.critical(self, "Export Support Bundle", str(error))
            return
        self._record_support(
            SupportEventCategory.EXPORT,
            "export.support_bundle_completed",
            destination=result.path,
            selected_start_date=dialog.start_date.isoformat(),
            selected_end_date=dialog.end_date.isoformat(),
            file_count=result.included_file_count,
            status="success",
        )
        QMessageBox.information(
            self,
            "Support Bundle Exported",
            "The support bundle was written here:\n%s" % result.path,
        )


def main():
    support_logger = SupportLoggingService.create_default()
    set_support_logging_service(support_logger)
    install_exception_hooks(support_logger)
    support_logger.record(
        SupportEventCategory.APPLICATION,
        "application.started",
        application_name=APP_NAME,
        details="Support logging initialized.",
        status="started",
    )
    app = QApplication(sys.argv)
    icon_path = bundled_asset_path(NORMAL_BRANDING_ASSET)
    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))
    if "--check-dependencies" in sys.argv[1:]:
        dialog = DependencyCheckDialog(collect_dependency_report())
        dialog.show()
        try:
            return app.exec_()
        finally:
            support_logger.shutdown()
            set_support_logging_service(None)
    window = MainWindow(
        sys.argv[1] if len(sys.argv) > 1 else None,
        support_logger=support_logger,
    )
    window.show()
    try:
        return app.exec_()
    finally:
        support_logger.shutdown()
        set_support_logging_service(None)


if __name__ == "__main__":
    raise SystemExit(main())
