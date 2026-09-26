"""PyQt5 desktop viewer for insertion-loss run data."""

import sys
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
from application.live_controller import LiveILReadingController
from application.hardware_planning import parse_hardware_channels
from application.hardware_session import HardwareRunSession
from application.run_start import (
    build_hardware_run_request,
    prepare_hardware_run,
)
from domain.measurement import calculate_insertion_loss
from domain.comparison import comparison_values, index_measurements
from domain.raw_export import format_raw_measurements
from domain.timing import SwitchTestTimer
from hardware.factory import HardwareFactory
from infrastructure.coc_exporter import (
    COC_TEMPLATE_FILENAME,
    DEFAULT_PART_LOOKUP_ROOT,
    FileCocExporter,
)
from infrastructure.run_repository import DEFAULT_RUN_ROOT, FileRunRepository
from infrastructure.unit_repository import FileUnitRepository
from hardware.optical_switch import OSX150
from hardware.power_meter import SantecPowerMeter, SimulatedPowerMeter
from run_data import MeasurementRecord, RunData
from domain.replacements import (
    ReplacementReading,
    analyze_replacements,
    normalise_completed_replacements,
    recommendation_category,
)
from tools.dependency_check import DependencyReport, collect_dependency_report
from ui.red_light_test import RedLightTestDialog
from config.app_info import APP_NAME, APP_TAGLINE, APP_VERSION, about_text
from ui.live_il_reading import LiveILReadingDialog, LiveILReadingWorker


