"""Application controller for raw power and insertion-loss diagnostics."""

from collections.abc import Callable

from PyQt5.QtCore import QMetaObject, QObject, QThread, Qt, pyqtSignal, pyqtSlot

from domain.measurement import calculate_insertion_loss
from domain.reference import calculate_reference_offsets
from hardware.interfaces import PowerMeter
from hardware.session import OpticalTestSession


class PowerDiagnosticsWorker(QObject):
    """Read absolute meter power away from the Qt UI thread."""

    connected = pyqtSignal(str)
    reading_ready = pyqtSignal(object, float, float, float, float)
    reference_ready = pyqtSignal(object, float, float)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, meter: PowerMeter):
        super().__init__()
        self.meter = meter
        self.hardware_session = OpticalTestSession(meter)
        self._finished = False

    @pyqtSlot()
    def start(self):
        try:
            self.hardware_session.connect()
            self.connected.emit(self.meter.description or "Power meter connected")
        except Exception as error:
            # Keep the worker alive long enough for the controller to perform
            # orderly vendor-session cleanup after a failed connection.
            self.failed.emit(str(error))

    @pyqtSlot(float, float, object, object, object, object)
    def read(
        self,
        reference_1310: float,
        reference_1550: float,
        measurement_id=None,
        method=None,
        channel=None,
        physical_port=None,
    ):
        if self._finished:
            return
        try:
            self._set_trace_context(
                measurement_id=measurement_id,
                method=method,
                channel=channel,
                physical_port=physical_port,
                reference_1310_dbm=float(reference_1310),
                reference_1550_dbm=float(reference_1550),
            )
            measured = dict(self.meter.measure_both_wavelengths())
            losses = calculate_insertion_loss(
                {1310: reference_1310, 1550: reference_1550},
                measured,
            )
            self.reading_ready.emit(
                measured,
                float(reference_1310),
                float(reference_1550),
                losses[1310],
                losses[1550],
            )
        except Exception as error:
            self.failed.emit(str(error))

    @pyqtSlot(object)
    def calculate_reference(self, reference_id=None):
        if self._finished:
            return
        try:
            self._set_trace_context(
                measurement_id=reference_id,
                method="Reference",
            )
            measured = dict(self.meter.measure_reference_wavelengths())
            reference_1310, reference_1550 = calculate_reference_offsets(measured)
            self.reference_ready.emit(
                measured,
                reference_1310,
                reference_1550,
            )
        except Exception as error:
            self.failed.emit(str(error))

    def _set_trace_context(self, **values):
        setter = getattr(self.meter, "set_trace_context", None)
        if setter is not None:
            try:
                setter(**values)
            except Exception:
                # Tracing is optional and must not turn a usable meter into a
                # failed diagnostic measurement.
                return

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
            close_error = error
        finally:
            self.finished.emit()
        if close_error:
            self.failed.emit("Meter disconnect failed: %s" % close_error)


class PowerDiagnosticsController(QObject):
    """Own the diagnostic meter worker and its cleanup lifecycle."""

    connected = pyqtSignal(str)
    reading_ready = pyqtSignal(object, float, float, float, float)
    reference_ready = pyqtSignal(object, float, float)
    failed = pyqtSignal(str)
    finished = pyqtSignal()
    thread_finished = pyqtSignal()

    read_requested = pyqtSignal(float, float, object, object, object, object)
    reference_requested = pyqtSignal(object)

    def __init__(
        self,
        parent=None,
        worker_factory: Callable[[PowerMeter], QObject] | None = None,
        trace_callback=None,
        trace_metadata=None,
    ):
        super().__init__(parent)
        self.worker_factory = worker_factory or PowerDiagnosticsWorker
        self.thread: QThread | None = None
        self.worker: QObject | None = None
        self._command_connections = []
        self.trace_callback = trace_callback
        self.trace_metadata = dict(trace_metadata or {})

    def start(self, meter_factory: Callable[[], PowerMeter]) -> None:
        """Create the worker and connect the meter asynchronously."""
        if self.thread is not None or self.worker is not None:
            raise RuntimeError("Power diagnostics meter is already active.")

        meter = None
        worker = None
        thread = None
        try:
            meter = meter_factory()
            if self.trace_callback is not None:
                setter = getattr(meter, "set_trace_callback", None)
                if setter is not None:
                    try:
                        setter(self.trace_callback)
                    except Exception:
                        pass
            if self.trace_metadata:
                setter = getattr(meter, "set_trace_metadata", None)
                if setter is not None:
                    try:
                        setter(**self.trace_metadata)
                    except Exception:
                        pass
            worker = self.worker_factory(meter)
            thread = QThread(self)
            worker.moveToThread(thread)
            self.worker = worker
            self.thread = thread
            worker.connected.connect(self.connected)
            worker.reading_ready.connect(self.reading_ready)
            worker.reference_ready.connect(self.reference_ready)
            worker.failed.connect(self.failed)
            worker.finished.connect(self.finished)
            worker.finished.connect(thread.quit)
            self.read_requested.connect(worker.read, type=Qt.QueuedConnection)
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
            raise

    def _disconnect_commands(self):
        for signal, slot in self._command_connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._command_connections = []

    def read(
        self,
        reference_1310: float,
        reference_1550: float,
        measurement_id=None,
        method=None,
        channel=None,
        physical_port=None,
    ) -> None:
        if self.worker is not None:
            self.read_requested.emit(
                float(reference_1310),
                float(reference_1550),
                measurement_id,
                method,
                channel,
                physical_port,
            )

    def calculate_reference(self, reference_id=None) -> None:
        if self.worker is not None:
            self.reference_requested.emit(reference_id)

    def stop_and_wait(self, timeout_ms: int = 5000) -> bool:
        """Stop the meter and wait for vendor cleanup in its worker thread."""
        worker = self.worker
        thread = self.thread
        if worker is None or thread is None:
            return True

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

    @pyqtSlot()
    def _thread_finished(self):
        if self.thread is None:
            return
        thread = self.thread
        self._disconnect_commands()
        self.worker = None
        self.thread = None
        thread.deleteLater()
        self.thread_finished.emit()


__all__ = ["PowerDiagnosticsController", "PowerDiagnosticsWorker"]
