"""Background measurement orchestration for the desktop application."""

import threading
from collections.abc import Mapping, Sequence

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


class MeasurementWorker(QObject):
    """Run a channel sequence away from the Qt UI thread.

    The worker owns the instrument lifecycle. The UI receives an
    ``operator_required`` signal after routing each channel and calls
    ``continue_current`` after the operator has moved the cable.
    """

    operator_required = pyqtSignal(int, int)
    channel_selection_required = pyqtSignal(int, object)
    reading_ready = pyqtSignal(int, int, float, float)
    progress_changed = pyqtSignal(int, int)
    completed = pyqtSignal()
    stopped = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        power_meter,
        switch,
        channels: Sequence[int] | None,
        reference_powers: Mapping[int, float],
        manual_channel_order=False,
    ):
        super().__init__()
        self.power_meter = power_meter
        self.switch = switch
        self.channels = list(channels) if channels is not None else None
        self.reference_powers = dict(reference_powers)
        self.manual_channel_order = bool(manual_channel_order)
        self._stop_event = threading.Event()
        self._operator_ready = threading.Event()
        self._channel_selection_event = threading.Event()
        self._decision_event = threading.Event()
        self._decision_lock = threading.Lock()
        self._channel_selection_lock = threading.Lock()
        self._selected_channel = None
        self._decision = None

    @pyqtSlot()
    def run(self):
        try:
            self.switch.connect()
            self.power_meter.connect()
            configured_count = None
            if self.channels is not None:
                channels = list(self.channels)
            else:
                configured_count = self.switch.configured_channel_count()
                channels = list(range(1, configured_count + 1))
            if not channels:
                raise RuntimeError("No channels were selected for measurement.")
            if hasattr(self.switch, "configured_channel_count"):
                configured_count = self.switch.configured_channel_count()
                invalid_channels = [
                    channel for channel in channels
                    if channel < 1 or channel > configured_count
                ]
                if invalid_channels:
                    raise RuntimeError(
                        "Selected channel(s) exceed the OSX-150 configured range "
                        "1-%d: %s"
                        % (configured_count, ", ".join(str(channel) for channel in invalid_channels))
                    )
            if self.manual_channel_order:
                self._run_manual_channel_order(configured_count)
            else:
                self._run_channels(channels)

            self.completed.emit()
        except InterruptedError:
            self.stopped.emit()
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.power_meter.close()
            self.switch.close()

    def _run_channels(self, channels):
        """Run the original ordered channel sequence."""
        total = len(channels)
        for index, channel in enumerate(channels, start=1):
            self._measure_channel(channel, index, total)

    def _run_manual_channel_order(self, configured_count):
        """Let the operator choose channels until every channel is covered."""
        completed_channels = set()

        while True:
            self._channel_selection_event.clear()
            self.channel_selection_required.emit(
                configured_count,
                sorted(completed_channels),
            )
            channel = self._wait_for_channel_selection()
            if channel is None:
                if len(completed_channels) < configured_count:
                    raise RuntimeError(
                        "The manual pass ended before every configured channel "
                        "was measured."
                    )
                return
            if channel < 1 or channel > configured_count:
                raise RuntimeError(
                    "Selected channel must be from 1 through %d." % configured_count
                )

            self._measure_channel(
                channel,
                len(completed_channels) + 1,
                configured_count,
                emit_progress=False,
            )
            completed_channels.add(channel)
            self.progress_changed.emit(
                len(completed_channels),
                configured_count,
            )

    def _measure_channel(self, channel, index, total, emit_progress=True):
        """Route, read, and accept one channel, including repeat reads."""
        self._raise_if_stopped()
        physical_port = self.switch.set_channel(channel)
        self._operator_ready.clear()
        self.operator_required.emit(channel, physical_port)
        self._wait_for_operator()
        self._raise_if_stopped()

        while True:
            measurements = self.power_meter.measure_both_wavelengths()
            loss_1310 = self.reference_powers[1310] - measurements[1310]
            loss_1550 = self.reference_powers[1550] - measurements[1550]
            self.reading_ready.emit(
                channel,
                physical_port,
                loss_1310,
                loss_1550,
            )
            decision = self._wait_for_read_or_write()
            self._raise_if_stopped()
            if decision == "write":
                if emit_progress:
                    self.progress_changed.emit(index, total)
                return

    def _wait_for_channel_selection(self):
        while not self._channel_selection_event.wait(0.1):
            self._raise_if_stopped()
        self._raise_if_stopped()
        with self._channel_selection_lock:
            channel = self._selected_channel
            self._selected_channel = None
            self._channel_selection_event.clear()
        return channel

    @pyqtSlot()
    def continue_current(self):
        self._operator_ready.set()

    @pyqtSlot(int)
    def select_next_channel(self, channel):
        """Release a manual-order wait with the operator's chosen channel."""
        with self._channel_selection_lock:
            self._selected_channel = int(channel)
            self._channel_selection_event.set()

    @pyqtSlot()
    def finish_manual_pass(self):
        """Finish a manual pass after every configured channel is covered."""
        with self._channel_selection_lock:
            self._selected_channel = None
            self._channel_selection_event.set()

    @pyqtSlot()
    def write_current(self):
        self._set_decision("write")

    @pyqtSlot()
    def read_current(self):
        """Request another reading for the currently routed channel."""
        self._set_decision("read")

    @pyqtSlot()
    def stop(self):
        self._stop_event.set()
        self._operator_ready.set()
        self._channel_selection_event.set()
        self._set_decision("write")

    def _wait_for_operator(self):
        while not self._operator_ready.wait(0.1):
            self._raise_if_stopped()

    def _wait_for_read_or_write(self):
        while not self._decision_event.wait(0.1):
            self._raise_if_stopped()
        with self._decision_lock:
            decision = self._decision
            self._decision = None
            self._decision_event.clear()
        return decision

    def _set_decision(self, decision):
        with self._decision_lock:
            self._decision = decision
            self._decision_event.set()

    def _raise_if_stopped(self):
        if self._stop_event.is_set():
            raise InterruptedError()
