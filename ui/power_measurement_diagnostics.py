"""Diagnostic dialog for absolute ILM power and optional switch routing."""

from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.power_diagnostics_controller import PowerDiagnosticsController
from application.diagnostic_trace import DiagnosticTraceRecorder
from application.red_light_controller import RedLightTestController
from application.timing import LIVE_UPDATE_PAUSE_MS
from config.app_info import APP_VERSION
from domain.diagnostic_analysis import (
    DiagnosticAnalysis,
    DiagnosticReading,
    MANUAL_METHOD,
    MONITORING_METHOD,
    analyze_diagnostic_readings,
)
from hardware.factory import HardwareFactory
from infrastructure.diagnostic_export import (
    available_diagnostic_export_path,
    export_diagnostic_history,
    timestamped_diagnostic_filename,
)


class DiagnosticExportOptionsDialog(QDialog):
    """Choose whether the optional in-memory hardware trace is exported."""

    def __init__(self, has_trace, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export Diagnostic History")
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Choose whether to include the optional hardware trace. "
                "The normal diagnostic history export is always included."
            )
        )
        self.include_trace_checkbox = QCheckBox("Include Hardware Trace")
        self.include_trace_checkbox.setChecked(bool(has_trace))
        self.include_trace_checkbox.setEnabled(bool(has_trace))
        if not has_trace:
            self.include_trace_checkbox.setToolTip(
                "No hardware trace events were collected in this session."
            )
        layout.addWidget(self.include_trace_checkbox)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def include_trace(self):
        """Return the operator's trace-export selection."""
        return self.include_trace_checkbox.isChecked()


