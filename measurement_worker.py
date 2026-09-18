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
    channel_configuration_ready = pyqtSignal(int)
    continuation_selection_required = pyqtSignal(int, object, int)
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
        existing_channels: Sequence[int] | None = None,
        resume_existing=False,
        resume_full_pass=False,
    ):
        super().__init__()
        self.power_meter = power_meter
        self.switch = switch
        self.channels = list(channels) if channels is not None else None
        self.reference_powers = dict(reference_powers)
        self.manual_channel_order = bool(manual_channel_order)
        self.existing_channels = set(existing_channels or ())
        self.resume_existing = bool(resume_existing)
        self.resume_full_pass = bool(resume_full_pass)
        self._stop_event = threading.Event()
        self._operator_ready = threading.Event()
        self._channel_selection_event = threading.Event()
        self._continuation_selection_event = threading.Event()
        self._decision_event = threading.Event()
        self._decision_lock = threading.Lock()
        self._channel_selection_lock = threading.Lock()
        self._continuation_selection_lock = threading.Lock()
        self._channel_change_lock = threading.Lock()
        self._selected_channel = None
        self._continuation_channel = None
        self._channel_change_request = None
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
            if configured_count is None:
                configured_count = max(channels)
            self.channel_configuration_ready.emit(configured_count)
            if self.manual_channel_order:
                self._run_manual_channel_order(
                    configured_count,
                    self.existing_channels if self.resume_existing else None,
                )
            else:
                start_channel = None
                if self.resume_existing and self.resume_full_pass:
                    default_channel = self._first_uncompleted_channel(
                        channels,
                        self.existing_channels,
                    ) or channels[0]
                    self.continuation_selection_required.emit(
                        configured_count,
                        sorted(self.existing_channels),
                        default_channel,
                    )
                    start_channel = self._wait_for_continuation_selection()
                self._run_channels(
                    channels,
                    self.existing_channels if self.resume_existing else None,
                    start_channel,
                )

            self.completed.emit()
        except InterruptedError:
            self.stopped.emit()
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.power_meter.close()
            self.switch.close()

    def _run_channels(self, channels, existing_channels=None, start_channel=None):
        """Run channels while allowing safe mid-run channel overrides."""
        all_channels = list(channels)
        completed_channels = set(existing_channels or ())
        completed_channels.intersection_update(all_channels)
        if start_channel is None:
            current_channel = self._first_uncompleted_channel(
                all_channels,
                completed_channels,
            )
        else:
            current_channel = int(start_channel)

        while current_channel is not None:
            resume_channel = None
            while True:
                change = self._measure_channel(
                    current_channel,
                    emit_progress=False,
                )
                if change is None:
                    completed_channels.add(current_channel)
                    self.progress_changed.emit(
                        len(completed_channels),
                        len(all_channels),
                    )
                    break

                target_channel = change["channel"]
                if target_channel not in all_channels:
                    all_channels.append(target_channel)
                if change["resume_interrupted"]:
                    resume_channel = current_channel
                else:
                    resume_channel = None
                current_channel = target_channel

            if len(completed_channels) >= len(all_channels):
                return
            if resume_channel is not None and resume_channel not in completed_channels:
                current_channel = resume_channel
            else:
                current_channel = self._next_uncompleted_channel(
                    current_channel,
                    all_channels,
                    completed_channels,
                )

    def _run_manual_channel_order(self, configured_count, existing_channels=None):
        """Let the operator choose channels until every channel is covered."""
        completed_channels = set(existing_channels or ())
        completed_channels = {
            channel
            for channel in completed_channels
            if 1 <= channel <= configured_count
        }

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

            while True:
                change = self._measure_channel(channel, emit_progress=False)
                if change is None:
                    break
                channel = change["channel"]
            completed_channels.add(channel)
            self.progress_changed.emit(
                len(completed_channels),
                configured_count,
            )

    def _measure_channel(self, channel, index=None, total=None, emit_progress=True):
        """Route, read, and accept one channel, including repeat reads."""
        self._raise_if_stopped()
        physical_port = self.switch.set_channel(channel)
        self._operator_ready.clear()
        self.operator_required.emit(channel, physical_port)
        change = self._wait_for_operator()
        if change is not None:
            return change
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
            if isinstance(decision, dict):
                return decision
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

    def _next_uncompleted_channel(self, current_channel, all_channels, completed_channels):
        """Return the next uncompleted channel after the supplied channel."""
        start_index = all_channels.index(current_channel)
        for offset in range(1, len(all_channels) + 1):
            candidate = all_channels[(start_index + offset) % len(all_channels)]
            if candidate not in completed_channels:
                return candidate
        return None

    @staticmethod
    def _first_uncompleted_channel(all_channels, completed_channels):
        for channel in all_channels:
            if channel not in completed_channels:
                return channel
        return None

    @pyqtSlot()
    def continue_current(self):
        self._operator_ready.set()

    @pyqtSlot(int)
    def select_next_channel(self, channel):
        """Release a manual-order wait with the operator's chosen channel."""
        with self._channel_selection_lock:
            self._selected_channel = int(channel)
            self._channel_selection_event.set()

    @pyqtSlot(int)
    def select_resume_channel(self, channel):
        """Set the first channel for a resumed ordered pass."""
        with self._continuation_selection_lock:
            self._continuation_channel = int(channel)
            self._continuation_selection_event.set()

    @pyqtSlot(int, bool)
    def change_channel(self, channel, resume_interrupted=False):
        """Replace the current uncommitted step with another channel."""
        with self._channel_change_lock:
            self._channel_change_request = {
                "channel": int(channel),
                "resume_interrupted": bool(resume_interrupted),
            }
        # Wake whichever operator decision is currently blocking. The worker
        # consumes the request before it takes another measurement.
        self._operator_ready.set()
        self._set_decision("change")

    @pyqtSlot()
    def finish_manual_pass(self):
        """Finish a manual pass after every configured channel is covered."""
        with self._channel_selection_lock:
            self._selected_channel = None
            self._channel_selection_event.set()

    def _wait_for_continuation_selection(self):
        while not self._continuation_selection_event.wait(0.1):
            self._raise_if_stopped()
        self._raise_if_stopped()
        with self._continuation_selection_lock:
            channel = self._continuation_channel
            self._continuation_channel = None
            self._continuation_selection_event.clear()
        return channel

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
        self._continuation_selection_event.set()
        self._set_decision("write")

    def _wait_for_operator(self):
        while not self._operator_ready.wait(0.1):
            self._raise_if_stopped()
        return self._take_channel_change()

    def _wait_for_read_or_write(self):
        while not self._decision_event.wait(0.1):
            self._raise_if_stopped()
        with self._decision_lock:
            decision = self._decision
            self._decision = None
            self._decision_event.clear()
        if decision == "change":
            return self._take_channel_change()
        return decision

    def _take_channel_change(self):
        with self._channel_change_lock:
            request = self._channel_change_request
            self._channel_change_request = None
        if request is not None:
            # A change requested while waiting for cable placement wakes both
            # wait events. Remove the unused decision so it cannot affect the
            # next channel.
            with self._decision_lock:
                if self._decision == "change":
                    self._decision = None
                    self._decision_event.clear()
        return request

    def _set_decision(self, decision):
        with self._decision_lock:
            self._decision = decision
            self._decision_event.set()

    def _raise_if_stopped(self):
        if self._stop_event.is_set():
            raise InterruptedError()
