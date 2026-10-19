"""Background measurement orchestration for the desktop application."""

import threading
import time
import uuid
import math
from collections.abc import Mapping, Sequence

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from application.timing import LIVE_WRITE_INTERVAL_SECONDS
from domain.measurement import (
    DARK_REFERENCE_THRESHOLD_DBM,
    NON_NEGATIVE_LOSS_THRESHOLD_DB,
    calculate_insertion_loss,
    validate_insertion_loss,
)
from domain.models import ConnectionState, DeviceCategory
from domain.extra_ports import (
    DEFAULT_MAXIMUM_PHYSICAL_PORT_PROBE,
    ExtraPortPhaseStatus,
    PhysicalPortRouteStatus,
)
from domain.wavelengths import (
    MeasurementConfiguration,
    SM_SOURCE_PROFILE,
    measurement_configuration,
)
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
    extra_port_offer_required = pyqtSignal(int)
    extra_port_phase_changed = pyqtSignal(str, int, object)
    extra_port_confirmation_required = pyqtSignal(int, object)
    extra_port_issue = pyqtSignal(int, str, str)

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
        measurement_configuration_value: MeasurementConfiguration | None = None,
        front_panel_channel_count: int | None = None,
        offer_extra_ports=False,
        maximum_physical_port_probe=DEFAULT_MAXIMUM_PHYSICAL_PORT_PROBE,
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
        self.measurement_configuration = (
            measurement_configuration_value
            if measurement_configuration_value is not None
            else measurement_configuration("SM", SM_SOURCE_PROFILE)
        )
        self.front_panel_channel_count = (
            int(front_panel_channel_count)
            if front_panel_channel_count is not None
            else None
        )
        self.offer_extra_ports = bool(offer_extra_ports)
        self.maximum_physical_port_probe = int(maximum_physical_port_probe)
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
        self._negative_episode_active = False
        self._negative_episode_count = 0
        self._negative_episode_context = {}
        self._extra_action_event = threading.Event()
        self._extra_action_lock = threading.Lock()
        self._extra_action = None
        self._highest_confirmed_extra_port = None

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
            configure = getattr(self.power_meter, "configure_measurement", None)
            if configure is not None:
                configure(self.measurement_configuration)
            self._emit_device_status(ConnectionState.CONNECTED)
            configured_count = None
            if self.channels is not None:
                channels = list(self.channels)
            else:
                configured_count = self.switch.configured_channel_count()
                planned_count = self.front_panel_channel_count or configured_count
                channels = list(range(1, planned_count + 1))
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

            if self.offer_extra_ports and self.front_panel_channel_count is not None:
                self._offer_and_run_extra_ports()

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
            self._finish_negative_episode("run_finished")
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
        self._finish_negative_episode("channel_changed")
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
        return self._measure_routed_target(
            channel,
            physical_port,
            index=index,
            total=total,
            emit_progress=emit_progress,
            extra_port=False,
        )

    def _measure_routed_target(
        self,
        channel,
        physical_port,
        *,
        index=None,
        total=None,
        emit_progress=True,
        extra_port=False,
    ):
        """Measure an already-routed target without duplicating IL logic."""
        self._operator_ready.clear()
        self.operator_required.emit(channel, physical_port)
        if not self.live_write_mode:
            change = self._wait_for_operator()
            if extra_port:
                action = self._take_extra_action()
                if action is not None:
                    return {"extra_action": action}
            if change is not None:
                return change
        self._raise_if_stopped()

        while True:
            wavelengths = self.measurement_configuration.opm_wavelengths_nm
            first_wavelength, second_wavelength = wavelengths
            measurement_id = "measurement-" + uuid.uuid4().hex
            trace_context = {
                "workflow_id": self.workflow_id,
                "operation_id": measurement_id,
                "measurement_id": measurement_id,
                "method": "live_write" if self.live_write_mode else "normal_run",
                "channel": channel,
                "physical_port": physical_port,
                "wavelength_mode": (
                    self.measurement_configuration.wavelength_profile.code
                ),
                "opm_wavelengths_nm": list(wavelengths),
                "source_ids": list(self.measurement_configuration.source_ids),
                "source_wavelengths_nm": list(
                    self.measurement_configuration.source_wavelengths_nm
                ),
                "measurement_classification": (
                    self.measurement_configuration.classification.value
                ),
            }
            trace_context.update(
                {
                    "reference_%d_dbm" % wavelength: self.reference_powers.get(
                        wavelength
                    )
                    for wavelength in wavelengths
                }
            )
            self._set_meter_trace_context(
                **trace_context
            )
            started = time.perf_counter()
            measurements = self.power_meter.measure_both_wavelengths()
            if extra_port:
                unusable_wavelengths = tuple(
                    wavelength
                    for wavelength in wavelengths
                    if (
                        wavelength not in measurements
                        or not math.isfinite(float(measurements[wavelength]))
                        or float(measurements[wavelength])
                        < DARK_REFERENCE_THRESHOLD_DBM
                    )
                )
                if unusable_wavelengths:
                    self._record(
                        SupportEventCategory.MEASUREMENT,
                        "extra_ports.provisional_signal_invalid",
                        level=SupportLogLevel.WARNING,
                        operation_id=measurement_id,
                        physical_port=physical_port,
                        invalid_wavelength=",".join(
                            str(value) for value in unusable_wavelengths
                        ),
                        measured_power_dbm={
                            str(value): measurements.get(value)
                            for value in wavelengths
                        },
                        reading_state="discarded",
                        status="warning",
                    )
                    self.extra_port_issue.emit(
                        physical_port,
                        "invalid_signal",
                        "No valid optical signal was received for wavelength(s) %s."
                        % ", ".join(str(value) for value in unusable_wavelengths),
                    )
                    return {"extra_action": self._wait_for_extra_action()}
            losses = calculate_insertion_loss(
                self.reference_powers, measurements, wavelengths
            )
            validation = validate_insertion_loss(losses, wavelengths)
            if validation.valid:
                self._finish_negative_episode("valid_sample")
            else:
                if not self._negative_episode_active:
                    self._negative_episode_active = True
                    self._negative_episode_count = 0
                    self._negative_episode_context = {
                        "logical_channel": channel,
                        "physical_port": physical_port,
                        "references_by_wavelength": {
                            str(value): self.reference_powers.get(value)
                            for value in wavelengths
                        },
                        "measured_power_dbm": {
                            str(value): measurements[value] for value in wavelengths
                        },
                        "losses_by_wavelength": {
                            str(value): losses[value] for value in wavelengths
                        },
                        "threshold_db": NON_NEGATIVE_LOSS_THRESHOLD_DB,
                        "validation_reason": validation.reason,
                        "invalid_wavelength": ",".join(
                            str(value) for value in validation.invalid_wavelengths
                        ),
                    }
                    self._record(
                        SupportEventCategory.MEASUREMENT,
                        "measurement.negative_loss_episode_started",
                        operation_id=measurement_id,
                        logical_channel=channel,
                        physical_port=physical_port,
                        references_by_wavelength={
                            str(value): self.reference_powers.get(value)
                            for value in wavelengths
                        },
                        measured_power_dbm={
                            str(value): measurements[value] for value in wavelengths
                        },
                        losses_by_wavelength={
                            str(value): losses[value] for value in wavelengths
                        },
                        threshold_db=NON_NEGATIVE_LOSS_THRESHOLD_DB,
                        validation_reason=validation.reason,
                        invalid_wavelength=",".join(
                            str(value) for value in validation.invalid_wavelengths
                        ),
                    )
                self._negative_episode_count += 1
            self._record(
                SupportEventCategory.MEASUREMENT,
                "measurement.two_wavelength_completed",
                operation_id=measurement_id,
                logical_channel=channel,
                physical_port=physical_port,
                measured_power_dbm={
                    str(value): measurements[value] for value in wavelengths
                },
                references_by_wavelength={
                    str(value): self.reference_powers.get(value)
                    for value in wavelengths
                },
                losses_by_wavelength={
                    str(value): losses[value] for value in wavelengths
                },
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                reading_state="temporary",
                both_wavelengths_complete=True,
                acquisition_method=("live_write" if self.live_write_mode else "normal_run"),
                validation_reason=validation.reason,
                invalid_wavelength=",".join(
                    str(value) for value in validation.invalid_wavelengths
                ),
                status="success" if validation.valid else "warning",
            )
            self.reading_ready.emit(
                channel,
                physical_port,
                losses[first_wavelength],
                losses[second_wavelength],
            )
            decision = self._wait_for_read_or_write(
                live_update=self.live_write_mode
            )
            self._raise_if_stopped()
            if decision == "extra_action" and extra_port:
                return {"extra_action": self._take_extra_action()}
            if isinstance(decision, dict):
                return decision
            if decision == "live_update":
                continue
            if decision == "write":
                if not validation.valid:
                    self._record(
                        SupportEventCategory.OPERATOR,
                        "measurement.write_rejected_negative_loss",
                        operation_id=measurement_id,
                        logical_channel=channel,
                        physical_port=physical_port,
                        validation_reason=validation.reason,
                        invalid_wavelength=",".join(
                            str(value) for value in validation.invalid_wavelengths
                        ),
                        invalid_sample_count=self._negative_episode_count,
                        reading_state="rejected",
                        status="rejected",
                    )
                    continue
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

    def _offer_and_run_extra_ports(self):
        """Pause once after the front-panel pass, then probe extras sequentially."""
        count = self.front_panel_channel_count
        self._set_extra_phase(ExtraPortPhaseStatus.OFFERED, count)
        self._record(
            SupportEventCategory.WORKFLOW,
            "extra_ports.offered",
            front_panel_channel_count=count,
            status="offered",
        )
        self.extra_port_offer_required.emit(count)
        action = self._wait_for_extra_action()
        if action != "begin":
            self._set_extra_phase(ExtraPortPhaseStatus.DECLINED, count)
            self._record(
                SupportEventCategory.OPERATOR,
                "extra_ports.declined",
                front_panel_channel_count=count,
                status="declined",
            )
            self._record(
                SupportEventCategory.WORKFLOW,
                "extra_ports.phase_completed",
                phase_status=ExtraPortPhaseStatus.DECLINED.value,
                status="completed",
            )
            return

        candidate = count + 1
        self._record(
            SupportEventCategory.OPERATOR,
            "extra_ports.accepted",
            first_candidate=candidate,
            safety_ceiling=self.maximum_physical_port_probe,
            status="accepted",
        )
        while candidate <= self.maximum_physical_port_probe:
            self._set_extra_phase(ExtraPortPhaseStatus.IN_PROGRESS, candidate)
            outcome = self._run_extra_candidate(candidate)
            if outcome == "written":
                self._highest_confirmed_extra_port = candidate
                self._record(
                    SupportEventCategory.MEASUREMENT,
                    "extra_ports.reading_written",
                    physical_port=candidate,
                    highest_confirmed_extra_port=candidate,
                    status="success",
                )
                candidate += 1
                continue
            if outcome == "retry":
                self._record(
                    SupportEventCategory.OPERATOR,
                    "extra_ports.retry_requested",
                    physical_port=candidate,
                    status="requested",
                )
                continue
            if outcome == "no_more":
                self._set_extra_phase(
                    ExtraPortPhaseStatus.END_OF_INSTALLED_PORTS_REPORTED,
                    candidate,
                )
                self._record(
                    SupportEventCategory.OPERATOR,
                    "extra_ports.end_of_installed_ports_reported",
                    physical_port=candidate,
                    highest_confirmed_extra_port=self._highest_confirmed_extra_port,
                    reading_state="discarded",
                    status="reported",
                )
                self._record(
                    SupportEventCategory.WORKFLOW,
                    "extra_ports.phase_completed",
                    phase_status=(
                        ExtraPortPhaseStatus.END_OF_INSTALLED_PORTS_REPORTED.value
                    ),
                    highest_confirmed_extra_port=self._highest_confirmed_extra_port,
                    status="completed",
                )
                return
            if outcome == "failed":
                self._set_extra_phase(ExtraPortPhaseStatus.FAILED, candidate)
            else:
                self._set_extra_phase(ExtraPortPhaseStatus.STOPPED, candidate)
            self._record(
                SupportEventCategory.OPERATOR,
                "extra_ports.phase_ended",
                physical_port=candidate,
                highest_confirmed_extra_port=self._highest_confirmed_extra_port,
                reading_state="discarded",
                status=outcome,
            )
            self._record(
                SupportEventCategory.WORKFLOW,
                "extra_ports.phase_completed",
                phase_status=(
                    ExtraPortPhaseStatus.FAILED.value
                    if outcome == "failed"
                    else ExtraPortPhaseStatus.STOPPED.value
                ),
                highest_confirmed_extra_port=self._highest_confirmed_extra_port,
                status="failed" if outcome == "failed" else "completed",
            )
            return

        self._set_extra_phase(
            ExtraPortPhaseStatus.SAFETY_CEILING_REACHED,
            self.maximum_physical_port_probe,
        )
        self._record(
            SupportEventCategory.WORKFLOW,
            "extra_ports.safety_ceiling_reached",
            safety_ceiling=self.maximum_physical_port_probe,
            highest_confirmed_extra_port=self._highest_confirmed_extra_port,
            status="stopped",
        )
        self.extra_port_issue.emit(
            self.maximum_physical_port_probe,
            "safety_ceiling",
            "The configured maximum physical-port probe has been reached. "
            "Ask an administrator to review the safety ceiling before testing more ports.",
        )
        self._wait_for_extra_action()
        self._record(
            SupportEventCategory.WORKFLOW,
            "extra_ports.phase_completed",
            phase_status=ExtraPortPhaseStatus.SAFETY_CEILING_REACHED.value,
            highest_confirmed_extra_port=self._highest_confirmed_extra_port,
            status="completed",
        )

    def _run_extra_candidate(self, candidate):
        """Route and provisionally measure one candidate until the operator decides."""
        try:
            result = self.switch.set_physical_port(
                candidate,
                self.maximum_physical_port_probe,
            )
            route_status = result.status
            network_address = result.network_address
            network_port = result.network_port
            response = result.response
            detail = result.detail
        except Exception as error:
            return self._extra_issue_decision(candidate, "route_failed", str(error))

        self._record(
            SupportEventCategory.HARDWARE,
            "extra_ports.route_result",
            physical_port=candidate,
            network_address=network_address,
            network_port=network_port,
            verification_status=route_status.value,
            response=response,
            details=detail,
            status=(
                "error"
                if route_status is PhysicalPortRouteStatus.FAILED
                else "provisional"
            ),
        )
        if route_status is PhysicalPortRouteStatus.FAILED:
            return self._extra_issue_decision(
                candidate,
                "route_failed",
                detail or "The direct physical-port route failed.",
            )
        if route_status is PhysicalPortRouteStatus.UNVERIFIED:
            self.extra_port_confirmation_required.emit(candidate, result)
            action = self._wait_for_extra_action()
            if action != "proceed_unverified":
                return action
            self._record(
                SupportEventCategory.OPERATOR,
                "extra_ports.unverified_route_confirmed",
                physical_port=candidate,
                verification_status=route_status.value,
                status="accepted",
            )

        try:
            measurement_outcome = self._measure_routed_target(
                candidate,
                candidate,
                emit_progress=False,
                extra_port=True,
            )
        except Exception as error:
            return self._extra_issue_decision(
                candidate,
                "measurement_failed",
                "No usable optical reading was obtained: %s" % error,
            )
        if measurement_outcome is None:
            return "written"
        return measurement_outcome.get("extra_action", "retry")

    def _extra_issue_decision(self, candidate, issue_kind, message):
        self._record(
            SupportEventCategory.HARDWARE,
            "extra_ports.provisional_failed",
            level=SupportLogLevel.WARNING,
            physical_port=candidate,
            issue_kind=issue_kind,
            error_message=message,
            reading_state="discarded",
            status="warning",
        )
        self.extra_port_issue.emit(candidate, issue_kind, message)
        action = self._wait_for_extra_action()
        return "failed" if action == "stop_failed" else action

    def _set_extra_phase(self, status, candidate):
        details = {
            "highest_confirmed_extra_port": self._highest_confirmed_extra_port,
            "safety_ceiling": self.maximum_physical_port_probe,
        }
        self.extra_port_phase_changed.emit(status.value, int(candidate), details)

    def _wait_for_extra_action(self):
        while not self._extra_action_event.wait(0.1):
            self._raise_if_stopped()
        self._raise_if_stopped()
        action = self._take_extra_action()
        with self._decision_lock:
            if self._decision == "extra_action":
                self._decision = None
                self._decision_event.clear()
        return action

    def _take_extra_action(self):
        with self._extra_action_lock:
            action = self._extra_action
            self._extra_action = None
            self._extra_action_event.clear()
        return action

    def _set_meter_trace_context(self, **context):
        setter = getattr(self.power_meter, "set_trace_context", None)
        if setter is None:
            return
        try:
            setter(**context)
        except Exception:
            pass

    def _finish_negative_episode(self, reason):
        """Coalesce repeated negative live samples into one support episode."""
        if not self._negative_episode_active:
            return
        self._record(
            SupportEventCategory.MEASUREMENT,
            "measurement.negative_loss_episode_ended",
            **self._negative_episode_context,
            invalid_sample_count=self._negative_episode_count,
            details=reason,
            status="cleared" if reason == "valid_sample" else "ended",
        )
        self._negative_episode_active = False
        self._negative_episode_count = 0
        self._negative_episode_context = {}

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
        self._extra_action_event.set()
        self._set_decision("write")

    @pyqtSlot(bool)
    def choose_extra_port_testing(self, enabled):
        self._set_extra_action("begin" if enabled else "finish")

    @pyqtSlot(str)
    def extra_port_action(self, action):
        allowed = {"retry", "no_more", "stop", "stop_failed", "proceed_unverified"}
        if action not in allowed:
            return
        self._set_extra_action(action)
        self._operator_ready.set()
        self._set_decision("extra_action")

    def _set_extra_action(self, action):
        with self._extra_action_lock:
            self._extra_action = action
            self._extra_action_event.set()

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