class PowerMeasurementDiagnosticsDialog(QDialog):
    """Show raw meter values and optionally route the OSX-150 switch.

    Diagnostic readings are intentionally kept in memory. This makes the tool
    useful for investigating instrument behavior without altering a production
    run or creating a second diagnostic file format.
    """

    references_changed = pyqtSignal(float, float)

    def __init__(
        self,
        parent=None,
        reference_1310=0.00,
        reference_1550=0.00,
        meter_factory=None,
        switch_factory=None,
    ):
        super().__init__(parent)
        self.hardware_factory = HardwareFactory()
        self.meter_factory = meter_factory or self.hardware_factory.create_power_meter
        self.switch_factory = switch_factory or self.hardware_factory.create_switch

        self.trace_recorder = DiagnosticTraceRecorder(APP_VERSION)
        self.meter_controller = PowerDiagnosticsController(
            self,
            trace_callback=self.trace_recorder.record,
            trace_metadata={"application_version": APP_VERSION},
        )
        self.switch_controller = RedLightTestController(self)
        self.meter_controller.connected.connect(self._meter_connected)
        self.meter_controller.reading_ready.connect(self._reading_ready)
        self.meter_controller.reference_ready.connect(self._reference_ready)
        self.meter_controller.failed.connect(self._meter_failed)
        self.meter_controller.thread_finished.connect(self._meter_finished)
        self.switch_controller.connected.connect(self._switch_connected)
        self.switch_controller.channel_selected.connect(self._channel_selected)
        self.switch_controller.failed.connect(self._switch_failed)
        self.switch_controller.thread_finished.connect(self._switch_finished)

        self.meter_connected = False
        self.switch_connected = False
        self.read_pending = False
        self.pending_method = None
        self.pending_trace_id = None
        self.reference_trace_id = 0
        self.reference_pending = False
        self.monitoring_active = False
        self.variation_analysis_visible = True
        self.analysis_text = ""
        self.history = []
        self.reference_progress = None
        self.channel_count = 0
        self.last_physical_port = None

        self.monitor_timer = QTimer(self)
        self.monitor_timer.setSingleShot(True)
        self.monitor_timer.timeout.connect(self._request_monitoring_read)

        self.setWindowTitle("Power Measurement Diagnostics")
        self.setMinimumSize(980, 680)
        self.resize(1180, 760)
        self._build_ui(reference_1310, reference_1550)
        self._update_controls()

    def _build_ui(self, reference_1310, reference_1550):
        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Read the ILM/OP815 absolute power and see the exact insertion-loss "
            "calculation. Diagnostic readings are not saved. The switch is "
            "optional and can be used to route a channel before reading."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        setup_layout = QHBoxLayout()
        meter_box = QGroupBox("Power meter")
        meter_layout = QVBoxLayout(meter_box)
        meter_buttons = QHBoxLayout()
        self.connect_meter_button = QPushButton("Connect Meter")
        self.connect_meter_button.setObjectName("primary_action")
        self.connect_meter_button.clicked.connect(self.start_meter)
        meter_buttons.addWidget(self.connect_meter_button)
        self.disconnect_meter_button = QPushButton("Disconnect Meter")
        self.disconnect_meter_button.clicked.connect(self.stop_meter)
        meter_buttons.addWidget(self.disconnect_meter_button)
        meter_layout.addLayout(meter_buttons)
        self.meter_status_label = QLabel("Not connected")
        self.meter_status_label.setWordWrap(True)
        meter_layout.addWidget(self.meter_status_label)
        setup_layout.addWidget(meter_box, 1)

        switch_box = QGroupBox("Optional switch control")
        switch_layout = QVBoxLayout(switch_box)
        switch_buttons = QHBoxLayout()
        self.connect_switch_button = QPushButton("Connect Switch")
        self.connect_switch_button.clicked.connect(self.start_switch)
        switch_buttons.addWidget(self.connect_switch_button)
        self.disconnect_switch_button = QPushButton("Disconnect Switch")
        self.disconnect_switch_button.clicked.connect(self.stop_switch)
        switch_buttons.addWidget(self.disconnect_switch_button)
        switch_layout.addLayout(switch_buttons)
        switch_form = QFormLayout()
        self.channel_spin = QSpinBox()
        self.channel_spin.setRange(1, 1)
        self.channel_spin.setKeyboardTracking(False)
        self.channel_spin.setToolTip("Logical channel to route through the switch.")
        switch_form.addRow("Logical channel:", self.channel_spin)
        self.physical_port_label = QLabel("-")
        switch_form.addRow("Physical port:", self.physical_port_label)
        switch_layout.addLayout(switch_form)
        channel_buttons = QHBoxLayout()
        self.set_channel_button = QPushButton("Set Channel")
        self.set_channel_button.clicked.connect(self.set_channel)
        channel_buttons.addWidget(self.set_channel_button)
        self.previous_channel_button = QPushButton("Previous")
        self.previous_channel_button.clicked.connect(self.previous_channel)
        channel_buttons.addWidget(self.previous_channel_button)
        self.next_channel_button = QPushButton("Next")
        self.next_channel_button.clicked.connect(self.next_channel)
        channel_buttons.addWidget(self.next_channel_button)
        switch_layout.addLayout(channel_buttons)
        self.switch_status_label = QLabel("Switch not connected")
        self.switch_status_label.setWordWrap(True)
        switch_layout.addWidget(self.switch_status_label)
        setup_layout.addWidget(switch_box, 1)

        reference_box = QGroupBox("Diagnostic references")
        reference_layout = QFormLayout(reference_box)
        self.reference_1310_spin = self._reference_spin(reference_1310)
        self.reference_1550_spin = self._reference_spin(reference_1550)
        reference_layout.addRow("1310 nm:", self.reference_1310_spin)
        reference_layout.addRow("1550 nm:", self.reference_1550_spin)
        reference_buttons = QHBoxLayout()
        self.calculate_reference_button = QPushButton("Calculate Reference")
        self.calculate_reference_button.clicked.connect(self.calculate_reference)
        reference_buttons.addWidget(self.calculate_reference_button)
        self.apply_reference_button = QPushButton("Apply References to Main Setup")
        self.apply_reference_button.clicked.connect(self.apply_references)
        reference_buttons.addWidget(self.apply_reference_button)
        reference_layout.addRow("", reference_buttons)
        self.last_reference_label = QLabel("No reference measurement yet")
        self.last_reference_label.setWordWrap(True)
        reference_layout.addRow("Last baseline:", self.last_reference_label)
        setup_layout.addWidget(reference_box, 1)
        layout.addLayout(setup_layout)

        current_box = QGroupBox("Current diagnostic measurement")
        current_layout = QGridLayout(current_box)
        current_layout.addWidget(QLabel("Wavelength"), 0, 0)
        current_layout.addWidget(QLabel("Measured power"), 0, 1)
        current_layout.addWidget(QLabel("Reference"), 0, 2)
        current_layout.addWidget(QLabel("Calculation"), 0, 3)
        current_layout.addWidget(QLabel("Insertion loss"), 0, 4)
        self.current_labels = {}
        for row, wavelength in enumerate((1310, 1550), start=1):
            current_layout.addWidget(QLabel("%d nm" % wavelength), row, 0)
            measured = QLabel("-")
            reference = QLabel("-")
            calculation = QLabel("-")
            loss = QLabel("-")
            calculation.setWordWrap(True)
            current_layout.addWidget(measured, row, 1)
            current_layout.addWidget(reference, row, 2)
            current_layout.addWidget(calculation, row, 3)
            current_layout.addWidget(loss, row, 4)
            self.current_labels[wavelength] = {
                "measured": measured,
                "reference": reference,
                "calculation": calculation,
                "loss": loss,
            }
        layout.addWidget(current_box)

        history_box = QGroupBox("Reading history")
        history_layout = QVBoxLayout(history_box)
        self.history_table = QTableWidget(0, 11)
        self.history_table.setHorizontalHeaderLabels(
            [
                "Reading",
                "Time",
                "Channel",
                "Physical port",
                "1310 measured (dBm)",
                "1310 reference (dBm)",
                "1310 IL (dB)",
                "1550 measured (dBm)",
                "1550 reference (dBm)",
                "1550 IL (dB)",
                "Method",
            ]
        )
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionMode(QTableWidget.NoSelection)
        self.history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.history_table.setMinimumHeight(190)
        history_layout.addWidget(self.history_table)
        history_buttons = QHBoxLayout()
        self.clear_history_button = QPushButton("Clear History")
        self.clear_history_button.clicked.connect(self.clear_history)
        history_buttons.addWidget(self.clear_history_button)
        self.export_history_button = QPushButton("Export History...")
        self.export_history_button.clicked.connect(self.export_history)
        history_buttons.addWidget(self.export_history_button)
        self.toggle_analysis_button = QPushButton("Hide Variation Analysis")
        self.toggle_analysis_button.clicked.connect(self.toggle_variation_analysis)
        history_buttons.addWidget(self.toggle_analysis_button)
        history_buttons.addStretch()
        history_layout.addLayout(history_buttons)

        analysis_box = QGroupBox("Variation analysis")
        analysis_box_layout = QVBoxLayout(analysis_box)
        self.analysis_scroll_area = QScrollArea()
        self.analysis_scroll_area.setObjectName("variation_analysis_scroll_area")
        self.analysis_scroll_area.setWidgetResizable(True)
        self.analysis_scroll_area.setFrameShape(QFrame.NoFrame)
        self.analysis_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        analysis_content = QWidget()
        analysis_content.setObjectName("variation_analysis_content")
        analysis_layout = QVBoxLayout(analysis_content)
        self.analyze_repeatability_button = QPushButton("Analyze Repeatability")
        self.analyze_repeatability_button.clicked.connect(
            self.analyze_repeatability
        )
        analysis_layout.addWidget(self.analyze_repeatability_button)
        self.analyze_stability_button = QPushButton("Analyze Stability")
        self.analyze_stability_button.clicked.connect(self.analyze_stability)
        analysis_layout.addWidget(self.analyze_stability_button)
        self.copy_analysis_button = QPushButton("Copy Analysis")
        self.copy_analysis_button.clicked.connect(self.copy_analysis)
        analysis_layout.addWidget(self.copy_analysis_button)
        self.analysis_results_label = QLabel(
            "No analysis run. Use manual readings for repeatability or "
            "monitoring readings for stability."
        )
        self.analysis_results_label.setWordWrap(True)
        analysis_layout.addWidget(self.analysis_results_label)
        analysis_layout.addStretch()
        self.analysis_scroll_area.setWidget(analysis_content)
        self._apply_variation_analysis_theme()
        analysis_box_layout.addWidget(self.analysis_scroll_area)
        analysis_box.setMinimumWidth(300)
        self.variation_analysis_panel = analysis_box

        self.analysis_splitter = QSplitter(Qt.Horizontal)
        self.analysis_splitter.setChildrenCollapsible(False)
        self.analysis_splitter.addWidget(history_box)
        self.analysis_splitter.addWidget(analysis_box)
        self.analysis_splitter.setStretchFactor(0, 3)
        self.analysis_splitter.setStretchFactor(1, 1)
        self.analysis_splitter.setSizes([780, 340])
        layout.addWidget(self.analysis_splitter, 1)

        self.live_indicator = QLabel("● LIVE")
        self.live_indicator.setObjectName("live_indicator")
        self.live_indicator.setVisible(False)
        layout.addWidget(self.live_indicator)
        self.status_label = QLabel("Not started. Connect the meter to begin.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.read_button = QPushButton("Read Measured Power")
        self.read_button.setObjectName("primary_action")
        self.read_button.clicked.connect(self.read_power)
        actions.addWidget(self.read_button)
        self.start_monitor_button = QPushButton("Start Monitoring")
        self.start_monitor_button.clicked.connect(self.start_monitoring)
        actions.addWidget(self.start_monitor_button)
        self.stop_monitor_button = QPushButton("Stop Monitoring")
        self.stop_monitor_button.clicked.connect(self.stop_monitoring)
        actions.addWidget(self.stop_monitor_button)
        actions.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.request_close)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

    def _apply_variation_analysis_theme(self):
        """Keep the scroll area's separate viewport consistent with the app theme.

        QScrollArea's viewport and its content widget do not always inherit the
        top-level dialog stylesheet, so they need explicit colors. The parent
        main window owns the persisted theme setting; standalone dialogs default
        to the light palette.
        """
        parent = self.parentWidget()
        dark_mode = False
        while parent is not None:
            if hasattr(parent, "dark_mode_enabled"):
                dark_mode = bool(parent.dark_mode_enabled)
                break
            parent = parent.parentWidget()

        if dark_mode:
            background = "#2b2e33"
            text = "#e8eaed"
        else:
            background = "#f7f8f9"
            text = "#202124"

        # The scroll area's local stylesheet takes precedence over the main
        # window stylesheet, so preserve the application's red button treatment
        # explicitly for controls inside the analysis content widget.
        analysis_content_style = """
            QWidget#variation_analysis_content {{
                background-color: {background};
            }}
            QPushButton {{
                background-color: #e60013;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #b80010;
            }}
            QPushButton:disabled {{
                background-color: #8b000b;
                color: #f3c7ca;
            }}
        """.format(background=background)

        self.analysis_scroll_area.setStyleSheet(
            "QScrollArea#variation_analysis_scroll_area "
            "{ background-color: %s; border: none; }" % background
        )
        self.analysis_scroll_area.viewport().setStyleSheet(
            "background-color: %s;" % background
        )
        self.analysis_scroll_area.widget().setStyleSheet(analysis_content_style)
        self.analysis_results_label.setStyleSheet(
            "background-color: transparent; color: %s;" % text
        )

    @staticmethod
    def _reference_spin(value):
        spin = QDoubleSpinBox()
        spin.setRange(-100.0, 100.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.01)
        spin.setValue(value)
        spin.setSuffix(" dBm")
        return spin

    def _parent_hardware_active(self):
        return bool(getattr(self.parent(), "hardware_run_active", False))

    def _warn_if_hardware_active(self):
        if not self._parent_hardware_active():
            return False
        QMessageBox.warning(
            self,
            "Hardware run active",
            "Stop the current hardware run before using Power Measurement "
            "Diagnostics.",
        )
        return True

    def start_meter(self):
        if self._warn_if_hardware_active() or self.meter_controller.worker is not None:
            return
        try:
            self.meter_controller.start(self.meter_factory)
        except Exception as error:
            QMessageBox.critical(self, "Power diagnostics", str(error))
            return
        self.meter_status_label.setText("Connecting to the ILM/OP815...")
        self.status_label.setText("Connecting to the power meter...")
        self._update_controls()

    def _meter_connected(self, description):
        self.meter_connected = True
        self.trace_recorder.update_metadata(meter_description=description)
        self.meter_status_label.setText(description)
        self.status_label.setText(
            "Meter connected. Read the current absolute power when ready."
        )
        self._update_controls()

    def stop_meter(self):
        self.stop_monitoring(update_status=False)
        if self.meter_controller.worker is None and self.meter_controller.thread is None:
            self._reset_meter_state()
            return
        self.status_label.setText("Disconnecting the ILM/OP815...")
        if not self.meter_controller.stop_and_wait():
            QMessageBox.warning(
                self,
                "Power diagnostics",
                "The meter is still disconnecting. Try again shortly.",
            )

    def _meter_finished(self):
        self._reset_meter_state()
        if self.isVisible():
            self.status_label.setText("Meter disconnected.")

    def _reset_meter_state(self):
        self.meter_connected = False
        self.read_pending = False
        self.pending_method = None
        self.pending_trace_id = None
        self.reference_pending = False
        self.meter_status_label.setText("Not connected")
        self._close_reference_progress()
        self._update_controls()

    def read_power(self, method=MANUAL_METHOD):
        if not self.meter_connected or self.read_pending or self.reference_pending:
            return
        self.read_pending = True
        self.pending_method = method
        self.pending_trace_id = len(self.history) + 1
        channel = self.channel_spin.value() if self.switch_connected else None
        physical_port = (
            self.last_physical_port if self.switch_connected else None
        )
        self.status_label.setText("Reading 1310 nm and 1550 nm absolute power...")
        self.meter_controller.read(
            self.reference_1310_spin.value(),
            self.reference_1550_spin.value(),
            self.pending_trace_id,
            method,
            channel,
            physical_port,
        )
        self._update_controls()

    def _reading_ready(
        self,
        measured,
        reference_1310,
        reference_1550,
        loss_1310,
        loss_1550,
    ):
        self.read_pending = False
        method = self.pending_method or MANUAL_METHOD
        self.pending_method = None
        self.pending_trace_id = None
        self._display_current(
            measured,
            reference_1310,
            reference_1550,
            loss_1310,
            loss_1550,
        )
        self._append_history(
            measured,
            reference_1310,
            reference_1550,
            loss_1310,
            loss_1550,
            method,
        )
        if self.monitoring_active:
            self.status_label.setText(
                "Monitoring sample complete. Next sample will start shortly."
            )
            self.monitor_timer.start(LIVE_UPDATE_PAUSE_MS)
        else:
            self.status_label.setText("Reading complete. No data was saved.")
        self._update_controls()

    def _display_current(
        self,
        measured,
        reference_1310,
        reference_1550,
        loss_1310,
        loss_1550,
    ):
        values = {
            1310: (measured[1310], reference_1310, loss_1310),
            1550: (measured[1550], reference_1550, loss_1550),
        }
        for wavelength, (power, reference, loss) in values.items():
            labels = self.current_labels[wavelength]
            labels["measured"].setText("%.4f dBm" % power)
            labels["reference"].setText("%.2f dBm" % reference)
            labels["calculation"].setText(
                "%s - %s = %.4f dB"
                % (
                    self._format_arithmetic_value(reference, 2),
                    self._format_arithmetic_value(power, 4),
                    loss,
                )
            )
            labels["loss"].setText("%.4f dB" % loss)

    @staticmethod
    def _format_arithmetic_value(value, decimals):
        """Parenthesize negative operands so the displayed subtraction is clear."""
        formatted = ("%%.%df" % decimals) % value
        return "(%s)" % formatted if value < 0 else formatted

    def _append_history(
        self,
        measured,
        reference_1310,
        reference_1550,
        loss_1310,
        loss_1550,
        method,
    ):
        reading = DiagnosticReading(
            reading_number=len(self.history) + 1,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            method=method,
            channel=self.channel_spin.value() if self.switch_connected else None,
            physical_port=(
                self.last_physical_port
                if self.switch_connected and self.last_physical_port is not None
                else None
            ),
            measured_1310=float(measured[1310]),
            reference_1310=float(reference_1310),
            insertion_loss_1310=float(loss_1310),
            measured_1550=float(measured[1550]),
            reference_1550=float(reference_1550),
            insertion_loss_1550=float(loss_1550),
        )
        self.history.append(reading)
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        row_data = (
            reading.reading_number,
            reading.timestamp,
            reading.channel if reading.channel is not None else "-",
            reading.physical_port if reading.physical_port is not None else "-",
            "%.4f" % reading.measured_1310,
            "%.2f" % reading.reference_1310,
            "%.4f" % reading.insertion_loss_1310,
            "%.4f" % reading.measured_1550,
            "%.2f" % reading.reference_1550,
            "%.4f" % reading.insertion_loss_1550,
            reading.method,
        )
        for column, value in enumerate(row_data):
            self.history_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.history_table.scrollToBottom()
        self._clear_analysis_display()

    def calculate_reference(self):
        if (
            not self.meter_connected
            or self.read_pending
            or self.reference_pending
            or self.monitoring_active
        ):
            return
        self.reference_pending = True
        self.reference_trace_id += 1
        self.reference_progress = QProgressDialog(
            "Calculating reference offset...",
            None,
            0,
            0,
            self,
        )
        self.reference_progress.setWindowTitle("Calculate Reference")
        self.reference_progress.setWindowModality(Qt.ApplicationModal)
        self.reference_progress.setMinimumDuration(0)
        self.reference_progress.setAutoClose(False)
        self.reference_progress.setAutoReset(False)
        self.reference_progress.show()
        self.status_label.setText("Calculating reference from the meter baseline...")
        self.meter_controller.calculate_reference(self.reference_trace_id)
        self._update_controls()

    def _reference_ready(self, measured, reference_1310, reference_1550):
        self.reference_pending = False
        self.reference_1310_spin.setValue(reference_1310)
        self.reference_1550_spin.setValue(reference_1550)
        self.last_reference_label.setText(
            "1310: %.4f dBm; 1550: %.4f dBm"
            % (measured[1310], measured[1550])
        )
        self._close_reference_progress()
        self.status_label.setText(
            "Reference calculated in diagnostics. Apply it to the main setup "
            "only if desired."
        )
        self._update_controls()

    def apply_references(self):
        self.references_changed.emit(
            self.reference_1310_spin.value(),
            self.reference_1550_spin.value(),
        )
        self.status_label.setText("Diagnostic references applied to main setup.")

    def start_monitoring(self):
        if self.meter_connected and not self.monitoring_active and not self.reference_pending:
            self.monitoring_active = True
            self.live_indicator.setVisible(True)
            self.status_label.setText("Monitoring active. Taking a reading...")
            self._request_monitoring_read()
            self._update_controls()

    def stop_monitoring(self, update_status=True):
        was_active = self.monitoring_active
        self.monitoring_active = False
        self.monitor_timer.stop()
        self.live_indicator.setVisible(False)
        if update_status and was_active:
            self.status_label.setText("Monitoring stopped. No data was saved.")
        self._update_controls()

    def _request_monitoring_read(self):
        if self.monitoring_active and self.meter_connected and not self.read_pending:
            self.read_power(MONITORING_METHOD)

    def _meter_failed(self, message):
        self.read_pending = False
        self.pending_method = None
        self.pending_trace_id = None
        self.reference_pending = False
        self.stop_monitoring(update_status=False)
        self._close_reference_progress()
        self.status_label.setText("Meter operation failed: %s" % message)
        # A failed startup can leave the worker alive because there is no
        # connected signal to trigger normal dialog cleanup.  Shut it down
        # through the same bounded path used by the Close button.
        if not self.meter_connected and self.meter_controller.worker is not None:
            self.meter_controller.stop_and_wait()
        self._update_controls()
        if not self.meter_connected:
            QMessageBox.critical(self, "Power diagnostics", message)

    def start_switch(self):
        if self._warn_if_hardware_active() or self.switch_controller.worker is not None:
            return
        try:
            self.switch_controller.start(self.switch_factory)
        except Exception as error:
            QMessageBox.critical(self, "Power diagnostics", str(error))
            return
        self.switch_status_label.setText("Connecting to the OSX-150...")
        self._update_controls()

    def _switch_connected(self, channel_count):
        self.switch_connected = True
        self.channel_count = channel_count
        self.channel_spin.setRange(1, channel_count)
        self.switch_status_label.setText(
            "Connected. Select a logical channel and click Set Channel."
        )
        self._update_controls()

    def set_channel(self):
        if not self.switch_connected or self.read_pending or self.monitoring_active:
            if self.monitoring_active:
                self.switch_status_label.setText(
                    "Stop monitoring before changing the switch channel."
                )
            return
        self.switch_controller.select_channel(self.channel_spin.value())
        self.switch_status_label.setText(
            "Selecting logical channel %d..." % self.channel_spin.value()
        )

    def _channel_selected(self, channel, physical_port):
        self.last_physical_port = physical_port
        self.physical_port_label.setText(str(physical_port))
        self.switch_status_label.setText(
            "Logical channel %d selected; physical port %s is active."
            % (channel, physical_port)
        )

    def previous_channel(self):
        if self.switch_connected and self.channel_spin.value() > 1:
            self.channel_spin.setValue(self.channel_spin.value() - 1)
            self.set_channel()

    def next_channel(self):
        if self.switch_connected and self.channel_spin.value() < self.channel_count:
            self.channel_spin.setValue(self.channel_spin.value() + 1)
            self.set_channel()

    def stop_switch(self):
        if self.switch_controller.worker is None and self.switch_controller.thread is None:
            self._reset_switch_state()
            return
        self.switch_status_label.setText("Disconnecting the OSX-150...")
        if not self.switch_controller.stop_and_wait():
            QMessageBox.warning(
                self,
                "Power diagnostics",
                "The switch is still disconnecting. Try again shortly.",
            )

    def _switch_finished(self):
        self._reset_switch_state()

    def _reset_switch_state(self):
        self.switch_connected = False
        self.channel_count = 0
        self.last_physical_port = None
        self.channel_spin.setRange(1, 1)
        self.physical_port_label.setText("-")
        self.switch_status_label.setText("Switch not connected")
        self._update_controls()

    def _switch_failed(self, message):
        self.switch_status_label.setText("Switch operation failed: %s" % message)
        if not self.switch_connected:
            QMessageBox.critical(self, "Power diagnostics", message)

    def clear_history(self):
        self.history.clear()
        self.trace_recorder.clear()
        self.history_table.setRowCount(0)
        self._clear_analysis_display()
        self.status_label.setText("Diagnostic history cleared.")

    def toggle_variation_analysis(self):
        """Show or hide the right-side analysis panel without clearing results."""
        self.variation_analysis_visible = not self.variation_analysis_visible
        self.variation_analysis_panel.setVisible(self.variation_analysis_visible)
        self.toggle_analysis_button.setText(
            "Hide Variation Analysis"
            if self.variation_analysis_visible
            else "Show Variation Analysis"
        )

    def export_history(self):
        """Save the complete in-memory history in the operator's chosen format."""
        if not self.history:
            QMessageBox.information(
                self,
                "Export Diagnostic History",
                "There are no diagnostic readings to export.",
            )
            return

        suggested_name = timestamped_diagnostic_filename()
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Diagnostic History",
            suggested_name,
            "CSV Files (*.csv);;JSON Files (*.json)",
        )
        if not path:
            return

        destination = Path(path)
        if destination.suffix.lower() not in (".csv", ".json"):
            extension = ".json" if "JSON" in selected_filter else ".csv"
            destination = destination.with_suffix(extension)

        include_trace = self._ask_trace_export()
        if include_trace is None:
            return

        # Automatically generated timestamped names must not overwrite an
        # export from the same second.  Deliberately edited filenames retain
        # the existing save behavior.
        if destination.stem == Path(suggested_name).stem:
            destination = available_diagnostic_export_path(
                destination,
                include_hardware_trace=include_trace,
            )

        try:
            export_diagnostic_history(
                destination,
                self.history,
                include_hardware_trace=include_trace,
                trace_events=self.trace_recorder.events(),
                trace_metadata=self.trace_recorder.metadata(),
            )
        except (OSError, ValueError) as error:
            QMessageBox.critical(
                self,
                "Export Diagnostic History",
                "Could not export diagnostic history: %s" % error,
            )
            return

        trace_note = " and hardware trace" if include_trace else ""
        self.status_label.setText(
            "Diagnostic history%s exported to %s. No run data was changed."
            % (trace_note, destination)
        )

    def _ask_trace_export(self):
        """Return the trace choice, or ``None`` when the export is cancelled."""
        dialog = DiagnosticExportOptionsDialog(
            bool(self.trace_recorder.events()),
            self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return None
        return dialog.include_trace()

    def analyze_repeatability(self):
        self._analyze_method(MANUAL_METHOD, "Repeatability Analysis")

    def analyze_stability(self):
        self._analyze_method(MONITORING_METHOD, "Stability Analysis")

    def _analyze_method(self, method, title):
        try:
            analysis = analyze_diagnostic_readings(self.history, method)
        except ValueError as error:
            self.status_label.setText(str(error))
            QMessageBox.information(self, title, str(error))
            return

        self.analysis_text = self._format_analysis(title, analysis)
        self.analysis_results_label.setText(self.analysis_text)
        self.status_label.setText(
            "%s calculated from %d readings. No data was saved."
            % (title, analysis.count)
        )
        self._update_controls()

    @staticmethod
    def _format_analysis(title, analysis: DiagnosticAnalysis):
        lines = [
            title,
            "Samples: %d (%s readings)" % (analysis.count, analysis.method.lower()),
            "",
        ]
        for wavelength in (1310, 1550):
            statistics = analysis.by_wavelength[wavelength]
            lines.extend(
                [
                    "%d nm IL" % wavelength,
                    "  Average: %.4f dB" % statistics.average,
                    "  Lowest: %.4f dB" % statistics.minimum,
                    "  Highest: %.4f dB" % statistics.maximum,
                    "  Range: %.4f dB" % statistics.value_range,
                    "  Standard deviation: %.4f dB"
                    % statistics.standard_deviation,
                    "  First-to-last change: %+.4f dB"
                    % statistics.first_to_last,
                    "",
                ]
            )
        return "\n".join(lines).rstrip()

    def _clear_analysis_display(self):
        self.analysis_text = ""
        self.analysis_results_label.setText(
            "No analysis run. Use manual readings for repeatability or "
            "monitoring readings for stability."
        )

    def copy_analysis(self):
        """Copy the displayed variation analysis as plain text."""
        if not self.analysis_text:
            return
        QApplication.clipboard().setText(self.analysis_text)
        self.status_label.setText("Variation analysis copied to clipboard.")

    def _update_controls(self):
        meter_busy = self.read_pending or self.reference_pending
        meter_active = self.meter_controller.worker is not None
        switch_active = self.switch_controller.worker is not None
        self.connect_meter_button.setEnabled(not meter_active)
        self.disconnect_meter_button.setEnabled(meter_active)
        self.read_button.setEnabled(self.meter_connected and not meter_busy)
        self.calculate_reference_button.setEnabled(
            self.meter_connected and not meter_busy and not self.monitoring_active
        )
        self.apply_reference_button.setEnabled(not self.reference_pending)
        self.start_monitor_button.setEnabled(
            self.meter_connected and not meter_busy and not self.monitoring_active
        )
        self.stop_monitor_button.setEnabled(self.monitoring_active)
        self.connect_switch_button.setEnabled(not switch_active)
        self.disconnect_switch_button.setEnabled(switch_active)
        switch_controls = (
            self.switch_connected
            and not self.read_pending
            and not self.monitoring_active
        )
        self.channel_spin.setEnabled(self.switch_connected and not self.read_pending)
        self.set_channel_button.setEnabled(switch_controls)
        self.previous_channel_button.setEnabled(switch_controls)
        self.next_channel_button.setEnabled(switch_controls)
        self.clear_history_button.setEnabled(bool(self.history))
        self.export_history_button.setEnabled(bool(self.history))
        has_manual = any(reading.method == MANUAL_METHOD for reading in self.history)
        has_monitoring = any(
            reading.method == MONITORING_METHOD for reading in self.history
        )
        self.analyze_repeatability_button.setEnabled(has_manual)
        self.analyze_stability_button.setEnabled(has_monitoring)
        self.copy_analysis_button.setEnabled(bool(self.analysis_text))

    def _close_reference_progress(self):
        if self.reference_progress is not None:
            self.reference_progress.close()
            self.reference_progress.deleteLater()
            self.reference_progress = None

    def _shutdown_hardware(self):
        self.stop_monitoring(update_status=False)
        meter_stopped = self.meter_controller.stop_and_wait()
        switch_stopped = self.switch_controller.stop_and_wait()
        if meter_stopped:
            self._reset_meter_state()
        if switch_stopped:
            self._reset_switch_state()
        return meter_stopped and switch_stopped

    def request_close(self):
        if not self._shutdown_hardware():
            QMessageBox.warning(
                self,
                "Power diagnostics",
                "Hardware is still disconnecting. The dialog will remain open; "
                "please try closing it again shortly.",
            )
            return
        self.accept()

    def closeEvent(self, event):
        if not self._shutdown_hardware():
            QMessageBox.warning(
                self,
                "Power diagnostics",
                "Hardware is still disconnecting. The dialog will remain open; "
                "please try closing it again shortly.",
            )
            event.ignore()
            return
        event.accept()


__all__ = ["PowerMeasurementDiagnosticsDialog"]
