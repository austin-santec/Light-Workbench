"""Controller for the real hardware-run lifecycle.

The controller owns the Qt thread and measurement worker. The UI receives
operator-facing signals from this class and sends commands back through queued
signals, so it does not call worker methods across thread boundaries directly.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot

from application.timing import LIVE_WRITE_INTERVAL_SECONDS
from domain.models import RunState
from hardware.interfaces import OpticalSwitch, PowerMeter
from application.measurement_worker import MeasurementWorker


@dataclass(frozen=True)
class HardwareRunRequest:
    """Inputs needed to start one hardware measurement workflow."""

    power_meter_factory: Callable[[], PowerMeter]
    switch_factory: Callable[[], OpticalSwitch]
    channels: Sequence[int] | None
    reference_powers: Mapping[int, float]
    manual_channel_order: bool = False
    existing_channels: Sequence[int] | None = None
    resume_existing: bool = False
    resume_full_pass: bool = False
    live_write_mode: bool = False
    live_write_interval: float = LIVE_WRITE_INTERVAL_SECONDS
    support_logger: object | None = None
    workflow_id: str = ""


class HardwareRunController(QObject):
    """Own one real hardware run and expose a UI-safe command boundary."""

    channel_selection_required = pyqtSignal(int, object)
    continuation_selection_required = pyqtSignal(int, object, int)
    channel_configuration_ready = pyqtSignal(int)
    operator_required = pyqtSignal(int, int)
    reading_ready = pyqtSignal(int, int, float, float)
    progress_changed = pyqtSignal(int, int)
    completed = pyqtSignal()
    stopped = pyqtSignal()
    failed = pyqtSignal(str)
    thread_finished = pyqtSignal()
    state_changed = pyqtSignal(object)
    device_status_changed = pyqtSignal(object)

    # These signals are connected to worker slots after the worker enters its
    # thread. Qt queues UI commands safely into the worker thread.
    _continue_requested = pyqtSignal()
    _read_requested = pyqtSignal()
    _write_requested = pyqtSignal()
    _select_next_requested = pyqtSignal(int)
    _select_resume_requested = pyqtSignal(int)
    _change_requested = pyqtSignal(int, bool)
    _finish_manual_requested = pyqtSignal()
    _stop_requested = pyqtSignal()

    def __init__(self, parent=None, worker_factory=MeasurementWorker):
        super().__init__(parent)
        self.worker_factory = worker_factory
        self.thread: QThread | None = None
        self.worker: QObject | None = None
        self.state = RunState.IDLE
        self._live_write_mode = False
        self._command_connections: list[tuple[Any, Any]] = []

    @property
    def is_active(self) -> bool:
        """Whether this controller still owns a worker or its thread."""
        return self.worker is not None or self.thread is not None

    def _set_state(self, state: RunState) -> None:
        if self.state == state:
            return
        self.state = state
        self.state_changed.emit(state)

    def start(self, request: HardwareRunRequest) -> None:
        """Create and start the worker for one requested hardware run."""
        if self.is_active:
            raise RuntimeError("A hardware run is already active.")

        self._live_write_mode = bool(request.live_write_mode)
        self._set_state(RunState.STARTING)
        meter = None
        switch = None
        worker = None
        thread = None
        try:
            meter = request.power_meter_factory()
            switch = request.switch_factory()
            worker = self.worker_factory(
                meter,
                switch,
                request.channels,
                request.reference_powers,
                manual_channel_order=request.manual_channel_order,
                existing_channels=request.existing_channels,
                resume_existing=request.resume_existing,
                resume_full_pass=request.resume_full_pass,
                live_write_mode=request.live_write_mode,
                live_write_interval=request.live_write_interval,
                support_logger=request.support_logger,
                workflow_id=request.workflow_id,
            )
            thread = QThread(self)
            worker.moveToThread(thread)
            self.worker = worker
            self.thread = thread
            self._connect_worker(worker, thread)
            thread.started.connect(worker.run)
            thread.start()
        except Exception:
            # Release adapters if setup fails before the worker can run. This
            # matters when a Qt connection or thread allocation fails after
            # the worker has been constructed but before thread.start().
            devices = (
                (getattr(worker, "power_meter", None), getattr(worker, "switch", None))
                if worker is not None
                else (meter, switch)
            )
            for device in devices:
                if device is not None:
                    try:
                        device.close()
                    except Exception:
                        pass
            if thread is not None and not thread.isRunning():
                thread.deleteLater()
            self.worker = None
            self.thread = None
            self._set_state(RunState.IDLE)
            raise

    def _connect_worker(self, worker: QObject, thread: QThread) -> None:
        worker.channel_selection_required.connect(self._relay_channel_selection)
        worker.continuation_selection_required.connect(
            self._relay_continuation_selection
        )
        worker.channel_configuration_ready.connect(
            self.channel_configuration_ready
        )
        worker.operator_required.connect(self._relay_operator_required)
        worker.reading_ready.connect(self._relay_reading_ready)
        worker.progress_changed.connect(self.progress_changed)
        worker.device_status_changed.connect(self.device_status_changed)
        worker.completed.connect(self._worker_completed)
        worker.stopped.connect(self._worker_stopped)
        worker.failed.connect(self._worker_failed)
        worker.completed.connect(thread.quit)
        worker.stopped.connect(thread.quit)
        worker.failed.connect(thread.quit)

        command_connections = [
            (self._continue_requested, worker.continue_current),
            (self._read_requested, worker.read_current),
            (self._write_requested, worker.write_current),
            (self._select_next_requested, worker.select_next_channel),
            (self._select_resume_requested, worker.select_resume_channel),
            (self._change_requested, worker.change_channel),
            (self._finish_manual_requested, worker.finish_manual_pass),
            (self._stop_requested, worker.stop),
        ]
        for signal, slot in command_connections:
            # MeasurementWorker.run intentionally blocks on threading.Event
            # objects. Its command slots only set those thread-safe events,
            # so direct delivery is required while its event loop is busy.
            signal.connect(slot, type=Qt.DirectConnection)
        self._command_connections = command_connections
        thread.finished.connect(self._thread_finished)

    def _relay_channel_selection(self, channel_count, completed_channels):
        self._set_state(RunState.WAITING_FOR_CABLE)
        self.channel_selection_required.emit(channel_count, completed_channels)

    def _relay_continuation_selection(
        self,
        channel_count,
        completed_channels,
        default_channel,
    ):
        self._set_state(RunState.WAITING_FOR_CABLE)
        self.continuation_selection_required.emit(
            channel_count,
            completed_channels,
            default_channel,
        )

    def _relay_operator_required(self, channel, physical_port):
        self._set_state(RunState.WAITING_FOR_CABLE)
        self.operator_required.emit(channel, physical_port)

    def _relay_reading_ready(self, channel, physical_port, loss_1310, loss_1550):
        self._set_state(
            RunState.READING if self._live_write_mode else RunState.READY_TO_WRITE
        )
        self.reading_ready.emit(channel, physical_port, loss_1310, loss_1550)

    def _worker_completed(self):
        self._set_state(RunState.COMPLETED)
        self.completed.emit()

    def _worker_stopped(self):
        self._set_state(RunState.STOPPED)
        self.stopped.emit()

    def _worker_failed(self, message):
        self._set_state(RunState.FAILED)
        self.failed.emit(message)

    def _disconnect_commands(self) -> None:
        for signal, slot in self._command_connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._command_connections = []

    @pyqtSlot()
    def _thread_finished(self):
        # Do not call worker.deleteLater() after the worker thread's event loop
        # has stopped. This preserves the shutdown ordering that avoids native
        # Qt crashes with the vendor hardware DLL.
        self._disconnect_commands()
        thread = self.thread
        self.worker = None
        self.thread = None
        self._set_state(RunState.IDLE)
        if thread is not None:
            thread.deleteLater()
        self.thread_finished.emit()

    def _invoke_command(self, signal, *args) -> None:
        if self.worker is not None:
            signal.emit(*args)

    def continue_current(self) -> None:
        self._invoke_command(self._continue_requested)

    def read_current(self) -> None:
        self._invoke_command(self._read_requested)

    def select_next_channel(self, channel: int) -> None:
        self._invoke_command(self._select_next_requested, int(channel))

    def select_resume_channel(self, channel: int) -> None:
        self._invoke_command(self._select_resume_requested, int(channel))

    def change_channel(self, channel: int, resume_interrupted: bool = False) -> None:
        self._invoke_command(
            self._change_requested,
            int(channel),
            bool(resume_interrupted),
        )

    def finish_manual_pass(self) -> None:
        self._invoke_command(self._finish_manual_requested)

    def write_current(self) -> None:
        self._set_state(RunState.WRITING)
        self._invoke_command(self._write_requested)

    def stop(self) -> None:
        if self.worker is not None:
            self._set_state(RunState.STOPPING)
            self._invoke_command(self._stop_requested)

    def stop_and_wait(self, timeout_ms: int = 5000) -> bool:
        """Request stop and wait during application shutdown."""
        self.stop()
        if self.thread is None:
            return True
        return self.thread.wait(timeout_ms)
