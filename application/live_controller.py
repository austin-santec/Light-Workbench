"""Application controller for meter-only Live IL reading."""

from collections.abc import Callable

from PyQt5.QtCore import QMetaObject, QObject, QThread, Qt, pyqtSignal, pyqtSlot

from domain.models import RunState
from hardware.interfaces import PowerMeter


class LiveILReadingController(QObject):
    """Own a Live IL meter worker and its thread lifecycle."""

    connected = pyqtSignal(str)
    reading_ready = pyqtSignal(float, float)
    reference_ready = pyqtSignal(float, float)
    failed = pyqtSignal(str)
    finished = pyqtSignal()
    thread_finished = pyqtSignal()
    state_changed = pyqtSignal(object)

    read_requested = pyqtSignal(float, float)
    reference_requested = pyqtSignal()

    def __init__(self, parent=None, worker_factory: Callable[[PowerMeter], QObject] | None = None):
        super().__init__(parent)
        self.worker_factory = worker_factory
        self.thread: QThread | None = None
        self.worker: QObject | None = None
        self.state = RunState.IDLE
        self._command_connections = []

    def _set_state(self, state: RunState) -> None:
        if self.state == state:
            return
        self.state = state
        self.state_changed.emit(state)

    def start(self, meter_factory: Callable[[], PowerMeter], measurement_configuration=None) -> None:
        """Create the meter worker and begin connection asynchronously."""
        if self.thread is not None or self.worker is not None:
            raise RuntimeError("Live IL reading is already active.")
        if self.worker_factory is None:
            raise RuntimeError("No Live IL worker factory was configured.")

        meter = None
        thread = None
        worker = None
        self._set_state(RunState.STARTING)
        try:
            meter = meter_factory()
            worker = (
                self.worker_factory(
                    meter,
                    measurement_configuration_value=measurement_configuration,
                )
                if measurement_configuration is not None
                else self.worker_factory(meter)
            )
            thread = QThread(self)
            worker.moveToThread(thread)
            self.worker = worker
            self.thread = thread
            worker.connected.connect(self._relay_connected)
            worker.reading_ready.connect(self._relay_reading)
            worker.reference_ready.connect(self._relay_reference)
            worker.failed.connect(self._relay_failed)
            worker.finished.connect(self._worker_finished)
            worker.finished.connect(thread.quit)
            self.read_requested.connect(
                worker.read,
                type=Qt.QueuedConnection,
            )
            self.reference_requested.connect(
                worker.calculate_reference,
                type=Qt.QueuedConnection,
            )
            self._command_connections = [
                (self.read_requested, worker.read),
                (self.reference_requested, worker.calculate_reference),
            ]
            thread.started.connect(worker.start)
            thread.finished.connect(self._thread_finished)
            thread.start()
        except Exception:
            self._disconnect_commands()
            if worker is None and meter is not None:
                try:
                    meter.close()
                except Exception:
                    pass
            self.worker = None
            self.thread = None
            if thread is not None and not thread.isRunning():
                thread.deleteLater()
            self._set_state(RunState.IDLE)
            raise

    def _relay_connected(self, description):
        self._set_state(RunState.READING)
        self.connected.emit(description)

    def _relay_reading(self, loss_1310, loss_1550):
        self._set_state(RunState.READING)
        self.reading_ready.emit(loss_1310, loss_1550)

    def _relay_reference(self, reference_1310, reference_1550):
        self._set_state(RunState.READING)
        self.reference_ready.emit(reference_1310, reference_1550)

    def _relay_failed(self, message):
        self._set_state(RunState.FAILED)
        self.failed.emit(message)

    def _worker_finished(self):
        self._set_state(RunState.STOPPED)
        self.finished.emit()

    def _disconnect_commands(self) -> None:
        """Disconnect queued UI commands before releasing the worker."""
        for signal, slot in self._command_connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._command_connections = []

    @pyqtSlot()
    def _thread_finished(self):
        if self.thread is None:
            return
        thread = self.thread
        # Do not call worker.deleteLater() after the worker thread's event
        # loop has stopped. Deferred deletion at that point can race with
        # vendor-session cleanup and trigger a native Qt abort.
        self._disconnect_commands()
        self.worker = None
        self.thread = None
        self._set_state(RunState.IDLE)
        thread.deleteLater()
        self.thread_finished.emit()

    def read(self, reference_1310: float, reference_1550: float) -> None:
        if self.worker is not None:
            self.read_requested.emit(float(reference_1310), float(reference_1550))

    def calculate_reference(self) -> None:
        if self.worker is not None:
            self.reference_requested.emit()

    def stop_and_wait(self, timeout_ms: int = 5000) -> bool:
        """Stop the worker, wait for meter cleanup, and release references."""
        worker = self.worker
        thread = self.thread
        if worker is None or thread is None:
            return True

        self._set_state(RunState.STOPPING)
        if thread.isRunning():
            QMetaObject.invokeMethod(worker, "stop", Qt.BlockingQueuedConnection)
            thread.quit()
            stopped = thread.wait(timeout_ms)
        else:
            worker.stop()
            stopped = True

        if stopped and not thread.isRunning() and self.thread is thread:
            self._thread_finished()
        return stopped
