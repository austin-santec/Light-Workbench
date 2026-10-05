"""Standalone ILM/OP815 live-reading tool with no switch or run persistence."""

from PyQt5.QtCore import (
    QObject,
    QTimer,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from application.live_controller import LiveILReadingController
from application.timing import LIVE_UPDATE_PAUSE_MS
from domain.measurement import (
    calculate_insertion_loss,
    format_dark_reference_error,
    validate_insertion_loss,
    validate_reference_measurements,
)
from domain.reference import calculate_reference_offsets
from hardware.factory import HardwareFactory
from hardware.session import OpticalTestSession


class LiveILReadingWorker(QObject):
    """Own the meter connection and reads in a worker thread."""

    connected = pyqtSignal(str)
    reading_ready = pyqtSignal(float, float)
    reference_ready = pyqtSignal(float, float)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, meter):
        super().__init__()
        self.meter = meter
        self.hardware_session = OpticalTestSession(meter)
        self._finished = False

    @pyqtSlot()
    def start(self):
        try:
            self.hardware_session.connect()
            self.connected.emit(self.meter.description or "OP815 connected")
        except Exception as error:
            # Leave the worker event loop available until the UI receives the
            # error and asks this worker to close. Otherwise the worker can be
            # deleted before the queued failure handler has a chance to clean
            # up its thread safely.
            self.failed.emit(str(error))

    @pyqtSlot(float, float)
    def read(self, reference_1310, reference_1550):
        if self._finished:
            return
        try:
            setter = getattr(self.meter, "set_trace_context", None)
            if setter is not None:
                setter(
                    reference_1310_dbm=float(reference_1310),
                    reference_1550_dbm=float(reference_1550),
                    method="live_il",
                )
            measurements = self.meter.measure_both_wavelengths()
            losses = calculate_insertion_loss(
                {1310: reference_1310, 1550: reference_1550},
                measurements,
            )
            self.reading_ready.emit(losses[1310], losses[1550])
        except Exception as error:
            self.failed.emit(str(error))

    @pyqtSlot()
    def calculate_reference(self):
        if self._finished:
            return
        try:
            measurements = self.meter.measure_reference_wavelengths()
            validation = validate_reference_measurements(measurements)
            if not validation.valid:
                self.failed.emit(format_dark_reference_error(measurements))
                return
            reference_1310, reference_1550 = calculate_reference_offsets(measurements)
            self.reference_ready.emit(reference_1310, reference_1550)
        except Exception as error:
            self.failed.emit(str(error))

    @pyqtSlot()
    def stop(self):
        self._finish()

    def _finish(self):
        if self._finished:
            return
        self._finished = True
        close_error = None
        try:
            self.hardware_session.close()
        except Exception as error:
            close_error = str(error)
        finally:
            self.finished.emit()
        if close_error:
            self.failed.emit("Meter disconnect failed: %s" % close_error)


