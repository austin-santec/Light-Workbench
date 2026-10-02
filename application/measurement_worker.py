"""Background measurement orchestration for the desktop application."""

import threading
import time
import uuid
from collections.abc import Mapping, Sequence

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from application.timing import LIVE_WRITE_INTERVAL_SECONDS
from domain.measurement import calculate_insertion_loss
from domain.models import ConnectionState, DeviceCategory
from domain.support_events import SupportEventCategory, SupportLogLevel
from hardware.device_identity import device_info_for
from hardware.interfaces import OpticalSwitch, PowerMeter
from hardware.session import OpticalTestSession


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
    device_status_changed = pyqtSignal(object)

    def __init__(
        self,
        power_meter: PowerMeter,
        switch: OpticalSwitch,
        channels: Sequence[int] | None,
        reference_powers: Mapping[int, float],
        manual_channel_order=False,
        existing_channels: Sequence[int] | None = None,
        resume_existing=False,
        resume_full_pass=False,
        live_write_mode=False,
        live_write_interval=LIVE_WRITE_INTERVAL_SECONDS,
        support_logger=None,
        workflow_id="",
    ):
        super().__init__()
        self.power_meter = power_meter
        self.switch = switch
        self.hardware_session = OpticalTestSession(power_meter, switch=switch)
        self.channels = list(channels) if channels is not None else None
        self.reference_powers = dict(reference_powers)
        self.manual_channel_order = bool(manual_channel_order)
        self.existing_channels = set(existing_channels or ())
        self.resume_existing = bool(resume_existing)
        self.resume_full_pass = bool(resume_full_pass)
        self.live_write_mode = bool(live_write_mode)
        self.live_write_interval = max(0.1, float(live_write_interval))
        self.support_logger = support_logger
        self.workflow_id = str(workflow_id or "")
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
        terminal_state = None
        terminal_message = None
        try:
            self._record(
                SupportEventCategory.WORKFLOW,
                "run.worker_started",
                live_write_mode=self.live_write_mode,
                status="started",
            )
            self._emit_device_status(ConnectionState.CONNECTING)
            self.hardware_session.connect()
            self._emit_device_status(ConnectionState.CONNECTED)
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
                    channel
                    for channel in channels
                    if channel < 1 or channel > configured_count
                ]
                if invalid_channels:
                    raise RuntimeError(
                        "Selected channel(s) exceed the OSX-150 configured range "
                        "1-%d: %s"
                        % (
                            configured_count,
                            ", ".join(str(channel) for channel in invalid_channels),
                        )
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

            terminal_state = "completed"
        except InterruptedError:
            terminal_state = "stopped"
        except Exception as error:
            terminal_state = "failed"
            terminal_message = str(error)
            self._record(
                SupportEventCategory.WORKFLOW,
                "run.worker_failed",
                level=SupportLogLevel.ERROR,
                error_type=type(error).__name__,
                error_message=str(error),
                status="error",
            )
        finally:
            # Do not notify the UI that the worker has completed until both
            # instruments have been released. The previous ordering emitted
            # the terminal signal first, allowing QThread cleanup and queued
            # UI callbacks to race with the worker's native-driver teardown.
            cleanup_error = None
            try:
                self.hardware_session.close()
            except Exception as error:
                cleanup_error = str(error)
            if cleanup_error:
                if terminal_state == "completed":
                    terminal_state = "failed"
                    terminal_message = "Could not close hardware cleanly: %s" % cleanup_error
                elif terminal_state == "failed":
                    terminal_message = "%s (cleanup: %s)" % (
                        terminal_message,
                        cleanup_error,
                    )

            final_state = (
                ConnectionState.ERROR
                if terminal_state == "failed"
                else ConnectionState.DISCONNECTED
            )
            self._emit_device_status(final_state, terminal_message or "")

        # Terminal signals are intentionally emitted after the finally block
        # so the UI never starts thread shutdown while a device close is still
        # executing in the worker thread.
        if terminal_state == "completed":
            self._record(
                SupportEventCategory.WORKFLOW,
                "run.worker_completed",
                status="success",
            )
            self.completed.emit()
        elif terminal_state == "stopped":
            self._record(
                SupportEventCategory.WORKFLOW,
                "run.worker_stopped",
                status="stopped",
            )
            self.stopped.emit()
        elif terminal_state == "failed":
            self.failed.emit(terminal_message or "Hardware worker failed.")

    def _emit_device_status(self, state, error=""):
        """Publish transient identities without coupling the worker to Qt UI."""
        self.device_status_changed.emit(
            device_info_for(
                self.power_meter,
                DeviceCategory.POWER_METER,
                state=state,
                error=error,
            )
        )
        self.device_status_changed.emit(
            device_info_for(
                self.switch,
                DeviceCategory.OPTICAL_SWITCH,
                state=state,
                error=error,
            )
        )

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
        route_started = time.perf_counter()
        physical_port = self.switch.set_channel(channel)
        self._record(
            SupportEventCategory.HARDWARE,
            "switch.channel_routed",
            logical_channel=channel,
            physical_port=physical_port,
            elapsed_ms=(time.perf_counter() - route_started) * 1000.0,
            status="success",
        )
        self._operator_ready.clear()
        self.operator_required.emit(channel, physical_port)
        if not self.live_write_mode:
            change = self._wait_for_operator()
            if change is not None:
                return change
        self._raise_if_stopped()

        while True:
            measurement_id = "measurement-" + uuid.uuid4().hex
            self._set_meter_trace_context(
                workflow_id=self.workflow_id,
                operation_id=measurement_id,
                measurement_id=measurement_id,
                method="live_write" if self.live_write_mode else "normal_run",
                channel=channel,
                physical_port=physical_port,
                reference_1310_dbm=self.reference_powers.get(1310),
                reference_1550_dbm=self.reference_powers.get(1550),
            )
            started = time.perf_counter()
            measurements = self.power_meter.measure_both_wavelengths()
            losses = calculate_insertion_loss(self.reference_powers, measurements)
            self._record(
                SupportEventCategory.MEASUREMENT,
                "measurement.two_wavelength_completed",
                operation_id=measurement_id,
                logical_channel=channel,
                physical_port=physical_port,
                measured_power_dbm={
                    "1310": measurements[1310],
                    "1550": measurements[1550],
                },
                reference_1310_dbm=self.reference_powers.get(1310),
                reference_1550_dbm=self.reference_powers.get(1550),
                loss_1310_db=losses[1310],
                loss_1550_db=losses[1550],
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                reading_state="temporary",
                both_wavelengths_complete=True,
                acquisition_method=("live_write" if self.live_write_mode else "normal_run"),
                status="success",
            )
            self.reading_ready.emit(
                channel,
                physical_port,
                losses[1310],
                losses[1550],
            )
            decision = self._wait_for_read_or_write(
                live_update=self.live_write_mode
            )
            self._raise_if_stopped()
            if isinstance(decision, dict):
                return decision
            if decision == "live_update":
                continue
            if decision == "write":
                self._record(
                    SupportEventCategory.OPERATOR,
                    "measurement.write_requested",
                    operation_id=measurement_id,
                    logical_channel=channel,
                    physical_port=physical_port,
                    reading_state="accepted_pending_persistence",
                    status="requested",
                )
                if emit_progress:
                    self.progress_changed.emit(index, total)
                return

            self._record(
                SupportEventCategory.OPERATOR,
                "measurement.repeat_requested",
                operation_id=measurement_id,
                logical_channel=channel,
                physical_port=physical_port,
                reading_state="overwritten",
                repeated_reading=True,
                status="requested",
            )

    def _set_meter_trace_context(self, **context):
        setter = getattr(self.power_meter, "set_trace_context", None)
        if setter is None:
            return
        try:
            setter(**context)
        except Exception:
            pass

    def _record(self, category, event, *, level=SupportLogLevel.INFO, operation_id="", **fields):
        if self.support_logger is None:
            return
        try:
            self.support_logger.record(
                category,
                event,
                level=level,
                workflow_id=self.workflow_id,
                operation_id=operation_id,
                workflow_type="hardware_run",
                **fields,
            )
        except Exception:
            pass

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

    def _wait_for_read_or_write(self, live_update=False):
        if live_update:
            if not self._decision_event.wait(self.live_write_interval):
                self._raise_if_stopped()
                return "live_update"
        else:
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


__all__ = ["MeasurementWorker"]