ACCENT = "#e60013"
DANGER = QColor("#ffe1dc")
DEFAULT_READ_SHORTCUT = "Return"
KEYPAD_ENTER_SHORTCUT = "Enter"
FILTER_ALL = 0
FILTER_WITHIN_LIMIT = 1
FILTER_ANY_OVER_LIMIT = 2
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
    """Edit the physical-port replacements that were actually performed."""

    def __init__(
        self,
        records=None,
        recommendations=None,
        designated_spares=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Record Replaced Ports")
        self.setMinimumSize(650, 450)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Current Port", "Replacement Port"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Record the physical port swaps that were actually completed. "
                "Recommendations are pre-filled when available."
            )
        )
        layout.addWidget(self.table, 1)

        row_buttons = QHBoxLayout()
        add_button = QPushButton("Add Replacement")
        add_button.clicked.connect(self.add_row)
        row_buttons.addWidget(add_button)
        remove_button = QPushButton("Remove Selected")
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

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept_records)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        initial_records = list(records or [])
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

    def add_row(self, record=None):
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

    def remove_selected_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _records_from_table(self):
        records = []
        for row in range(self.table.rowCount()):
            values = [
                self.table.cellWidget(row, column).value()
                for column in range(self.table.columnCount())
            ]
            if not any(values):
                continue
            if not all(values):
                raise ValueError(
                    "Complete both fields in each replacement row, "
                    "or remove the blank row."
                )
            records.append(
                {
                    "current_port": values[0],
                    "replacement_port": values[1],
                }
            )
        return normalise_completed_replacements(records)

    def accept_records(self):
        try:
            self.records = self._records_from_table()
            self.designated_spares = self._spares_from_edit()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid replacement or spare record", str(error))
            return
        self.accept()

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

    def __init__(self, initial_path: str | None = None):
        super().__init__()
        self.run_data: RunData | None = None
        # Keep adapter selection in one composition point. Passing the module
        # aliases preserves the existing test seam while allowing future
        # workstation-specific hardware configurations.
        self.hardware_factory = HardwareFactory(
            power_meter_factory=SantecPowerMeter,
            switch_factory=OSX150,
        )
        self.coc_exporter = FileCocExporter()
        self.run_repository = FileRunRepository()
        self.unit_repository = FileUnitRepository()
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
        # Noah Mode is deliberately session-only and defaults off. Live Write
        # Mode is also session-only, but is the normal first-launch workflow.
        self.noah_mode_enabled = False
        self.live_write_mode_enabled = True
        self.reference_progress = None
        self.run_recorder = None
        self.unit_directory = None
        self.unit_record = {}
        self.replacement_analysis = None
        self.completed_replacements = []
        self.designated_spares = []
        self.hardware_session = HardwareRunSession()
        self.switch_test_timer = None
        self.displayed_records = []
        self.comparison_run_data = None
        self.comparison_run_number = None
        self.settings = QSettings("Light Workbench", "LightWorkbench")
        self._migrate_legacy_settings()
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
        self._connect_hardware_controller()
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
        self.hardware_controller.progress_changed.connect(
            self.hardware_progress_changed
        )
        self.hardware_controller.completed.connect(self.hardware_completed)
        self.hardware_controller.stopped.connect(self.hardware_stopped)
        self.hardware_controller.failed.connect(self.hardware_failed)
        self.hardware_controller.thread_finished.connect(
            self.hardware_thread_finished
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

        tools_menu = self.menuBar().addMenu("Tools")
        dependency_action = QAction("Check Dependencies...", self)
        dependency_action.triggered.connect(self.show_dependency_check)
        tools_menu.addAction(dependency_action)
        red_light_action = QAction("Red Light Test...", self)
        red_light_action.triggered.connect(self.show_red_light_test)
        tools_menu.addAction(red_light_action)
        live_il_action = QAction("Live IL Reading...", self)
        live_il_action.triggered.connect(self.show_live_il_reading)
        tools_menu.addAction(live_il_action)
        self.noah_mode_action = QAction("Noah Mode", self)
        self.noah_mode_action.setCheckable(True)
        self.noah_mode_action.setChecked(False)
        self.noah_mode_action.triggered.connect(self.toggle_noah_mode)
        tools_menu.addAction(self.noah_mode_action)
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
        self.logo_label.setToolTip("Lulu - CandC")
        logo_roots = [Path(__file__).resolve().parent]
        if getattr(sys, "_MEIPASS", None):
            logo_roots.insert(0, Path(sys._MEIPASS))
        logo_path = next(
            (
                root_path / "assets" / "Lulu - CandC.png"
                for root_path in logo_roots
                if (root_path / "assets" / "Lulu - CandC.png").is_file()
            ),
            None,
        )
        if logo_path:
            logo = QPixmap(str(logo_path))
            self.logo_label.setPixmap(
                logo.scaled(132, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self.logo_label.setMaximumSize(140, 56)
            header.addWidget(self.logo_label)
        else:
            self.logo_label.hide()
        header.addLayout(titles)
        header.addStretch()
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
        hardware_setup_layout.addWidget(QLabel("Tested by:"), 6, 0)
        self.hardware_tested_by = QLineEdit()
        self.hardware_tested_by.setPlaceholderText("Initials")
        self.hardware_tested_by.setMaximumWidth(90)
        self.hardware_tested_by.setToolTip(
            "Enter the operator's initials. They are saved with the run and COC."
        )
        hardware_setup_layout.addWidget(self.hardware_tested_by, 6, 1)
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
        self.update_channel_mode_controls(self.hardware_channel_mode.currentIndex())
        setup_row.addWidget(hardware_setup_box, 1)

        controls_box = QGroupBox("Hardware controls")
        controls_layout = QVBoxLayout(controls_box)
        controls_layout.setSpacing(8)

        run_controls_layout = QHBoxLayout()
        self.start_hardware_button = QPushButton("Start Run")
        self.start_hardware_button.setObjectName("hardware_primary_control")
        self.start_hardware_button.setToolTip("Start a real OP815 and OSX-150 hardware run.")
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
        analysis_layout.addWidget(QLabel("Warning limit:"), 0, 0)
        self.limit_spin = QDoubleSpinBox()
        self.limit_spin.setRange(-100.0, 100.0)
        self.limit_spin.setDecimals(4)
        self.limit_spin.setSingleStep(0.1)
        self.limit_spin.setValue(2.0)
        self.limit_spin.setSuffix(" dB")
        self.limit_spin.valueChanged.connect(self.refresh_analysis)
        analysis_layout.addWidget(self.limit_spin, 0, 1)
        self.select_over_limit_button = QPushButton("Select Over-Limit")
        self.select_over_limit_button.clicked.connect(self.select_over_limit)
        analysis_layout.addWidget(self.select_over_limit_button, 0, 2)
        self.metric_labels = {}
        for row, (key, display) in enumerate(
            (
                ("total", "Total channels"),
                ("over_limit", "Over-limit channels"),
                ("over_1310", "1310 nm over"),
                ("over_1550", "1550 nm over"),
                ("over_both", "Both wavelengths over"),
            ),
            start=1,
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
        self.record_replacements_button = QPushButton("Record Replaced Ports...")
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
        self.statusBar().showMessage("Ready. Open a saved CSV run to begin.")

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

    def toggle_noah_mode(self, enabled):
        """Enable one-step read-and-save behavior for hardware IL runs."""
        enabled = bool(enabled)
        if self.hardware_run_active:
            self.noah_mode_action.setChecked(self.noah_mode_enabled)
            self.statusBar().showMessage(
                "Noah Mode cannot be changed during an active hardware run."
            )
            return
        if enabled and self.live_write_mode_enabled:
            self.noah_mode_action.setChecked(False)
            QMessageBox.warning(
                self,
                "Noah Mode unavailable",
                "Turn off Live Write Mode before enabling Noah Mode.",
            )
            return

        if enabled:
            confirmation = QMessageBox.question(
                self,
                "Enable Noah Mode?",
                "Each successful IL reading will be written to the run "
                "immediately, without a review or reread step first. "
                "You can repeat a channel later, but its new reading will "
                "replace the current table value.\n\n"
                "Noah Mode will turn off when Light Workbench closes.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirmation != QMessageBox.Yes:
                self.noah_mode_action.setChecked(False)
                return

        self.noah_mode_enabled = enabled
        self._apply_noah_mode_controls()
        self.statusBar().showMessage(
            "Noah Mode enabled: successful readings save automatically."
            if enabled
            else "Noah Mode disabled: Read IL and Write IL are separate steps."
        )

    def _apply_noah_mode_controls(self):
        """Update button and shortcut labels for the current session mode."""
        if hasattr(self, "noah_mode_action"):
            self.noah_mode_action.setChecked(self.noah_mode_enabled)
        if hasattr(self, "live_write_mode_action"):
            self.live_write_mode_action.setChecked(self.live_write_mode_enabled)
        if hasattr(self, "continue_hardware_button"):
            if self.noah_mode_enabled:
                title = "Read & Write IL"
            elif self.live_write_mode_enabled:
                title = "Live Reading"
            else:
                title = "Read IL"
            self.continue_hardware_button.title_label.setText(title)
            self.continue_hardware_button.setAccessibleName(title)
            self.continue_hardware_button.setToolTip(
                "Read both wavelengths and save the result automatically."
                if self.noah_mode_enabled
                else (
                    "Start continuous IL updates for the current channel; "
                    "updates begin automatically when the channel is routed. "
                    "Use Write IL when the reading is ready."
                    if self.live_write_mode_enabled
                    else "Read both wavelengths for the current channel."
                )
            )
        if hasattr(self, "write_shortcut") and self.write_shortcut is not None:
            self.write_shortcut.setEnabled(not self.noah_mode_enabled)
        if self.noah_mode_enabled and hasattr(self, "write_hardware_button"):
            self.write_hardware_button.setEnabled(False)

    def toggle_live_write_mode(self, enabled):
        """Enable continuous IL updates until the operator writes a reading."""
        enabled = bool(enabled)
        if self.hardware_run_active:
            self.live_write_mode_action.setChecked(self.live_write_mode_enabled)
            self.statusBar().showMessage(
                "Live Write Mode cannot be changed during an active hardware run."
            )
            return
        if enabled and self.noah_mode_enabled:
            self.live_write_mode_action.setChecked(False)
            QMessageBox.warning(
                self,
                "Live Write Mode unavailable",
                "Turn off Noah Mode before enabling Live Write Mode.",
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
        self._apply_noah_mode_controls()
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
        RedLightTestDialog(
            self,
            switch_factory=self.hardware_factory.create_switch,
        ).exec_()

    def show_live_il_reading(self):
        """Open the meter-only live IL reader without touching run data."""
        if self.hardware_run_active:
            QMessageBox.warning(
                self,
                "Hardware run active",
                "Stop the current hardware run before starting a Live IL Reading.",
            )
            return
        dialog = LiveILReadingDialog(
            self,
            reference_1310=self.reference_1310_spin.value(),
            reference_1550=self.reference_1550_spin.value(),
            meter_factory=self.hardware_factory.create_power_meter,
        )
        self.reference_values_changed.connect(dialog.set_reference_values)
        dialog.references_changed.connect(self.set_reference_values)
        dialog.exec_()

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

        meter = None
        try:
            meter = self.hardware_factory.create_power_meter()
            if not meter.find_devices():
                meter.close()
                QMessageBox.warning(
                    self,
                    "ILM/OP815 not detected",
                    "Connect and power on the ILM/OP815, then try Calculate "
                    "Reference again.",
                )
                return
        except Exception as error:
            if meter is not None:
                try:
                    meter.close()
                except Exception:
                    pass
            QMessageBox.warning(
                self,
                "ILM/OP815 unavailable",
                "Light Workbench could not check the ILM/OP815:\n%s" % error,
            )
            return

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
            self._close_reference_progress()
            self.calculate_reference_button.setEnabled(True)
            QMessageBox.critical(self, "Reference calculation", str(error))

    def _reference_meter_connected(self, _description):
        """Start the offset measurement after the meter connection succeeds."""
        self.reference_controller.calculate_reference()

    def _reference_calculation_ready(self, reference_1310, reference_1550):
        self.set_reference_values(reference_1310, reference_1550)
        self.statusBar().showMessage(
            "Reference calculated. ILM disconnected.",
            5000,
        )
        self._finish_reference_calculation()

    def _reference_calculation_failed(self, message):
        if self.reference_worker is None:
            return
        self._finish_reference_calculation()
        QMessageBox.critical(self, "Reference calculation failed", message)

    def _finish_reference_calculation(self):
        """Stop the temporary meter worker and close its progress popup."""
        self.reference_controller.stop_and_wait()
        self._close_reference_progress()
        self.calculate_reference_button.setEnabled(True)

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
        current = self.coc_template_path()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select XLSX COC template",
            str(current.parent),
            "Excel workbooks (*.xlsx)",
        )
        if selected:
            self.settings.setValue("coc_template_path", selected)
            self.statusBar().showMessage("COC template selected: %s" % selected)

    def lookup_part_number(self):
        serial = self.hardware_main_board_serial.text().strip()
        lookup_root = str(DEFAULT_PART_LOOKUP_ROOT)
        try:
            part_number = self.coc_exporter.find_part_number(serial, lookup_root)
        except (OSError, LookupError, ValueError) as error:
            QMessageBox.warning(self, "Part number lookup", str(error))
            return

        self.hardware_part_number.setCurrentText(part_number)
        self.metadata_labels["Part number"].setText(part_number)
        if self.run_data is not None:
            self.run_data.metadata["Part number"] = part_number
        self.statusBar().showMessage(
            "Part number found for Main Board serial %s."
            % self.coc_exporter.normalise_serial(serial)
        )

    def coc_template_path(self):
        configured = self.settings.value("coc_template_path", "")
        if configured and Path(configured).is_file():
            return Path(configured)

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
        for root in roots:
            candidate = root / "Templates" / COC_TEMPLATE_FILENAME
            if candidate.is_file():
                return candidate
        return roots[0] / "Templates" / COC_TEMPLATE_FILENAME

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
            self.completed_replacements = []
            self.designated_spares = []
            self.refresh_comparison_runs()
            return
        try:
            self.unit_record = self.unit_repository.load_record(unit_directory)
        except (OSError, ValueError, TypeError, KeyError):
            self.unit_record = {}
        self.completed_replacements = list(
            self.unit_record.get("completed_replacements", [])
        )
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
        if (
            self.unit_directory is None
            or self.run_data is None
            or self.run_recorder is None
            or not self.run_data.measurements
        ):
            return
        try:
            run_number = int(self.run_data.metadata.get("Run number", 1))
        except (TypeError, ValueError):
            run_number = 1
        self.unit_repository.save_record(
            self.unit_directory,
            self._unit_metadata(self.run_data.metadata),
            self.completed_replacements,
            self.designated_spares,
            run_number,
            self.run_recorder.directory,
            switch_serial=self.run_data.metadata.get("Switch serial", ""),
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
        json_path = self.run_repository.find_json_path(path)
        if json_path.is_file():
            try:
                payload = self.run_repository.load_json(json_path)
                completed_replacements = payload.get("completed_replacements", [])
                legacy_replacements = normalise_completed_replacements(
                    completed_replacements
                    if isinstance(completed_replacements, list)
                    else []
                )
                if self.unit_directory is None and legacy_replacements:
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
                if physical_ports:
                    run_data.measurements = [
                        MeasurementRecord(
                            record.channel,
                            record.loss_1310,
                            record.loss_1550,
                            physical_ports.get(record.channel),
                        )
                        for record in run_data.measurements
                    ]
                run_data.warning_limit = float(payload["warning_limit_db"])
                self.limit_spin.setValue(run_data.warning_limit)
            except (OSError, ValueError, TypeError, KeyError):
                self.statusBar().showMessage(
                    "Loaded CSV; the companion run.json could not be read."
                )
        self.run_recorder = self.run_repository.recorder_from_existing(
            path,
            metadata=run_data.metadata,
            limit=self.limit_spin.value(),
            attempts=run_data.attempts,
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
        self.run_data.measurements = [
            existing
            for existing in self.run_data.measurements
            if existing.channel != self.demo_channel
        ]
        self.run_data.measurements.append(record)
        self.run_data.measurements.sort(key=lambda existing: existing.channel)
        if self.run_recorder is not None:
            self.run_recorder.save(self.run_data.measurements)
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
            self.run_data.measurements = [
                existing
                for existing in self.run_data.measurements
                if existing.channel != channel
            ]
            self.run_data.measurements.append(record)
            self.run_data.measurements.sort(key=lambda existing: existing.channel)
            if self.run_recorder is not None:
                self.run_recorder.save(self.run_data.measurements)
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
                        attempts=self.run_data.attempts,
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
        if not retest and not self.confirm_hardware_setup_complete():
            return
        confirmation = QMessageBox.question(
            self,
            "Start real hardware run",
            "This will connect to the OP815 and OSX-150 and move the switch. "
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

        # Preserve the previous preflight behavior: driver construction must
        # succeed before the in-memory run/timing state is initialized.
        try:
            meter = self.hardware_factory.create_power_meter()
            switch = self.hardware_factory.create_switch()
        except (RuntimeError, OSError) as error:
            QMessageBox.critical(self, "Hardware unavailable", str(error))
            return

        self.hardware_session.begin(
            retest=retest,
            plan=preparation.plan,
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
            )
            self._load_unit_state(selected_unit_directory)
            self.run_recorder = self.run_repository.new_recorder(
                metadata=self.run_data.metadata,
                limit=self.limit_spin.value(),
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
                    attempts=self.run_data.attempts,
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
                1310: self.reference_1310_spin.value(),
                1550: self.reference_1550_spin.value(),
            },
            existing_channels=(
                [record.channel for record in self.run_data.measurements]
                if continuing_existing
                else None
            ),
            resume_existing=continuing_existing,
            live_write_mode=self.live_write_mode_enabled,
        )
        try:
            self.hardware_controller.start(request)
        except (RuntimeError, OSError) as error:
            QMessageBox.critical(self, "Hardware unavailable", str(error))
            return
        self.hardware_thread = self.hardware_controller.thread
        self.hardware_worker = self.hardware_controller.worker
        self.noah_mode_action.setEnabled(False)
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

    def confirm_hardware_setup_complete(self):
        """Validate setup metadata and references before connecting hardware."""
        missing_metadata = []
        if not self.hardware_part_number.currentText().strip():
            missing_metadata.append("Part number")
        if not self.hardware_main_board_serial.text().strip():
            missing_metadata.append("Main board serial")
        if not self.hardware_switch_serial.text().strip():
            missing_metadata.append("Switch serial")
        if not self.hardware_tested_by.text().strip():
            missing_metadata.append("Tested by")
        if (
            self.hardware_channel_mode.currentIndex() == 2
            and not self.hardware_channel_ranges.text().strip()
        ):
            missing_metadata.append("Channels/ranges")

        if missing_metadata:
            choice = QMessageBox(self)
            choice.setWindowTitle("Hardware test setup incomplete")
            choice.setText("Hardware test setup is incomplete.")
            choice.setInformativeText(
                "Missing: %s\n\n"
                "Return to Hardware test setup to complete these fields, "
                "or continue without saving this metadata?"
                % ", ".join(missing_metadata)
            )
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
                return False

        if (
            self.reference_1310_spin.value() == 0.00
            and self.reference_1550_spin.value() == 0.00
        ):
            choice = QMessageBox(self)
            choice.setWindowTitle("Reference values are zero")
            choice.setText(
                "Please make sure to calculate or enter reference values for "
                "1310 nm and 1550 nm wavelengths."
            )
            choice.setInformativeText(
                "Also, don't try to tell me they're actually 0 because I "
                "don't believe you."
            )
            return_button = choice.addButton(
                "Return to Setup",
                QMessageBox.RejectRole,
            )
            continue_button = choice.addButton(
                "Continue Anyways",
                QMessageBox.AcceptRole,
            )
            choice.setDefaultButton(return_button)
            choice.exec_()
            if choice.clickedButton() != continue_button:
                return False

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
        self._hardware_command("change_channel", channel, resume_interrupted)

    def hardware_operator_required(self, channel, physical_port):
        self.hardware_session.set_pending_channel(channel, physical_port)
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
                self._hardware_command("continue_current")
            else:
                self._hardware_command("read_current")

    def write_hardware(self):
        if self.noah_mode_enabled:
            return
        self._commit_and_advance_hardware()

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
            if self.noah_mode_enabled:
                self.continue_hardware_button.setEnabled(True)
            else:
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
        record = MeasurementRecord(
            channel,
            loss_1310,
            loss_1550,
            physical_port,
        )
        updated_measurements = [
            existing
            for existing in self.run_data.measurements
            if existing.channel != channel
        ]
        updated_measurements.append(record)
        updated_measurements.sort(key=lambda existing: existing.channel)
        if self.run_recorder is not None:
            self.run_recorder.save(updated_measurements)
        self.run_data.measurements = updated_measurements
        self.hardware_session.clear_pending()
        self.refresh_analysis()
        self.scroll_to_channel(channel)
        return True

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
        self.write_shortcut.setEnabled(not self.noah_mode_enabled)
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
        self._apply_noah_mode_controls()

    def hardware_reading_ready(self, channel, _physical_port, loss_1310, loss_1550):
        self.hardware_session.set_pending_reading(
            channel,
            _physical_port,
            loss_1310,
            loss_1550,
        )
        self.set_current_reading_channel(channel)
        self.current_loss_1310 = loss_1310
        self.current_loss_1550 = loss_1550
        self.refresh_current_reading()
        self.demo_1310_label.setText("1310 nm: %.4f dB" % loss_1310)
        self.demo_1550_label.setText("1550 nm: %.4f dB" % loss_1550)
        self.continue_hardware_button.setEnabled(not self.live_write_mode_enabled)
        self.write_hardware_button.setEnabled(not self.noah_mode_enabled)
        self.change_hardware_channel_button.setEnabled(True)
        self.hardware_live_indicator.setVisible(self.live_write_mode_enabled)
        self.demo_channel_label.setText(
            (
                "Channel %d measured - saving automatically" % channel
                if self.noah_mode_enabled
                else (
                    "Channel %d live reading - write when ready" % channel
                    if self.live_write_mode_enabled
                    else "Channel %d measured - read again or write values" % channel
                )
            )
        )
        self.refresh_table()
        # In Live Write Mode the table may receive many readings before the
        # operator accepts one. Keep the operator's current scroll position
        # until Write IL commits the pending reading.
        if not self.live_write_mode_enabled:
            self.scroll_to_channel(channel)
        if self.noah_mode_enabled:
            self._commit_and_advance_hardware()

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
        self.finish_switch_test_session()
        self.hardware_live_indicator.setVisible(False)
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(False)
        self.retest_button.setEnabled(True)
        self.statusBar().showMessage("Hardware run complete. CSV and JSON are saved.")
        QTimer.singleShot(0, self.offer_coc_export)

    def hardware_stopped(self):
        self.finish_switch_test_session()
        self.hardware_live_indicator.setVisible(False)
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(False)
        self.retest_button.setEnabled(bool(self.run_data and self.run_data.measurements))
        self.statusBar().showMessage("Hardware run stopped. Completed readings remain visible.")
        QTimer.singleShot(0, self.offer_coc_export)

    def hardware_failed(self, message):
        self.finish_switch_test_session()
        self.hardware_live_indicator.setVisible(False)
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(False)
        QMessageBox.critical(self, "Hardware run stopped", message)
        QTimer.singleShot(0, self.offer_coc_export)

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
        if finished_thread is not None:
            finished_thread.deleteLater()
        self.start_hardware_button.setEnabled(True)
        self.noah_mode_action.setEnabled(True)
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
        if self.reference_worker is not None and self.reference_thread is not None:
            self._finish_reference_calculation()
        if self.hardware_run_active:
            if self.hardware_controller.is_active:
                self.hardware_controller.stop_and_wait()
            elif self.hardware_worker is not None and self.hardware_thread is not None:
                self.hardware_worker.stop()
                self.hardware_thread.quit()
                self.hardware_thread.wait(5000)
            self.finish_switch_test_session()
        event.accept()

    def refresh_analysis(self):
        if self.run_data is None:
            return
        if self.run_recorder is not None and self.run_data.measurements:
            self.run_recorder.limit = self.limit_spin.value()
            self.run_recorder.save(self.run_data.measurements)
            self.persist_unit_record()
        summary = self.run_data.analysis(self.limit_spin.value())
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
        self.record_replacements_button.setEnabled(has_measurements)
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
            if recommendation_category(item, result["warning_limit_db"]) == "required"
        ]
        optional_recommendations = [
            item
            for item in recommendations
            if recommendation_category(item, result["warning_limit_db"]) == "optional"
        ]
        spare_ports = [
            str(spare["physical_port"])
            for spare in result.get("bottom_spares", [])
        ]
        lines = [
            "Required replacements: %d" % len(required_recommendations),
            "Optional Replacements: %d" % len(optional_recommendations),
            "Recommended designated spares: %s"
            % (", ".join(spare_ports) if spare_ports else "none"),
        ]
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
        """Record the physical-port replacements completed by the operator."""
        if self.run_data is None or not self.run_data.measurements:
            QMessageBox.information(
                self,
                "No measurements",
                "Complete or load a run before recording replaced ports.",
            )
            return

        # A legacy timestamped CSV has no unit.json beside it. Establish the
        # shared unit context before opening the dialog so its existing device
        # replacements and spares can still be reused for future runs.
        self.ensure_unit_state_for_current_fields()

        recommendations = []
        if self.replacement_analysis:
            recommendations = self.replacement_analysis.get("recommendations", [])
        dialog = CompletedReplacementDialog(
            self.completed_replacements,
            recommendations,
            self.designated_spares,
            self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        self.completed_replacements = list(dialog.records)
        self.designated_spares = list(dialog.designated_spares)
        self.run_data.completed_replacements = list(self.completed_replacements)
        self.persist_unit_record()
        self.refresh_replacement_summary()
        self.statusBar().showMessage(
            "Completed replacements and designated spares saved to the unit record."
        )

    def copy_replacement_notes(self):
        """Copy completed physical-port swaps for pasting into Unit Editor."""
        if not self.completed_replacements:
            return
        notes = "Port replacements completed:\n" + "\n".join(
            "%d \u2192 %d"
            % (record["current_port"], record["replacement_port"])
            for record in self.completed_replacements
        )
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
                    self.limit_spin.value(),
                    minimum_improvement.value(),
                    bottom_spare_count.value(),
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
        """Enable run-data outputs whenever completed readings are available."""
        enabled = bool(self.run_data and self.run_data.measurements)
        self.write_coc_button.setEnabled(enabled)
        self.copy_raw_data_button.setEnabled(enabled)
        self.write_coc_action.setEnabled(enabled)

    def offer_coc_export(self):
        """Ask whether the current run should be copied into the COC template."""
        if self.run_data is None or not self.run_data.measurements:
            return
        answer = QMessageBox.question(
            self,
            "Write to COC?",
            "Write the current readings to a COC workbook now?\n"
            "Missing channel readings will remain blank.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            self.write_coc()

    def persist_run_metadata(self):
        """Save metadata changes without changing the current measurement rows."""
        if self.run_data is None:
            return
        if self.run_recorder is None:
            self.run_recorder = self.run_repository.recorder_from_existing(
                self.run_data.source_path,
                metadata=self.run_data.metadata,
                limit=self.limit_spin.value(),
                attempts=self.run_data.attempts,
                replacement_analysis=self.run_data.replacement_analysis,
                switch_test_sessions=self.run_data.switch_test_sessions,
                completed_replacements=self.completed_replacements,
            )
        else:
            self.run_recorder.metadata = dict(self.run_data.metadata)
            self.run_recorder.limit = self.limit_spin.value()
            self.run_recorder.attempts = list(self.run_data.attempts)
            self.run_recorder.replacement_analysis = self.run_data.replacement_analysis
            self.run_recorder.completed_replacements = list(
                self.completed_replacements
            )
            self.run_recorder.switch_test_sessions = list(
                self.run_data.switch_test_sessions
            )
        self.run_recorder.save(self.run_data.measurements)
        self.persist_unit_record()

    def write_coc(self):
        """Write the current partial or complete run to a copied XLSX template."""
        if self.run_data is None:
            QMessageBox.information(self, "No run loaded", "Load or start a run first.")
            return

        serial = self.hardware_main_board_serial.text().strip()
        if not serial:
            serial = self.run_data.metadata.get("Main board serial", "").strip()
        part_number = self.hardware_part_number.currentText().strip()
        tested_by = self.hardware_tested_by.text().strip()
        if not part_number:
            part_number = self.run_data.metadata.get("Part number", "").strip()
        if not part_number and serial:
            lookup_root = str(DEFAULT_PART_LOOKUP_ROOT)
            try:
                part_number = self.coc_exporter.find_part_number(serial, lookup_root)
                self.hardware_part_number.setCurrentText(part_number)
            except (OSError, LookupError, ValueError):
                pass

        template = self.coc_template_path()
        if not template.is_file():
            selected, _ = QFileDialog.getOpenFileName(
                self,
                "Select XLSX COC template",
                str(template.parent),
                "Excel workbooks (*.xlsx)",
            )
            if not selected:
                return
            template = Path(selected)
            self.settings.setValue("coc_template_path", str(template))

        try:
            output_path = self.coc_exporter.export(
                template,
                self.run_data.source_path.parent,
                self.run_data.measurements,
                part_number,
                serial,
                tested_by=tested_by,
            )
            self.run_data.metadata.update(
                {
                    "Part number": part_number,
                    "Main board serial": self.coc_exporter.normalise_serial(serial),
                    "Tested by": tested_by,
                    "COC output file": output_path.name,
                    "COC output path": str(output_path),
                    "COC exported at": datetime.now().isoformat(timespec="seconds"),
                    "COC template": str(template),
                }
            )
            self.hardware_part_number.setCurrentText(part_number)
            self.hardware_main_board_serial.setText(
                self.coc_exporter.normalise_serial(serial)
            )
            self.metadata_labels["Part number"].setText(part_number)
            self.metadata_labels["Main board serial"].setText(
                self.coc_exporter.normalise_serial(serial)
            )
            self.metadata_labels["Tested by"].setText(tested_by or "Not recorded")
            self.persist_run_metadata()
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            QMessageBox.critical(self, "Could not write COC", str(error))
            return

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
        else:
            limit = self.limit_spin.value()
            over_limit = (
                self.current_loss_1310 > limit or self.current_loss_1550 > limit
            )
            if over_limit:
                color = "#ff8f86" if self.dark_mode_enabled else "#a33b2f"
            else:
                color = "#72d19a" if self.dark_mode_enabled else "#28704a"
        self.reading_status_label.setStyleSheet("color: %s;" % color)

    def clear_current_reading(self, channel=None, status="No reading yet"):
        """Clear stale values while optionally showing the routed channel."""
        self.set_current_reading_channel(channel)
        self.current_loss_1310 = None
        self.current_loss_1550 = None
        self.demo_1310_label.setText("1310 nm: -")
        self.demo_1550_label.setText("1550 nm: -")
        self.reading_status_label.setText(status)
        self._refresh_reading_status_color()

    def refresh_current_reading(self):
        if self.current_loss_1310 is None or self.current_loss_1550 is None:
            return
        limit = self.limit_spin.value()
        flagged_1310 = self.current_loss_1310 > limit
        flagged_1550 = self.current_loss_1550 > limit
        if flagged_1310 and flagged_1550:
            status = "OVER LIMIT at both wavelengths"
        elif flagged_1310:
            status = "OVER LIMIT at 1310 nm"
        elif flagged_1550:
            status = "OVER LIMIT at 1550 nm"
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
        over_1310 = record.loss_1310 > limit
        over_1550 = record.loss_1550 > limit
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
        limit = self.limit_spin.value()
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
            or self.record_matches_filter(record, limit)
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
            flagged_1310 = record.loss_1310 > limit
            flagged_1550 = record.loss_1550 > limit
            flagged = flagged_1310 or flagged_1550
            if flagged_1310 and flagged_1550:
                status = "Both wavelengths over"
            elif flagged_1310:
                status = "1310 nm over"
            elif flagged_1550:
                status = "1550 nm over"
            else:
                status = "Within limit"
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
        limit = self.limit_spin.value()
        self.reading_filter.setCurrentIndex(FILTER_ANY_OVER_LIMIT)
        self.table.clearSelection()
        selected = 0
        for row_index, record in enumerate(self.displayed_records):
            if (
                record.channel != self.hardware_pending_channel
                and (record.loss_1310 > limit or record.loss_1550 > limit)
            ):
                index = self.table.model().index(row_index, 0)
                self.table.selectionModel().select(
                    index,
                    QItemSelectionModel.Select | QItemSelectionModel.Rows,
                )
                selected += 1
        self.statusBar().showMessage(
            "%d over-limit channel(s) selected for retest." % selected
        )


def main():
    app = QApplication(sys.argv)
    icon_roots = [Path(__file__).resolve().parent]
    if getattr(sys, "_MEIPASS", None):
        icon_roots.insert(0, Path(sys._MEIPASS))
    icon_path = next(
        (
            root_path / "assets" / "Lulu - C&C-white_square.ico"
            for root_path in icon_roots
            if (root_path / "assets" / "Lulu - C&C-white_square.ico").is_file()
        ),
        None,
    )
    if icon_path:
        app.setWindowIcon(QIcon(str(icon_path)))
    if "--check-dependencies" in sys.argv[1:]:
        dialog = DependencyCheckDialog(collect_dependency_report())
        dialog.show()
        return app.exec_()
    window = MainWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