class LiveILReadingDialog(QDialog):
    """Read the current ILM values without controlling a switch or saving data."""

    read_requested = pyqtSignal(float, float)
    reference_requested = pyqtSignal()
    references_changed = pyqtSignal(float, float)

    def __init__(
        self,
        parent=None,
        reference_1310=0.00,
        reference_1550=0.00,
        meter_factory=None,
        auto_calculate_reference=False,
        support_logger=None,
        workflow_id="",
    ):
        super().__init__(parent)
        self.hardware_factory = HardwareFactory()
        self.meter_factory = (
            meter_factory
            if meter_factory is not None
            else self.hardware_factory.create_power_meter
        )
        self.thread = None
        self.worker = None
        self.support_logger = support_logger
        self.workflow_id = str(workflow_id or "")
        self.live_controller = LiveILReadingController(
            self,
            worker_factory=LiveILReadingWorker,
        )
        self.live_controller.connected.connect(self.meter_connected)
        self.live_controller.reading_ready.connect(self.reading_ready)
        self.live_controller.reference_ready.connect(self.reference_ready)
        self.live_controller.failed.connect(self.reading_failed)
        self.live_controller.thread_finished.connect(self.thread_finished)
        self.read_requested.connect(self.live_controller.read_requested)
        self.reference_requested.connect(self.live_controller.reference_requested)
        self.connected = False
        self.uses_persistent_connection = False
        self.auto_calculate_reference = auto_calculate_reference
        self.repeatability_active = False
        self.repeatability_read_pending = False
        self.repeatability_readings = []
        self.reference_progress = None
        self.read_pending = False
        self.live_updates_active = False
        self.live_update_timer = QTimer(self)
        self.live_update_timer.setSingleShot(True)
        self.live_update_timer.timeout.connect(self._request_live_update)

        self.setWindowTitle("Live IL Reading")
        self.setMinimumWidth(520)
        self.resize(640, 460)

        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Read the ILM/OP815's current insertion loss without selecting a "
            "switch channel or recording a run."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        content_layout = QHBoxLayout()
        left_layout = QVBoxLayout()

        reference_box = QGroupBox("Reference powers")
        reference_layout = QFormLayout(reference_box)
        self.reference_1310_spin = self._reference_spin(reference_1310)
        self.reference_1550_spin = self._reference_spin(reference_1550)
        reference_layout.addRow("1310 nm:", self.reference_1310_spin)
        reference_layout.addRow("1550 nm:", self.reference_1550_spin)
        self.calculate_reference_button = QPushButton("Calculate Reference")
        self.calculate_reference_button.setToolTip(
            "Read the meter with a zero software reference and apply the offsets."
        )
        self.calculate_reference_button.setEnabled(False)
        self.calculate_reference_button.clicked.connect(self.calculate_reference)
        reference_layout.addRow("", self.calculate_reference_button)
        left_layout.addWidget(reference_box)

        self.reference_1310_spin.valueChanged.connect(self.emit_reference_values)
        self.reference_1550_spin.valueChanged.connect(self.emit_reference_values)

        readings_box = QGroupBox("Current IL")
        readings_layout = QVBoxLayout(readings_box)
        readings_header = QHBoxLayout()
        readings_header.addStretch()
        self.live_update_indicator = QLabel()
        self.live_update_indicator.setFixedSize(14, 14)
        self.live_update_indicator.setToolTip("Live updates are active")
        self.live_update_indicator.setStyleSheet(
            "background-color: #e60013; border-radius: 7px;"
        )
        self.live_update_indicator.setVisible(False)
        readings_header.addWidget(self.live_update_indicator)
        readings_layout.addLayout(readings_header)
        self.reading_1310_label = QLabel("1310 nm IL: -")
        self.reading_1310_label.setObjectName("reading")
        self.reading_1550_label = QLabel("1550 nm IL: -")
        self.reading_1550_label.setObjectName("reading")
        readings_layout.addWidget(self.reading_1310_label)
        readings_layout.addWidget(self.reading_1550_label)
        left_layout.addWidget(readings_box)
        left_layout.addStretch()
        content_layout.addLayout(left_layout, 1)

        self.repeatability_box = self._build_repeatability_panel()
        self.repeatability_box.setVisible(False)
        content_layout.addWidget(self.repeatability_box, 1)
        layout.addLayout(content_layout)

        self.status_label = QLabel("Not started. Click Start Meter to connect.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Meter")
        self.start_button.setObjectName("primary_action")
        self.start_button.clicked.connect(self.start_meter)
        button_layout.addWidget(self.start_button)
        self.read_button = QPushButton("Read IL")
        self.read_button.setObjectName("primary_action")
        self.read_button.setEnabled(False)
        self.read_button.clicked.connect(self.read_il)
        button_layout.addWidget(self.read_button)
        self.live_update_button = QPushButton("Start Live Updates")
        self.live_update_button.setToolTip(
            "Automatically refresh both wavelength readings without saving data."
        )
        self.live_update_button.setEnabled(False)
        self.live_update_button.clicked.connect(self.toggle_live_updates)
        button_layout.addWidget(self.live_update_button)
        self.repeatability_button = QPushButton("Repeatability Test")
        self.repeatability_button.setToolTip(
            "Record IL readings after manually unplugging and reconnecting the cable."
        )
        self.repeatability_button.setEnabled(False)
        self.repeatability_button.clicked.connect(self.start_repeatability)
        button_layout.addWidget(self.repeatability_button)
        self.stop_button = QPushButton("Stop Meter")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_meter)
        button_layout.addWidget(self.stop_button)
        button_layout.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)

    def _build_repeatability_panel(self):
        panel = QGroupBox("Repeatability Test")
        panel.setMinimumWidth(440)
        panel_layout = QVBoxLayout(panel)

        instructions = QLabel(
            "Take an initial reading, unplug and reconnect the cable, then "
            "click Read Next Reading. Repeat as often as needed."
        )
        instructions.setWordWrap(True)
        panel_layout.addWidget(instructions)

        self.repeatability_table = QTableWidget(0, 3)
        self.repeatability_table.setHorizontalHeaderLabels(
            ["Reading", "1310 nm IL (dB)", "1550 nm IL (dB)"]
        )
        self.repeatability_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.repeatability_table.setSelectionMode(QTableWidget.NoSelection)
        self.repeatability_table.setMinimumHeight(180)
        panel_layout.addWidget(self.repeatability_table)

        stats_box = QGroupBox("Statistics")
        stats_layout = QFormLayout(stats_box)
        self.repeatability_stats_1310_label = QLabel("No readings")
        self.repeatability_stats_1550_label = QLabel("No readings")
        stats_layout.addRow("1310 nm:", self.repeatability_stats_1310_label)
        stats_layout.addRow("1550 nm:", self.repeatability_stats_1550_label)
        panel_layout.addWidget(stats_box)

        repeatability_buttons = QHBoxLayout()
        self.repeatability_read_button = QPushButton("Read Initial Reading")
        self.repeatability_read_button.setObjectName("primary_action")
        self.repeatability_read_button.setEnabled(False)
        self.repeatability_read_button.clicked.connect(self.read_repeatability)
        repeatability_buttons.addWidget(self.repeatability_read_button)
        self.repeatability_clear_button = QPushButton("Clear")
        self.repeatability_clear_button.setEnabled(False)
        self.repeatability_clear_button.clicked.connect(self.clear_repeatability)
        repeatability_buttons.addWidget(self.repeatability_clear_button)
        self.repeatability_finish_button = QPushButton("Finish Test")
        self.repeatability_finish_button.setEnabled(False)
        self.repeatability_finish_button.clicked.connect(self.finish_repeatability)
        repeatability_buttons.addWidget(self.repeatability_finish_button)
        panel_layout.addLayout(repeatability_buttons)
        return panel

    @staticmethod
    def _reference_spin(value):
        spin = QDoubleSpinBox()
        spin.setRange(-100.0, 100.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.01)
        spin.setValue(value)
        spin.setSuffix(" dBm")
        return spin

    def start_meter(self):
        if self.thread is not None:
            return
        try:
            self.live_controller.start(self.meter_factory)
            self.thread = self.live_controller.thread
            self.worker = self.live_controller.worker
            self.start_button.setEnabled(False)
            self.read_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status_label.setText("Connecting to the ILM/OP815...")
            self.thread.start()
        except Exception as error:
            self.thread = None
            self.worker = None
            QMessageBox.critical(self, "Live IL Reading", str(error))

    def meter_connected(self, description):
        self.connected = True
        self.uses_persistent_connection = bool(
            self.worker is not None
            and getattr(self.worker.meter, "persistent_connection", False)
        )
        self.read_button.setEnabled(
            self.connected
            and not self.repeatability_active
            and not self.live_updates_active
            and not self.read_pending
        )
        self.calculate_reference_button.setEnabled(
            not self.repeatability_active and not self.live_updates_active
        )
        self.live_update_button.setEnabled(not self.repeatability_active)
        self.repeatability_button.setEnabled(not self.live_updates_active)
        self.status_label.setText(
            "%s. Click Read IL whenever a current reading is needed." % description
        )
        if self.auto_calculate_reference:
            QTimer.singleShot(0, self.calculate_reference)

    def emit_reference_values(self):
        self.references_changed.emit(
            self.reference_1310_spin.value(), self.reference_1550_spin.value()
        )

    def set_reference_values(self, reference_1310, reference_1550):
        """Update shared references without echoing a synchronization signal."""
        self.reference_1310_spin.blockSignals(True)
        self.reference_1550_spin.blockSignals(True)
        try:
            self.reference_1310_spin.setValue(reference_1310)
            self.reference_1550_spin.setValue(reference_1550)
        finally:
            self.reference_1310_spin.blockSignals(False)
            self.reference_1550_spin.blockSignals(False)

    def calculate_reference(self):
        if (
            self.worker is not None
            and self.connected
            and not self.live_updates_active
            and not self.read_pending
        ):
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
            self.read_button.setEnabled(False)
            self.live_update_button.setEnabled(False)
            self.repeatability_button.setEnabled(False)
            self.status_label.setText("Calculating reference from the current meter reading...")
            self.reference_requested.emit()

    def toggle_live_updates(self):
        """Toggle automatic current-IL refreshes without saving readings."""
        if self.live_updates_active:
            self.stop_live_updates()
        else:
            self.start_live_updates()

    def start_live_updates(self):
        if (
            self.worker is None
            or not self.connected
            or self.repeatability_active
            or self.live_updates_active
        ):
            return
        self.live_updates_active = True
        self.live_update_indicator.setVisible(True)
        self.live_update_button.setText("Stop Live Updates")
        self.live_update_button.setEnabled(True)
        self.read_button.setEnabled(False)
        self.calculate_reference_button.setEnabled(False)
        self.repeatability_button.setEnabled(False)
        self.status_label.setText("Live updates active. Taking a reading...")
        self._request_live_update()

    def stop_live_updates(self, update_status=True):
        if not self.live_updates_active:
            self.live_update_timer.stop()
            self.live_update_indicator.setVisible(False)
            return
        self.live_updates_active = False
        self.live_update_timer.stop()
        self.live_update_indicator.setVisible(False)
        self.live_update_button.setText("Start Live Updates")
        if self.connected:
            self.read_button.setEnabled(
                not self.repeatability_active and not self.read_pending
            )
            self.calculate_reference_button.setEnabled(
                not self.repeatability_active and not self.read_pending
            )
            self.live_update_button.setEnabled(not self.repeatability_active)
            self.repeatability_button.setEnabled(
                not self.repeatability_active and not self.read_pending
            )
        if update_status:
            self.status_label.setText("Live updates stopped. No data was saved.")

    def _request_live_update(self):
        if (
            self.live_updates_active
            and self.connected
            and self.worker is not None
            and not self.read_pending
        ):
            self.read_il()

    def start_repeatability(self):
        if not self.connected:
            return
        self.stop_live_updates(update_status=False)
        self.repeatability_active = True
        self.repeatability_read_pending = False
        self.repeatability_readings = []
        self.repeatability_table.setRowCount(0)
        self.repeatability_stats_1310_label.setText("No readings")
        self.repeatability_stats_1550_label.setText("No readings")
        self.repeatability_box.setVisible(True)
        self.setMinimumSize(920, 560)
        self.resize(max(self.width(), 1000), max(self.height(), 650))
        self.repeatability_button.setEnabled(False)
        self.read_button.setEnabled(False)
        self.calculate_reference_button.setEnabled(False)
        self.live_update_button.setEnabled(False)
        self.repeatability_read_button.setEnabled(True)
        self.repeatability_clear_button.setEnabled(False)
        self.repeatability_finish_button.setEnabled(True)
        self.status_label.setText(
            "Repeatability test ready. Click Read Initial Reading."
        )

    def read_repeatability(self):
        if (
            self.worker is None
            or not self.connected
            or not self.repeatability_active
            or self.repeatability_read_pending
        ):
            return
        self.repeatability_read_pending = True
        self.repeatability_read_button.setEnabled(False)
        self.calculate_reference_button.setEnabled(False)
        self.status_label.setText("Taking repeatability reading...")
        self.read_requested.emit(
            self.reference_1310_spin.value(),
            self.reference_1550_spin.value(),
        )

    def clear_repeatability(self):
        if self.repeatability_read_pending:
            return
        self.repeatability_readings = []
        self.repeatability_table.setRowCount(0)
        self.repeatability_stats_1310_label.setText("No readings")
        self.repeatability_stats_1550_label.setText("No readings")
        self.repeatability_read_button.setText("Read Initial Reading")
        self.repeatability_clear_button.setEnabled(False)
        self.status_label.setText(
            "Repeatability test cleared. Click Read Initial Reading."
        )

    def finish_repeatability(self):
        if self.repeatability_read_pending:
            return
        self.repeatability_active = False
        self.repeatability_button.setEnabled(self.connected)
        self.read_button.setEnabled(self.connected)
        self.calculate_reference_button.setEnabled(self.connected)
        self.repeatability_read_button.setEnabled(False)
        self.repeatability_finish_button.setEnabled(False)
        self.status_label.setText(
            "Repeatability test finished. Results were not saved."
        )

    def _add_repeatability_reading(self, loss_1310, loss_1550):
        self.repeatability_readings.append((loss_1310, loss_1550))
        row = self.repeatability_table.rowCount()
        self.repeatability_table.insertRow(row)
        for column, value in enumerate(
            (str(row + 1), "%.4f" % loss_1310, "%.4f" % loss_1550)
        ):
            self.repeatability_table.setItem(row, column, QTableWidgetItem(value))
        self.repeatability_clear_button.setEnabled(True)
        self.repeatability_read_button.setText("Read Next Reading")
        self.repeatability_read_button.setEnabled(self.connected)
        self.read_button.setEnabled(False)
        self.calculate_reference_button.setEnabled(False)
        self._refresh_repeatability_stats()

    def _refresh_repeatability_stats(self):
        if not self.repeatability_readings:
            return
        values_1310 = [reading[0] for reading in self.repeatability_readings]
        values_1550 = [reading[1] for reading in self.repeatability_readings]
        self.repeatability_stats_1310_label.setText(
            self._format_repeatability_stats(values_1310)
        )
        self.repeatability_stats_1550_label.setText(
            self._format_repeatability_stats(values_1550)
        )

    @staticmethod
    def _format_repeatability_stats(values):
        return (
            "High: %.4f | Low: %.4f | Range: %.4f dB"
            % (max(values), min(values), max(values) - min(values))
        )

    def reference_ready(self, reference_1310, reference_1550):
        self._record_support(
            "reference.completed",
            category="measurement",
            reference_1310_dbm=reference_1310,
            reference_1550_dbm=reference_1550,
            both_wavelengths_complete=True,
            status="success",
        )
        self.set_reference_values(reference_1310, reference_1550)
        self.references_changed.emit(reference_1310, reference_1550)
        self._close_reference_progress()
        self.calculate_reference_button.setEnabled(
            self.connected
            and not self.repeatability_active
            and not self.live_updates_active
            and not self.read_pending
        )
        self.read_button.setEnabled(
            self.connected
            and not self.repeatability_active
            and not self.live_updates_active
            and not self.read_pending
        )
        self.live_update_button.setEnabled(
            self.connected and not self.repeatability_active
        )
        self.repeatability_button.setEnabled(
            self.connected and not self.repeatability_active
        )
        self.status_label.setText(
            "Reference calculated and applied. You may edit either value manually."
        )

    def read_il(self):
        if (
            self.worker is not None
            and self.connected
            and not self.repeatability_active
            and not self.read_pending
        ):
            self.read_pending = True
            self.read_requested.emit(
                self.reference_1310_spin.value(),
                self.reference_1550_spin.value(),
            )
            self.read_button.setEnabled(False)
            if not self.live_updates_active:
                self.live_update_button.setEnabled(False)
                self.repeatability_button.setEnabled(False)
            self.status_label.setText("Reading both wavelengths...")

    def reading_ready(self, loss_1310, loss_1550):
        self.read_pending = False
        validation = validate_insertion_loss({1310: loss_1310, 1550: loss_1550})
        method = (
            "repeatability"
            if self.repeatability_read_pending
            else "live_monitoring"
            if self.live_updates_active
            else "manual"
        )
        self._record_support(
            "measurement.two_wavelength_completed",
            reference_1310_dbm=self.reference_1310_spin.value(),
            reference_1550_dbm=self.reference_1550_spin.value(),
            loss_1310_db=loss_1310,
            loss_1550_db=loss_1550,
            acquisition_method=method,
            reading_state="temporary",
            both_wavelengths_complete=True,
            validation_reason=validation.reason,
            invalid_wavelength=",".join(
                str(value) for value in validation.invalid_wavelengths
            ),
            status="success" if validation.valid else "warning",
        )
        self.reading_1310_label.setText("1310 nm IL: %.4f dB" % loss_1310)
        self.reading_1550_label.setText("1550 nm IL: %.4f dB" % loss_1550)
        if self.repeatability_read_pending:
            self.repeatability_read_pending = False
            self._add_repeatability_reading(loss_1310, loss_1550)
            self.status_label.setText(
                "Repeatability reading %d complete. Unplug/reconnect the cable "
                "before the next reading."
                % len(self.repeatability_readings)
            )
        elif self.live_updates_active:
            self.read_button.setEnabled(False)
            self.status_label.setText(
                "Live update complete. Next reading will start shortly."
            )
            self.live_update_timer.start(LIVE_UPDATE_PAUSE_MS)
        else:
            self.read_button.setEnabled(self.connected and not self.repeatability_active)
            self.live_update_button.setEnabled(
                self.connected and not self.repeatability_active
            )
            self.repeatability_button.setEnabled(
                self.connected and not self.repeatability_active
            )
            self.status_label.setText("Reading complete. No data was saved.")
        if not validation.valid:
            self.status_label.setText(
                "Invalid negative loss - check the reference or current connection."
            )

    def _record_support(self, event, *, category="measurement", level="info", **fields):
        if self.support_logger is None:
            return
        try:
            self.support_logger.record(
                category,
                event,
                level=level,
                workflow_id=self.workflow_id,
                workflow_type="live_il",
                **fields,
            )
        except Exception:
            pass

    def reading_failed(self, message):
        self.read_pending = False
        if "below the expected signal level" in str(message):
            self._record_support(
                "reference.failed",
                category="workflow",
                level="error",
                validation_reason="dark_reference",
                threshold_dbm=-40.0,
                error_message=message,
                status="error",
            )
        self._close_reference_progress()
        if self.live_updates_active:
            self.stop_live_updates(update_status=False)
        self.read_button.setEnabled(self.connected and not self.repeatability_active)
        self.calculate_reference_button.setEnabled(
            self.connected and not self.repeatability_active
        )
        self.live_update_button.setEnabled(
            self.connected and not self.repeatability_active
        )
        self.repeatability_button.setEnabled(
            self.connected and not self.repeatability_active
        )
        if self.repeatability_read_pending:
            self.repeatability_read_pending = False
            self.repeatability_read_button.setEnabled(self.connected)
        self.status_label.setText("Reading failed: %s" % message)
        if not self.connected and self.thread is not None:
            self._shutdown_worker()
            self.status_label.setText("Connection failed: %s" % message)

    def stop_meter(self):
        if self.worker is None or self.thread is None:
            return
        self.status_label.setText("Stopping the ILM/OP815...")
        self._shutdown_worker()

    def thread_finished(self):
        self._close_reference_progress()
        self._reset_after_shutdown()
        if self.isVisible():
            self.status_label.setText(
                "Meter released and still connected to Light Workbench."
                if self.uses_persistent_connection
                else "Meter disconnected."
            )

    def closeEvent(self, event):
        if not self._shutdown_worker():
            QMessageBox.warning(
                self,
                "Live IL Reading",
                "The meter is still disconnecting. The dialog will remain open; "
                "please try closing it again after the hardware responds.",
            )
            event.ignore()
            return
        event.accept()

    def _reset_after_shutdown(self):
        """Reset dialog state after the meter thread has fully stopped."""
        self.connected = False
        self.repeatability_active = False
        self.repeatability_read_pending = False
        self.read_pending = False
        self.stop_live_updates(update_status=False)
        self.worker = None
        self.thread = None
        self.start_button.setEnabled(True)
        self.read_button.setEnabled(False)
        self.calculate_reference_button.setEnabled(False)
        self.live_update_button.setEnabled(False)
        self.repeatability_button.setEnabled(False)
        self.repeatability_read_button.setEnabled(False)
        self.repeatability_finish_button.setEnabled(False)
        self.stop_button.setEnabled(False)

    def _shutdown_worker(self) -> bool:
        """Stop the meter thread and wait for remote-mode cleanup to finish."""
        if self.live_controller.worker is None and self.live_controller.thread is None:
            self._reset_after_shutdown()
            return True

        if not self.live_controller.stop_and_wait():
            return False

        self.connected = False
        self._close_reference_progress()
        self._reset_after_shutdown()
        return True

    def _close_reference_progress(self):
        if self.reference_progress is not None:
            self.reference_progress.close()
            self.reference_progress.deleteLater()
            self.reference_progress = None
