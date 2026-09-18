"""PyQt5 desktop viewer for insertion-loss run data."""

import sys
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import (
    QItemSelectionModel,
    QMetaObject,
    QSettings,
    QThread,
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
)

from measurement_worker import MeasurementWorker
from osx150_driver import OSX150
from power_meter import SantecPowerMeter, SimulatedPowerMeter
from run_persistence import (
    DEFAULT_RUN_ROOT,
    RunRecorder,
    find_run_json_path,
    load_run_json,
)
from run_data import MeasurementRecord, RunData, load_run_csv
from replacement_analysis import (
    ReplacementReading,
    analyze_replacements,
    replacement_metadata,
)
from coc_export import (
    COC_TEMPLATE_FILENAME,
    DEFAULT_PART_LOOKUP_ROOT,
    export_coc,
    find_part_number,
    normalise_serial,
)
from dependency_check import DependencyReport, collect_dependency_report
from red_light_test import RedLightTestDialog
from app_info import APP_NAME, APP_TAGLINE, APP_VERSION, about_text
from live_il_reading import LiveILReadingDialog, LiveILReadingWorker
from switch_timing import SwitchTestTimer


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


def parse_hardware_channels(value):
    """Expand positive channel numbers and inclusive ranges in entered order."""
    if not value.strip():
        raise ValueError("Enter at least one channel or range.")
    channels = []
    seen = set()
    for entry in value.split(","):
        entry = entry.strip()
        if not entry:
            raise ValueError("Empty entries are not allowed between commas.")
        if "-" in entry:
            parts = entry.split("-")
            if len(parts) != 2:
                raise ValueError("Invalid range %r." % entry)
            try:
                first, last = (int(part.strip()) for part in parts)
            except ValueError:
                raise ValueError("Range ends must be numeric: %s" % entry)
            if first < 1 or first > last:
                raise ValueError("Invalid range %r." % entry)
            candidates = range(first, last + 1)
        else:
            try:
                candidates = (int(entry),)
            except ValueError:
                raise ValueError("Invalid channel %r." % entry)
        for channel in candidates:
            if channel < 1:
                raise ValueError("Channels must be 1 or greater.")
            if channel not in seen:
                channels.append(channel)
                seen.add(channel)
    return channels


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
        summary.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: %s;"
            % ("#e60013" if report.overall_status == "ACTION REQUIRED" else "#164e6b")
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
            "font-size: 24px; font-weight: 800; color: #e60013;"
        )
        layout.addWidget(title)

        self.tagline_label = QLabel(APP_TAGLINE)
        self.tagline_label.setAlignment(Qt.AlignCenter)
        self.tagline_label.setStyleSheet(
            "font-size: 13px; font-style: italic; color: #164e6b;"
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
        self.demo_meter: SimulatedPowerMeter | None = None
        self.demo_channel = 0
        self.demo_measurement = None
        self.current_loss_1310 = None
        self.current_loss_1550 = None
        self.current_reading_channel = None
        self.hardware_thread = None
        self.hardware_worker = None
        self.reference_thread = None
        self.reference_worker = None
        self.reference_progress = None
        self.run_recorder = None
        self.replacement_analysis = None
        self.hardware_retest = False
        self.hardware_pending_reading = None
        self.hardware_pending_channel = None
        self.hardware_pending_physical_port = None
        self.hardware_manual_channel_order = False
        self.hardware_full_pass = False
        self.hardware_configured_channel_count = None
        self.switch_test_timer = None
        self.displayed_records = []
        self.settings = QSettings("Light Workbench", "LightWorkbench")
        self._migrate_legacy_settings()
        self.continue_shortcut = None
        self.keypad_enter_shortcut = None
        self.retest_shortcut = None
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 720)
        self._build_ui()
        if initial_path:
            self.load_path(Path(initial_path))

    def _build_ui(self):
        self.setStyleSheet(
            """
            QMainWindow { background: #eceff1; }
            QWidget#central_widget { background: #eceff1; }
            QGroupBox { background: #f7f8f9; font-weight: 600; border: 1px solid #c7cdd1; border-radius: 6px; margin-top: 12px; padding: 12px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #e60013; }
            QPushButton { background: #e60013; color: white; border: none; border-radius: 4px; padding: 8px 14px; font-weight: 600; }
            QPushButton:hover { background: #b80010; }
            QPushButton:disabled { background: #8b000b; color: #f3c7ca; }
            QPushButton#primary_action { padding: 11px 20px; font-size: 14px; font-weight: 800; }
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
            QLabel#button_title { color: white; font-size: 14px; font-weight: 800; }
            QLabel#button_shortcut { color: #ffe8e8; font-size: 8px; font-weight: 500; }
            """
        )

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

        lookup_folder_action = QAction("Part Number Lookup Folder...", self)
        lookup_folder_action.triggered.connect(self.choose_part_lookup_folder)
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
        hardware_setup_layout = QGridLayout(hardware_setup_box)
        hardware_setup_layout.addWidget(QLabel("Channel mode:"), 0, 0)
        self.hardware_channel_mode = QComboBox()
        self.hardware_channel_mode.addItems(["Full configured pass", "Single channel", "Specific channels/ranges"])
        self.hardware_channel_mode.currentIndexChanged.connect(
            self.update_channel_mode_controls
        )
        hardware_setup_layout.addWidget(self.hardware_channel_mode, 0, 1)
        self.hardware_channel_label = QLabel("Channel:")
        hardware_setup_layout.addWidget(self.hardware_channel_label, 0, 2)
        self.hardware_single_channel = QSpinBox()
        self.hardware_single_channel.setRange(1, 256)
        self.hardware_single_channel.setValue(1)
        hardware_setup_layout.addWidget(self.hardware_single_channel, 0, 3)
        self.hardware_channel_ranges_label = QLabel("Channels/ranges:")
        hardware_setup_layout.addWidget(self.hardware_channel_ranges_label, 1, 0)
        self.hardware_channel_ranges = QLineEdit()
        self.hardware_channel_ranges.setPlaceholderText("Example: 1, 9, 10-15, 27")
        hardware_setup_layout.addWidget(self.hardware_channel_ranges, 1, 1, 1, 3)
        hardware_setup_layout.addWidget(QLabel("Part number:"), 2, 0)
        self.hardware_part_number = QLineEdit()
        self.hardware_part_number.setPlaceholderText("Lookup or enter part number")
        hardware_setup_layout.addWidget(self.hardware_part_number, 2, 1)
        self.lookup_part_number_button = QPushButton("Lookup Part Number")
        self.lookup_part_number_button.clicked.connect(self.lookup_part_number)
        hardware_setup_layout.addWidget(self.lookup_part_number_button, 2, 2, 1, 2)
        hardware_setup_layout.addWidget(QLabel("Main board serial:"), 3, 0)
        self.hardware_main_board_serial = QLineEdit()
        hardware_setup_layout.addWidget(self.hardware_main_board_serial, 3, 1)
        hardware_setup_layout.addWidget(QLabel("Switch serial:"), 3, 2)
        self.hardware_switch_serial = QLineEdit()
        hardware_setup_layout.addWidget(self.hardware_switch_serial, 3, 3)
        hardware_setup_layout.addWidget(QLabel("Operating band:"), 4, 0)
        self.hardware_operating_band = QLineEdit("O band")
        hardware_setup_layout.addWidget(self.hardware_operating_band, 4, 1)
        hardware_setup_layout.addWidget(QLabel("1310 ref:"), 4, 2)
        self.reference_1310_spin = QDoubleSpinBox()
        self.reference_1310_spin.setRange(-100.0, 100.0)
        self.reference_1310_spin.setDecimals(2)
        self.reference_1310_spin.setSingleStep(0.01)
        self.reference_1310_spin.setValue(0.00)
        self.reference_1310_spin.setSuffix(" dBm")
        hardware_setup_layout.addWidget(self.reference_1310_spin, 4, 3)
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
        self.manual_channel_order_checkbox = QCheckBox(
            "Choose channel order manually"
        )
        self.manual_channel_order_checkbox.setToolTip(
            "Optional full-pass mode for scattered channels; repeated channels "
            "replace their previous saved result."
        )
        hardware_setup_layout.addWidget(
            self.manual_channel_order_checkbox,
            6,
            0,
            1,
            4,
        )
        self.update_channel_mode_controls(self.hardware_channel_mode.currentIndex())
        setup_row.addWidget(hardware_setup_box, 1)

        controls_box = QGroupBox("Hardware controls")
        controls_layout = QVBoxLayout(controls_box)
        controls_layout.setSpacing(8)

        run_controls_layout = QHBoxLayout()
        self.start_hardware_button = QPushButton("Start Run")
        self.start_hardware_button.setToolTip("Start a real OP815 and OSX-150 hardware run.")
        self.start_hardware_button.clicked.connect(self.start_hardware)
        run_controls_layout.addWidget(self.start_hardware_button)
        self.stop_hardware_button = QPushButton("Stop run")
        self.stop_hardware_button.setToolTip("Stop the hardware run and keep completed readings.")
        self.stop_hardware_button.setEnabled(False)
        self.stop_hardware_button.clicked.connect(self.stop_hardware)
        run_controls_layout.addWidget(self.stop_hardware_button)
        controls_layout.addLayout(run_controls_layout)

        measurement_controls_layout = QHBoxLayout()
        self.continue_hardware_button = ShortcutButton("Read IL")
        self.continue_hardware_button.setToolTip("Read both wavelengths for the current channel.")
        self.continue_hardware_button.setObjectName("primary_action")
        self.continue_hardware_button.setEnabled(False)
        self.continue_hardware_button.clicked.connect(self.continue_hardware)
        measurement_controls_layout.addWidget(self.continue_hardware_button)
        self.write_hardware_button = ShortcutButton("Write IL")
        self.write_hardware_button.setToolTip("Accept and save the current IL reading.")
        self.write_hardware_button.setObjectName("primary_action")
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
        controls_layout.addWidget(self.change_hardware_channel_button)

        self.retest_button = QPushButton("Retest selected")
        self.retest_button.setToolTip("Retest the selected completed channels.")
        self.retest_button.setEnabled(False)
        self.retest_button.clicked.connect(self.retest_selected)
        controls_layout.addWidget(self.retest_button)
        self.demo_channel_label = QLabel("No hardware run active")
        self.demo_channel_label.setWordWrap(True)
        # Retain the internal status target for existing run updates, but keep
        # it out of the hardware-controls layout so the controls stay compact.
        self.demo_channel_label.setVisible(False)
        self.write_coc_button = QPushButton("Write COC...")
        self.write_coc_button.setToolTip("Write the current run to a copied XLSX COC template.")
        self.write_coc_button.clicked.connect(self.write_coc)
        self.write_coc_button.setEnabled(False)
        controls_layout.addWidget(self.write_coc_button)
        for button in (
            self.start_hardware_button,
            self.continue_hardware_button,
            self.write_hardware_button,
            self.change_hardware_channel_button,
            self.stop_hardware_button,
            self.retest_button,
            self.write_coc_button,
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
        self.demo_1310_label = QLabel("1310 nm: -")
        self.demo_1310_label.setObjectName("reading")
        self.demo_1550_label = QLabel("1550 nm: -")
        self.demo_1550_label.setObjectName("reading")
        self.reading_status_label = QLabel("No reading yet")
        self.reading_status_label.setObjectName("reading_status")
        readings_layout.addWidget(self.current_channel_label)
        readings_layout.addWidget(self.demo_1310_label)
        readings_layout.addWidget(self.demo_1550_label)
        readings_layout.addWidget(self.reading_status_label)
        setup_row.addWidget(readings_box)
        root.addLayout(setup_row)

        content_splitter = QSplitter(Qt.Horizontal)
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
        replacement_layout.addWidget(self.replacement_summary_label)
        replacement_layout.addWidget(self.replacement_analysis_button)
        info_layout.addWidget(replacement_box)

        metadata_box = QGroupBox("Run information")
        metadata_layout = QFormLayout(metadata_box)
        self.metadata_labels = {}
        for key in ("Part number", "Main board serial", "Switch serial", "Operating band", "Retest attempts", "Source file"):
            label = QLabel("-")
            label.setWordWrap(True)
            self.metadata_labels[key] = label
            metadata_layout.addRow(key + ":", label)
        info_layout.addWidget(metadata_box)
        info_layout.addStretch()
        content_splitter.addWidget(info_panel)
        content_splitter.setSizes([820, 320])
        root.addWidget(content_splitter, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready. Open a saved CSV run to begin.")

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
            "part_lookup_root",
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

    def show_red_light_test(self):
        """Open the red-light test setup without connecting automatically."""
        if self.hardware_thread is not None:
            QMessageBox.warning(
                self,
                "Hardware run active",
                "Stop the current hardware run before opening a Red Light Test.",
            )
            return
        RedLightTestDialog(self).exec_()

    def show_live_il_reading(self):
        """Open the meter-only live IL reader without touching run data."""
        if self.hardware_thread is not None:
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
        if self.hardware_thread is not None:
            QMessageBox.warning(
                self,
                "Hardware run active",
                "Stop the current hardware run before calculating a reference.",
            )
            return
        if self.reference_thread is not None:
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
            meter = SantecPowerMeter()
            thread = QThread(self)
            worker = LiveILReadingWorker(meter)
            worker.moveToThread(thread)
            thread.started.connect(worker.start)
            worker.connected.connect(self._reference_meter_connected)
            worker.reference_ready.connect(self._reference_calculation_ready)
            worker.failed.connect(self._reference_calculation_failed)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            self.reference_thread = thread
            self.reference_worker = worker
            thread.start()
        except Exception as error:
            self.reference_thread = None
            self.reference_worker = None
            self._close_reference_progress()
            self.calculate_reference_button.setEnabled(True)
            QMessageBox.critical(self, "Reference calculation", str(error))

    def _reference_meter_connected(self, _description):
        """Start the offset measurement after the meter connection succeeds."""
        if self.reference_worker is not None:
            QMetaObject.invokeMethod(
                self.reference_worker,
                "calculate_reference",
                Qt.QueuedConnection,
            )

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
        worker = self.reference_worker
        thread = self.reference_thread
        if worker is not None and thread is not None:
            if thread.isRunning():
                QMetaObject.invokeMethod(worker, "stop", Qt.BlockingQueuedConnection)
                thread.quit()
                thread.wait(5000)
            else:
                worker.stop()
        self.reference_worker = None
        self.reference_thread = None
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

    def choose_part_lookup_folder(self):
        current = self.settings.value(
            "part_lookup_root",
            str(DEFAULT_PART_LOOKUP_ROOT),
        )
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select part-number lookup folder",
            str(current),
        )
        if selected:
            self.settings.setValue("part_lookup_root", selected)
            self.statusBar().showMessage(
                "Part-number lookup folder set to %s" % selected
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
        lookup_root = self.settings.value(
            "part_lookup_root",
            str(DEFAULT_PART_LOOKUP_ROOT),
        )
        try:
            part_number = find_part_number(serial, lookup_root)
        except (OSError, LookupError, ValueError) as error:
            QMessageBox.warning(self, "Part number lookup", str(error))
            return

        self.hardware_part_number.setText(part_number)
        self.metadata_labels["Part number"].setText(part_number)
        if self.run_data is not None:
            self.run_data.metadata["Part number"] = part_number
        self.statusBar().showMessage(
            "Part number found for Main Board serial %s." % normalise_serial(serial)
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

    def load_path(self, path: Path):
        try:
            run_data = load_run_csv(path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Could not open run", str(error))
            return

        self.run_data = run_data
        self.run_recorder = None
        self.replacement_analysis = None
        self.switch_test_timer = None
        self.clear_current_reading()
        self.file_label.setText(str(path))
        self.metadata_labels["Source file"].setText(path.name)
        self.hardware_part_number.setText(run_data.metadata.get("Part number", ""))
        self.hardware_main_board_serial.setText(
            run_data.metadata.get("Main board serial", "")
        )
        self.hardware_switch_serial.setText(
            run_data.metadata.get(
                "Switch serial",
                run_data.metadata.get("Switch serial (last 5 digits)", ""),
            )
        )
        self.metadata_labels["Part number"].setText(
            run_data.metadata.get("Part number", "Not recorded")
        )
        for key in ("Main board serial", "Switch serial", "Operating band"):
            value = run_data.metadata.get(key)
            if value is None and key == "Switch serial":
                value = run_data.metadata.get("Switch serial (last 5 digits)")
            self.metadata_labels[key].setText(value or "Not recorded")
        self.metadata_labels["Retest attempts"].setText("Not recorded")
        json_path = find_run_json_path(path)
        if json_path.is_file():
            try:
                payload = load_run_json(json_path)
                run_data.attempts = payload.get("attempts", [])
                run_data.replacement_analysis = payload.get("replacement_analysis")
                switch_test_sessions = payload.get("switch_test_sessions", [])
                run_data.switch_test_sessions = (
                    switch_test_sessions
                    if isinstance(switch_test_sessions, list)
                    else []
                )
                self.replacement_analysis = run_data.replacement_analysis
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
                retest_count = sum(
                    bool(attempt.get("retest")) for attempt in run_data.attempts
                )
                self.metadata_labels["Retest attempts"].setText(str(retest_count))
            except (OSError, ValueError, TypeError, KeyError):
                self.statusBar().showMessage(
                    "Loaded CSV; the companion run.json could not be read."
                )
        for metadata_key, reference_spin in (
            ("1310 reference dBm", self.reference_1310_spin),
            ("1550 reference dBm", self.reference_1550_spin),
        ):
            try:
                if metadata_key in run_data.metadata:
                    reference_spin.setValue(float(run_data.metadata[metadata_key]))
            except (TypeError, ValueError):
                pass
        self.run_recorder = RunRecorder.from_existing(
            path,
            metadata=run_data.metadata,
            limit=self.limit_spin.value(),
            attempts=run_data.attempts,
            replacement_analysis=run_data.replacement_analysis,
            switch_test_sessions=run_data.switch_test_sessions,
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
                "Mode": "Simulation",
                "1310 reference dBm": "%.2f" % reference_1310,
                "1550 reference dBm": "%.2f" % reference_1550,
            },
        )
        self.run_recorder = RunRecorder(
            metadata={
                "Operating band": "O band",
                "Mode": "Simulation",
                "1310 reference dBm": "%.2f" % reference_1310,
                "1550 reference dBm": "%.2f" % reference_1550,
            },
            limit=self.limit_spin.value(),
        )
        self.replacement_analysis = None
        self.run_data.replacement_analysis = None
        self.switch_test_timer = None
        self.run_data.source_path = self.run_recorder.csv_path
        self.file_label.setText(str(self.run_recorder.csv_path))
        self.metadata_labels["Main board serial"].setText("SIMULATED")
        self.metadata_labels["Switch serial"].setText("SIMULATED")
        self.metadata_labels["Operating band"].setText("O band")
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
        self.demo_measurement = {
            1310: self.reference_1310_spin.value() - measurements[1310],
            1550: self.reference_1550_spin.value() - measurements[1550],
        }
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
            self.run_recorder.record_attempt(
                self.demo_channel,
                self.demo_measurement[1310],
                self.demo_measurement[1550],
                self.demo_channel,
                retest=False,
            )
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
        if self.hardware_thread is not None or self.run_data is None:
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
                self.run_recorder.record_attempt(
                    channel,
                    record.loss_1310,
                    record.loss_1550,
                    channel,
                    retest=True,
                )
                self.run_recorder.save(self.run_data.measurements)
            self.demo_measurement = None
        self.refresh_analysis()
        self.retest_button.setEnabled(True)
        self.statusBar().showMessage("Selected simulation channels retested and saved.")

    def choose_hardware_run_mode(self):
        """Ask whether Start Run should continue or replace the loaded run."""
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
            "Part number": self.hardware_part_number.text().strip(),
            "Main board serial": self.hardware_main_board_serial.text().strip(),
            "Switch serial": self.hardware_switch_serial.text().strip(),
        }

    def _restore_hardware_identity(self, metadata):
        """Restore loaded identity values after declining an update."""
        self.hardware_part_number.setText(metadata.get("Part number", ""))
        self.hardware_main_board_serial.setText(
            metadata.get("Main board serial", "")
        )
        self.hardware_switch_serial.setText(
            metadata.get(
                "Switch serial",
                metadata.get("Switch serial (last 5 digits)", ""),
            )
        )

    def confirm_existing_run_identity(self):
        """Offer to update a loaded run's identity before continuing it."""
        if self.run_data is None:
            return True

        saved_identity = {
            key: self.run_data.metadata.get(key, "")
            for key in ("Part number", "Main board serial", "Switch serial")
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

        rename_files = QMessageBox.question(
            self,
            "Rename run files?",
            "Rename the run folder, CSV, JSON, and COC workbook to match the "
            "updated serial numbers?\n\n"
            "The original run timestamp will be preserved.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        new_metadata = dict(self.run_data.metadata)
        new_metadata.update(current_identity)
        try:
            if rename_files == QMessageBox.Yes:
                if self.run_recorder is None:
                    self.run_recorder = RunRecorder.from_existing(
                        self.run_data.source_path,
                        metadata=self.run_data.metadata,
                        limit=self.limit_spin.value(),
                        attempts=self.run_data.attempts,
                        replacement_analysis=self.run_data.replacement_analysis,
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
        if rename_files == QMessageBox.Yes:
            self.persist_run_metadata()
        self.statusBar().showMessage("Loaded run information updated.")
        return True

    def start_hardware(self, channels=None, retest=False):
        if self.hardware_thread is not None:
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

        manual_channel_order = False
        full_pass = False
        continuing_existing = run_mode == "continue"
        if not retest:
            try:
                if self.hardware_channel_mode.currentIndex() == 0:
                    channels = None
                    full_pass = True
                    manual_channel_order = (
                        self.manual_channel_order_checkbox.isChecked()
                    )
                elif self.hardware_channel_mode.currentIndex() == 1:
                    channels = [self.hardware_single_channel.value()]
                else:
                    channels = parse_hardware_channels(
                        self.hardware_channel_ranges.text()
                    )
            except ValueError as error:
                QMessageBox.warning(self, "Invalid channel selection", str(error))
                return

        try:
            meter = SantecPowerMeter()
            switch = OSX150()
        except (RuntimeError, OSError) as error:
            QMessageBox.critical(self, "Hardware unavailable", str(error))
            return

        self.hardware_retest = retest
        self.hardware_manual_channel_order = manual_channel_order
        self.hardware_full_pass = full_pass
        self.hardware_configured_channel_count = None
        if not retest and run_mode == "new":
            self.run_data = RunData(
                Path("Hardware run"),
                [],
                {
                    "Mode": "Real hardware",
                    "Part number": self.hardware_part_number.text().strip(),
                    "Main board serial": self.hardware_main_board_serial.text().strip(),
                    "Switch serial": self.hardware_switch_serial.text().strip(),
                    "Operating band": self.hardware_operating_band.text().strip() or "O band",
                    "1310 reference dBm": "%.2f" % self.reference_1310_spin.value(),
                    "1550 reference dBm": "%.2f" % self.reference_1550_spin.value(),
                },
            )
            self.run_recorder = RunRecorder(
                metadata=self.run_data.metadata,
                limit=self.limit_spin.value(),
            )
            self.switch_test_timer = SwitchTestTimer(
                self.run_data.metadata,
                self.run_data.switch_test_sessions,
            )
            self.replacement_analysis = None
            self.run_data.replacement_analysis = None
            self.run_data.source_path = self.run_recorder.csv_path
        elif not retest:
            if self.run_recorder is None:
                self.run_recorder = RunRecorder.from_existing(
                    self.run_data.source_path,
                    metadata=self.run_data.metadata,
                    limit=self.limit_spin.value(),
                    attempts=self.run_data.attempts,
                    replacement_analysis=self.run_data.replacement_analysis,
                    switch_test_sessions=self.run_data.switch_test_sessions,
                )
            self.run_data.source_path = self.run_recorder.csv_path
            self.replacement_analysis = self.run_data.replacement_analysis

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
        self.refresh_analysis()

        self.hardware_thread = QThread(self)
        self.hardware_worker = MeasurementWorker(
            meter,
            switch,
            channels,
            {
                1310: self.reference_1310_spin.value(),
                1550: self.reference_1550_spin.value(),
            },
            manual_channel_order=manual_channel_order,
            existing_channels=(
                [record.channel for record in self.run_data.measurements]
                if continuing_existing
                else None
            ),
            resume_existing=continuing_existing,
            resume_full_pass=(
                continuing_existing and full_pass and not manual_channel_order
            ),
        )
        self.hardware_worker.moveToThread(self.hardware_thread)
        self.hardware_thread.started.connect(self.hardware_worker.run)
        self.hardware_worker.channel_selection_required.connect(
            self.hardware_channel_selection_required
        )
        self.hardware_worker.continuation_selection_required.connect(
            self.hardware_continuation_selection_required
        )
        self.hardware_worker.channel_configuration_ready.connect(
            self.hardware_channel_configuration_ready
        )
        self.hardware_worker.operator_required.connect(self.hardware_operator_required)
        self.hardware_worker.reading_ready.connect(self.hardware_reading_ready)
        self.hardware_worker.progress_changed.connect(self.hardware_progress_changed)
        self.hardware_worker.completed.connect(self.hardware_completed)
        self.hardware_worker.stopped.connect(self.hardware_stopped)
        self.hardware_worker.failed.connect(self.hardware_failed)
        self.hardware_worker.completed.connect(self.hardware_thread.quit)
        self.hardware_worker.stopped.connect(self.hardware_thread.quit)
        self.hardware_worker.failed.connect(self.hardware_thread.quit)
        self.hardware_thread.finished.connect(self.hardware_thread_finished)
        self.start_hardware_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(True)
        self.set_open_csv_available(False)
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.retest_button.setEnabled(False)
        self.statusBar().showMessage("Starting hardware run...")
        self.begin_switch_test_session()
        self.hardware_thread.start()

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
        self.hardware_configured_channel_count = int(channel_count)

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
            self.hardware_worker.select_resume_channel(channel)
        else:
            self.hardware_worker.stop()

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
            self.hardware_worker.select_next_channel(channel)
        elif completed_count >= channel_count:
            self.hardware_worker.finish_manual_pass()
        else:
            self.hardware_worker.stop()

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

        self.hardware_pending_reading = None
        self.hardware_pending_channel = None
        self.hardware_pending_physical_port = None
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.clear_current_reading(channel, "Changing to channel %d..." % channel)
        self.refresh_table()
        self.demo_channel_label.setText(
            "Changing to channel %d without stopping the run" % channel
        )
        self.hardware_worker.change_channel(channel, resume_interrupted)

    def hardware_operator_required(self, channel, physical_port):
        self.hardware_pending_channel = channel
        self.hardware_pending_physical_port = physical_port
        self.hardware_pending_reading = None
        self.clear_current_reading(channel, "Move cable, then read values")
        self.continue_hardware_button.setEnabled(True)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(True)
        self.refresh_table()
        self.demo_channel_label.setText(
            "Channel %d routed to physical port %d - move cable, then read"
            % (channel, physical_port)
        )

    def continue_hardware(self):
        if self.hardware_worker is not None:
            self.continue_hardware_button.setEnabled(False)
            self.change_hardware_channel_button.setEnabled(False)
            if self.hardware_pending_reading is None:
                self.hardware_worker.continue_current()
            else:
                self.hardware_worker.read_current()

    def write_hardware(self):
        if self.hardware_worker is not None and self.hardware_pending_reading is not None:
            self.commit_hardware_reading()
            self.write_hardware_button.setEnabled(False)
            self.change_hardware_channel_button.setEnabled(False)
            self.hardware_worker.write_current()

    def commit_hardware_reading(self):
        channel, physical_port, loss_1310, loss_1550 = self.hardware_pending_reading
        if self.run_data is None:
            return
        already_recorded = any(
            existing.channel == channel for existing in self.run_data.measurements
        )
        record = MeasurementRecord(
            channel,
            loss_1310,
            loss_1550,
            physical_port,
        )
        self.run_data.measurements = [
            existing
            for existing in self.run_data.measurements
            if existing.channel != channel
        ]
        self.run_data.measurements.append(record)
        self.run_data.measurements.sort(key=lambda existing: existing.channel)
        if self.run_recorder is not None:
            self.run_recorder.record_attempt(
                channel,
                loss_1310,
                loss_1550,
                physical_port,
                retest=self.hardware_retest or already_recorded,
            )
            self.run_recorder.save(self.run_data.measurements)
        self.hardware_pending_reading = None
        self.hardware_pending_channel = None
        self.hardware_pending_physical_port = None
        self.refresh_analysis()
        self.scroll_to_channel(channel)

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

    def hardware_reading_ready(self, channel, _physical_port, loss_1310, loss_1550):
        self.hardware_pending_reading = (
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
        self.continue_hardware_button.setEnabled(True)
        self.write_hardware_button.setEnabled(True)
        self.change_hardware_channel_button.setEnabled(True)
        self.demo_channel_label.setText(
            "Channel %d measured - read again or write values" % channel
        )
        self.refresh_table()
        self.scroll_to_channel(channel)

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
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(False)
        self.retest_button.setEnabled(True)
        self.statusBar().showMessage("Hardware run complete. CSV and JSON are saved.")
        QTimer.singleShot(0, self.offer_coc_export)

    def hardware_stopped(self):
        self.finish_switch_test_session()
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(False)
        self.retest_button.setEnabled(bool(self.run_data and self.run_data.measurements))
        self.statusBar().showMessage("Hardware run stopped. Completed readings remain visible.")
        QTimer.singleShot(0, self.offer_coc_export)

    def hardware_failed(self, message):
        self.finish_switch_test_session()
        self.continue_hardware_button.setEnabled(False)
        self.write_hardware_button.setEnabled(False)
        self.change_hardware_channel_button.setEnabled(False)
        self.stop_hardware_button.setEnabled(False)
        QMessageBox.critical(self, "Hardware run stopped", message)
        QTimer.singleShot(0, self.offer_coc_export)

    def stop_hardware(self):
        if self.hardware_worker is not None:
            self.hardware_worker.stop()

    def hardware_thread_finished(self):
        # This is a fallback for shutdown paths where the worker's queued
        # stopped/failed signal cannot be delivered before the thread closes.
        self.finish_switch_test_session()
        if self.hardware_thread is not None:
            self.hardware_thread.deleteLater()
        if self.hardware_worker is not None:
            self.hardware_worker.deleteLater()
        self.hardware_thread = None
        self.hardware_worker = None
        self.start_hardware_button.setEnabled(True)
        self.change_hardware_channel_button.setEnabled(False)
        self.set_open_csv_available(True)

    def set_open_csv_available(self, available):
        """Keep CSV loading disabled while a hardware run owns the UI."""
        self.open_csv_button.setEnabled(available)
        self.open_csv_action.setEnabled(available)

    def closeEvent(self, event):
        if self.reference_worker is not None and self.reference_thread is not None:
            self._finish_reference_calculation()
        if self.hardware_worker is not None and self.hardware_thread is not None:
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
        result = self.replacement_analysis
        if not result:
            self.replacement_summary_label.setText("Not run")
            return
        if not result.get("applicable"):
            self.replacement_summary_label.setText(result.get("status", "Not applicable"))
            return

        recommendation_count = len(result.get("recommendations", []))
        spare_ports = [
            str(spare["physical_port"])
            for spare in result.get("bottom_spares", [])
        ]
        lines = [
            "%d replacement recommendation(s)." % recommendation_count,
            "Recommended designated spares: %s"
            % (", ".join(spare_ports) if spare_ports else "none"),
        ]
        for recommendation in result.get("recommendations", []):
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
        """Attach replacement results to the run and persist CSV/JSON metadata."""
        if self.run_data is None:
            return
        self.replacement_analysis = result
        self.run_data.replacement_analysis = result
        self.run_data.metadata.update(replacement_metadata(result))

        if self.run_recorder is None:
            self.run_recorder = RunRecorder.from_existing(
                self.run_data.source_path,
                metadata=self.run_data.metadata,
                limit=self.limit_spin.value(),
                attempts=self.run_data.attempts,
                replacement_analysis=result,
            )
        else:
            self.run_recorder.metadata.update(replacement_metadata(result))
            self.run_recorder.limit = self.limit_spin.value()
            self.run_recorder.replacement_analysis = result
        self.run_recorder.save(self.run_data.measurements)
        self.refresh_replacement_summary()
        self.statusBar().showMessage(
            "Replacement analysis saved to CSV metadata and run.json."
        )

    def refresh_coc_controls(self):
        """Enable COC export whenever a run, including a partial run, is loaded."""
        enabled = bool(self.run_data and self.run_data.measurements)
        self.write_coc_button.setEnabled(enabled)
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
            self.run_recorder = RunRecorder.from_existing(
                self.run_data.source_path,
                metadata=self.run_data.metadata,
                limit=self.limit_spin.value(),
                attempts=self.run_data.attempts,
                replacement_analysis=self.run_data.replacement_analysis,
                switch_test_sessions=self.run_data.switch_test_sessions,
            )
        else:
            self.run_recorder.metadata = dict(self.run_data.metadata)
            self.run_recorder.limit = self.limit_spin.value()
            self.run_recorder.attempts = list(self.run_data.attempts)
            self.run_recorder.replacement_analysis = self.run_data.replacement_analysis
            self.run_recorder.switch_test_sessions = list(
                self.run_data.switch_test_sessions
            )
        self.run_recorder.save(self.run_data.measurements)

    def write_coc(self):
        """Write the current partial or complete run to a copied XLSX template."""
        if self.run_data is None:
            QMessageBox.information(self, "No run loaded", "Load or start a run first.")
            return

        serial = self.hardware_main_board_serial.text().strip()
        if not serial:
            serial = self.run_data.metadata.get("Main board serial", "").strip()
        part_number = self.hardware_part_number.text().strip()
        if not part_number:
            part_number = self.run_data.metadata.get("Part number", "").strip()
        if not part_number and serial:
            lookup_root = self.settings.value(
                "part_lookup_root",
                str(DEFAULT_PART_LOOKUP_ROOT),
            )
            try:
                part_number = find_part_number(serial, lookup_root)
                self.hardware_part_number.setText(part_number)
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
            output_path = export_coc(
                template,
                self.run_data.source_path.parent,
                self.run_data.measurements,
                part_number,
                serial,
            )
            self.run_data.metadata.update(
                {
                    "Part number": part_number,
                    "Main board serial": normalise_serial(serial),
                    "COC output file": output_path.name,
                    "COC output path": str(output_path),
                    "COC exported at": datetime.now().isoformat(timespec="seconds"),
                    "COC template": str(template),
                }
            )
            self.hardware_part_number.setText(part_number)
            self.hardware_main_board_serial.setText(normalise_serial(serial))
            self.metadata_labels["Part number"].setText(part_number)
            self.metadata_labels["Main board serial"].setText(normalise_serial(serial))
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

    def clear_current_reading(self, channel=None, status="No reading yet"):
        """Clear stale values while optionally showing the routed channel."""
        self.set_current_reading_channel(channel)
        self.current_loss_1310 = None
        self.current_loss_1550 = None
        self.demo_1310_label.setText("1310 nm: -")
        self.demo_1550_label.setText("1550 nm: -")
        self.reading_status_label.setText(status)
        self.reading_status_label.setStyleSheet("color: #587073;")

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
        self.reading_status_label.setStyleSheet(
            "color: %s;" % ("#a33b2f" if flagged_1310 or flagged_1550 else "#28704a")
        )

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
            if is_pending:
                values = [str(record.channel), "-", "-", "Taking measurement"]
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
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                if flagged:
                    item.setBackground(DANGER)
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
