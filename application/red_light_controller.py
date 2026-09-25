"""Application controller for the switch-only Red Light Test."""

from collections.abc import Callable

from PyQt5.QtCore import QMetaObject, QObject, QThread, Qt, pyqtSignal, pyqtSlot

from domain.models import RunState
from hardware.interfaces import OpticalSwitch
from hardware.session import OpticalTestSession


class RedLightTestWorker(QObject):
    """Perform switch I/O away from the Red Light Test dialog thread."""

    connected = pyqtSignal(int)
    channel_selected = pyqtSignal(int, int)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, switch: OpticalSwitch):
        super().__init__()
        self.switch = switch
        self.hardware_session = OpticalTestSession(None, switch=switch)
        self._finished = False

    @pyqtSlot()
    def start(self):
        try:
            self.hardware_session.connect()
            channel_count = self.switch.configured_channel_count()
            if channel_count < 1:
                raise RuntimeError("The switch reported no usable channels.")
            self.connected.emit(channel_count)
        except Exception as error:
            self.failed.emit(str(error))
            self.stop()

    @pyqtSlot(int)
    def select_channel(self, channel):
        if self._finished:
            return
        try:
            physical_port = self.switch.set_channel(int(channel))
            self.channel_selected.emit(int(channel), int(physical_port))
        except Exception as error:
            self.failed.emit("Could not select channel %d: %s" % (channel, error))

    @pyqtSlot()
    def stop(self):
        if self._finished:
            return
        self._finished = True
        try:
            self.hardware_session.close()
        except Exception as error:
            self.failed.emit("Switch disconnect failed: %s" % error)
        finally:
            self.finished.emit()


class RedLightTestController(QObject):
    """Own the Red Light Test switch worker and thread."""

    connected = pyqtSignal(int)
    channel_selected = pyqtSignal(int, int)
    failed = pyqtSignal(str)
    finished = pyqtSignal()
    thread_finished = pyqtSignal()
    state_changed = pyqtSignal(object)

    channel_requested = pyqtSignal(int)

    def __init__(self, parent=None, worker_factory=RedLightTestWorker):
        super().__init__(parent)
        self.worker_factory = worker_factory
        self.thread: QThread | None = None
        self.worker: QObject | None = None
        self.switch: OpticalSwitch | None = None
        self.state = RunState.IDLE

    def _set_state(self, state: RunState) -> None:
        if self.state == state:
            return
        self.state = state
        self.state_changed.emit(state)

    def start(self, switch_factory: Callable[[], OpticalSwitch]) -> None:
        if self.thread is not None or self.worker is not None:
            raise RuntimeError("The Red Light Test is already active.")

        switch = None
        thread = None
        worker = None
        self._set_state(RunState.STARTING)
        try:
            switch = switch_factory()
            worker = self.worker_factory(switch)
            thread = QThread(self)
            worker.moveToThread(thread)
            self.worker = worker
            self.thread = thread
            self.switch = switch
            worker.connected.connect(self._relay_connected)
            worker.channel_selected.connect(self._relay_channel_selected)
            worker.failed.connect(self._relay_failed)
            worker.finished.connect(self._worker_finished)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            self.channel_requested.connect(
                worker.select_channel,
                type=Qt.QueuedConnection,
            )
            thread.started.connect(worker.start)
            thread.finished.connect(self._thread_finished)
            thread.start()
        except Exception:
            if worker is None and switch is not None:
                try:
                    switch.close()
                except Exception:
                    pass
            self.worker = None
            self.thread = None
            self.switch = None
            if thread is not None and not thread.isRunning():
                thread.deleteLater()
            self._set_state(RunState.IDLE)
            raise

    def _relay_connected(self, channel_count):
        self._set_state(RunState.WAITING_FOR_CABLE)
        self.connected.emit(channel_count)

    def _relay_channel_selected(self, channel, physical_port):
        self._set_state(RunState.WAITING_FOR_CABLE)
        self.channel_selected.emit(channel, physical_port)

    def _relay_failed(self, message):
        self._set_state(RunState.FAILED)
        self.failed.emit(message)

    def _worker_finished(self):
        self._set_state(RunState.STOPPED)
        self.finished.emit()

    @pyqtSlot()
    def _thread_finished(self):
        if self.thread is None:
            return
        thread = self.thread
        self.worker = None
        self.thread = None
        self.switch = None
        self._set_state(RunState.IDLE)
        thread.deleteLater()
        self.thread_finished.emit()

    def select_channel(self, channel: int) -> None:
        if self.worker is not None:
            self.channel_requested.emit(int(channel))

    def stop_and_wait(self, timeout_ms: int = 5000) -> bool:
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

        if not thread.isRunning() and self.thread is thread:
            self._thread_finished()
        return stopped
