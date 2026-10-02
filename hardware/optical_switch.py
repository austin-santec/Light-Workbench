"""PyVISA adapter for supported Santec optical switches."""

import logging
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from enum import Enum
from datetime import datetime, timezone

import pyvisa

from domain.models import ConnectionState, DeviceCategory, DeviceInfo


SWITCH_SETTLING_TIME_SECONDS = 0.25
MIN_SWITCH_CHANNEL = 1
SANTEC_USB_VENDOR_ID = "0x2428"
SANTEC_USB_PRODUCT_ID = "0xD00D"
SANTEC_USB_RESOURCE_QUERY = "USB?*::INSTR"
SWITCH_WRITE_TERMINATIONS = ("\n", "\r\n")
LOG = logging.getLogger(__name__)


class SwitchDiscoveryMethod(str, Enum):
    """Ways a VISA address can enter the bounded discovery sequence."""

    MANUAL = "Manual address"
    LAST_KNOWN = "Last-known address"
    AUTOMATIC_USB = "Automatic USB discovery"


class SwitchConnectionStage(str, Enum):
    """Connection stages retained for operator-facing diagnostics."""

    DISCOVERY = "discovery"
    OPEN = "resource open"
    IDENTITY = "identity"
    MODEL = "model validation"
    CONFIGURATION = "configuration"
    READY = "ready"
    ROUTING = "channel routing"


@dataclass(frozen=True)
class SwitchConnectionDiagnostics:
    """Transient details from the most recent switch connection attempt."""

    discovery_method: str = ""
    resource_address: str = ""
    enumeration_error: str = ""
    raw_identity: str = ""
    manufacturer: str = ""
    model: str = ""
    serial_number: str = ""
    firmware_version: str = ""
    write_termination: str = ""
    configured_channel_count: int | None = None
    failure_stage: str = ""
    failed_command: str = ""
    raw_failed_response: str = ""
    user_message: str = ""
    connection_warning: str = ""


class SwitchConnectionError(RuntimeError):
    """A staged switch startup failure with preserved diagnostic context."""

    def __init__(self, diagnostics: SwitchConnectionDiagnostics):
        self.diagnostics = diagnostics
        super().__init__(diagnostics.user_message or "Optical switch connection failed.")


@dataclass(frozen=True)
class SantecSwitchProfile:
    """Command capabilities for one recognized Santec switch model."""

    model: str
    current_channel_query: str = "CLOSe?"
    configured_channel_query: str = "CFG:SWT:END?"
    channel_command: str = "CLOSe %d"


@dataclass(frozen=True)
class _IdentityProbe:
    instrument: object
    identity: str
    write_termination: str


# Keep recognition and command compatibility in one registry. OSX-100 is
# intentionally absent until its command set has been verified on hardware.
SANTEC_SWITCH_PROFILES = {
    "OSX-150": SantecSwitchProfile(model="OSX-150"),
}
KNOWN_SANTEC_SWITCH_MODEL_PATTERN = re.compile(r"\bOSX[- ]?\d+\b", re.IGNORECASE)
SCPI_ERROR_RESPONSE_PATTERN = re.compile(r'^-\d+\s*,\s*"')


def detect_santec_switch_model(identity: object) -> str | None:
    """Extract a normalized model token from a Santec identity string."""
    match = KNOWN_SANTEC_SWITCH_MODEL_PATTERN.search(str(identity or ""))
    return match.group(0).upper().replace(" ", "-") if match else None


def _identity_fields(identity: object) -> tuple[str, str, str, str]:
    fields = [field.strip() for field in str(identity or "").split(",")]
    fields.extend([""] * (4 - len(fields)))
    return fields[0], fields[1], fields[2], fields[3]


def extract_santec_serial(identity: object) -> str:
    """Extract the serial field from the usual comma-separated VISA IDN."""
    return _identity_fields(identity)[2]


class OSX150:
    """Manage one supported Santec switch connected through USB VISA."""

    def __init__(
        self,
        resource_address: str = "",
        last_known_address: str = "",
        address_observer: Callable[[str], None] | None = None,
        trace_callback=None,
    ):
        self.resource_manager = None
        self.instrument = None
        self.address = None
        self.identity = None
        self.resource_address = resource_address.strip()
        self.last_known_address = last_known_address.strip()
        self.address_observer = address_observer
        self.write_termination = None
        self.model = "OSX-150"
        self.profile = SANTEC_SWITCH_PROFILES["OSX-150"]
        self._configured_channel_count = None
        self.connection_diagnostics = SwitchConnectionDiagnostics()
        self._enumeration_error = ""
        self._manual_address_failed = False
        self._last_failure = None
        self._trace_callbacks = []
        self._trace_metadata = {}
        if trace_callback is not None:
            self._trace_callbacks.append(trace_callback)

    def add_trace_callback(self, callback):
        """Subscribe a failure-isolated structured hardware trace consumer."""
        if callback is not None and callback not in self._trace_callbacks:
            self._trace_callbacks.append(callback)

    def remove_trace_callback(self, callback):
        if callback in self._trace_callbacks:
            self._trace_callbacks.remove(callback)

    def set_trace_metadata(self, **metadata):
        self._trace_metadata.update(metadata)

    def _trace(self, event, **values):
        if not self._trace_callbacks:
            return
        payload = dict(self._trace_metadata)
        payload.update({
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "device_category": "optical_switch",
        })
        payload.update(values)
        for callback in tuple(self._trace_callbacks):
            try:
                callback(dict(payload))
            except Exception:
                continue

    @staticmethod
    def _is_santec_usb_resource(address: object) -> bool:
        """Quickly filter VISA resources using Santec vendor/product IDs."""
        normalized_address = str(address or "").upper()
        return (
            normalized_address.startswith("USB")
            and SANTEC_USB_VENDOR_ID.upper() in normalized_address
            and SANTEC_USB_PRODUCT_ID.upper() in normalized_address
        )

    @staticmethod
    def _configure_instrument(instrument, write_termination: str) -> None:
        """Set the bounded probe timeout and selected SCPI line ending."""
        instrument.timeout = 2000
        instrument.read_termination = "\n"
        instrument.write_termination = write_termination

    def _base_diagnostics(
        self,
        address: str = "",
        discovery_method: str = "",
        identity: str = "",
        termination: str = "",
    ) -> SwitchConnectionDiagnostics:
        manufacturer, _raw_model, serial, firmware = _identity_fields(identity)
        return SwitchConnectionDiagnostics(
            discovery_method=discovery_method,
            resource_address=address,
            enumeration_error=self._enumeration_error,
            raw_identity=identity,
            manufacturer=manufacturer,
            model=detect_santec_switch_model(identity) or "",
            serial_number=serial,
            firmware_version=firmware,
            write_termination=(
                "CRLF" if termination == "\r\n" else "LF" if termination else ""
            ),
        )

    def _candidate_addresses(self) -> Iterator[tuple[str, str]]:
        """Yield manual, last-known, then targeted USB VISA resources once."""
        seen = set()
        for address, method in (
            (self.resource_address, SwitchDiscoveryMethod.MANUAL.value),
            (self.last_known_address, SwitchDiscoveryMethod.LAST_KNOWN.value),
        ):
            if address and address not in seen:
                seen.add(address)
                self._trace(
                    "switch_discovery_candidate",
                    resource_address=address,
                    discovery_method=method,
                    status="candidate",
                )
                yield address, method

        try:
            listed = self.resource_manager.list_resources(SANTEC_USB_RESOURCE_QUERY)
        except pyvisa.errors.VisaIOError as error:
            self._enumeration_error = str(error)
            LOG.info("Santec USB VISA enumeration failed: %s", error)
            self._trace(
                "switch_discovery_failed",
                operation="list_resources",
                command=SANTEC_USB_RESOURCE_QUERY,
                status="error",
                error=str(error),
            )
            return

        for address in listed:
            if self._is_santec_usb_resource(address) and address not in seen:
                seen.add(address)
                self._trace(
                    "switch_discovery_candidate",
                    resource_address=address,
                    discovery_method=SwitchDiscoveryMethod.AUTOMATIC_USB.value,
                    status="candidate",
                )
                yield address, SwitchDiscoveryMethod.AUTOMATIC_USB.value

    def _probe_identity(
        self,
        address: str,
        discovery_method: str,
    ) -> _IdentityProbe | None:
        """Try IDN with LF then CRLF, reopening after every failed attempt."""
        for termination in SWITCH_WRITE_TERMINATIONS:
            candidate = None
            keep_candidate = False
            try:
                candidate = self.resource_manager.open_resource(address)
                self._configure_instrument(candidate, termination)
                identity = candidate.query("*IDN?").strip()
                self._trace(
                    "switch_identity_probe",
                    operation="query",
                    command="*IDN?",
                    raw_response=identity,
                    response_length=len(identity),
                    resource_address=address,
                    discovery_method=discovery_method,
                    write_termination=("CRLF" if termination == "\r\n" else "LF"),
                    status="success",
                )
                manufacturer = identity.partition(",")[0].strip().upper()
                if manufacturer.startswith("SANTEC"):
                    keep_candidate = True
                    return _IdentityProbe(candidate, identity, termination)
                self._last_failure = replace(
                    self._base_diagnostics(
                        address, discovery_method, identity, termination
                    ),
                    failure_stage=SwitchConnectionStage.IDENTITY.value,
                    failed_command="*IDN?",
                    raw_failed_response=identity,
                    user_message=(
                        "The VISA resource at %s answered *IDN?, but it did not "
                        "identify itself as a Santec switch. Response: %r"
                        % (address, identity)
                    ),
                )
            except pyvisa.errors.VisaIOError as error:
                stage = (
                    SwitchConnectionStage.OPEN.value
                    if candidate is None
                    else SwitchConnectionStage.IDENTITY.value
                )
                message = (
                    "A possible OSX switch was found at %s, but its VISA session "
                    "could not be opened. Close Santec Terminal or other software "
                    "that may be using the switch, then try again. Technical error: %s"
                    % (address, error)
                    if candidate is None
                    else "The USB/VISA resource at %s opened, but the switch did "
                    "not answer *IDN? using %s. Technical error: %s"
                    % (address, "CRLF" if termination == "\r\n" else "LF", error)
                )
                self._last_failure = replace(
                    self._base_diagnostics(address, discovery_method),
                    failure_stage=stage,
                    failed_command="*IDN?" if candidate is not None else "",
                    user_message=message,
                )
                LOG.info(
                    "Switch identity probe failed at %s (%r): %s",
                    address,
                    termination,
                    error,
                )
                self._trace(
                    "switch_identity_probe",
                    operation="query",
                    command="*IDN?",
                    resource_address=address,
                    discovery_method=discovery_method,
                    write_termination=("CRLF" if termination == "\r\n" else "LF"),
                    status="error",
                    error=str(error),
                )
            finally:
                if candidate is not None and not keep_candidate:
                    candidate.close()
        if discovery_method == SwitchDiscoveryMethod.MANUAL.value:
            self._manual_address_failed = True
        if self._last_failure is not None:
            self._last_failure = replace(
                self._last_failure,
                user_message=(
                    "The USB/VISA resource at %s did not answer *IDN? with "
                    "either LF or CRLF command endings. Check that no other "
                    "application is using the switch. Last technical result: %s"
                    % (address, self._last_failure.user_message)
                ),
            )
        return None

    def _configuration_error(
        self,
        diagnostics: SwitchConnectionDiagnostics,
        message: str,
        response: str = "",
    ) -> SwitchConnectionError:
        diagnostics = replace(
            diagnostics,
            failure_stage=SwitchConnectionStage.CONFIGURATION.value,
            failed_command=self.profile.configured_channel_query,
            raw_failed_response=response,
            user_message=message,
        )
        self.connection_diagnostics = diagnostics
        return SwitchConnectionError(diagnostics)

    def _read_and_validate_channel_count(
        self,
        diagnostics: SwitchConnectionDiagnostics,
    ) -> int:
        command = self.profile.configured_channel_query
        try:
            response = self.instrument.query(command).strip()
            self._trace(
                "switch_channel_count",
                operation="query",
                command=command,
                raw_response=response,
                response_length=len(response),
                status="success",
            )
        except pyvisa.errors.VisaIOError as error:
            self._trace(
                "switch_channel_count",
                operation="query",
                command=command,
                status="error",
                error=str(error),
            )
            raise self._configuration_error(
                diagnostics,
                "%s connected and identified itself, but Light Workbench could "
                "not read its configured channel count. Command: %s. Technical "
                "error: %s" % (self.model, command, error),
            ) from error

        if SCPI_ERROR_RESPONSE_PATTERN.match(response):
            raise self._configuration_error(
                diagnostics,
                "%s connected and identified itself, but it rejected the "
                "configured-channel query.\n\nCommand: %s\nResponse: %s\n\n"
                "Check the switch configuration and firmware compatibility. "
                "No channel command was sent." % (self.model, command, response),
                response,
            )

        try:
            channel_count = int(response)
        except ValueError as error:
            raise self._configuration_error(
                diagnostics,
                "%s connected and identified itself, but returned an unexpected "
                "configured channel count.\n\nCommand: %s\nResponse: %r\n\n"
                "No channel command was sent." % (self.model, command, response),
                response,
            ) from error

        diagnostics = replace(diagnostics, configured_channel_count=channel_count)
        if channel_count == 0:
            raise self._configuration_error(
                diagnostics,
                "Santec %s detected and identified successfully.\n\n"
                "Serial: %s\nFirmware: %s\nVISA address: %s\n"
                "Configured channels: %d\n\nThe switch does not currently have a "
                "usable channel configuration. The configuration may have been "
                "cleared during the firmware change. Restore or load the correct "
                "switch configuration, then reconnect. No channel command was sent."
                % (
                    self.model,
                    diagnostics.serial_number or "Unknown",
                    diagnostics.firmware_version or "Unknown",
                    diagnostics.resource_address,
                    channel_count,
                ),
                response,
            )
        if channel_count < 0:
            raise self._configuration_error(
                diagnostics,
                "%s connected and identified itself, but returned an invalid "
                "negative configured channel count.\n\nCommand: %s\nResponse: %r\n\n"
                "No channel command was sent."
                % (self.model, command, response),
                response,
            )
        self.connection_diagnostics = replace(
            diagnostics,
            configured_channel_count=channel_count,
            failure_stage=SwitchConnectionStage.READY.value,
        )
        self._trace(
            "switch_configuration_validated",
            configured_channel_count=channel_count,
            model=diagnostics.model,
            firmware=diagnostics.firmware_version,
            device_serial=diagnostics.serial_number,
            resource_address=diagnostics.resource_address,
            status="success",
        )
        return channel_count

    def _require_connection(self) -> None:
        if self.instrument is None:
            raise RuntimeError("The %s is not connected." % self.model)

    def get_device_info(
        self,
        state=ConnectionState.DISCONNECTED,
        error="",
    ) -> DeviceInfo:
        """Return switch identity and the latest transient connection details."""
        diagnostics = self.connection_diagnostics
        transport_parts = []
        if diagnostics.discovery_method:
            transport_parts.append("Discovery: %s" % diagnostics.discovery_method)
        if diagnostics.write_termination:
            transport_parts.append(
                "SCPI write ending: %s" % diagnostics.write_termination
            )
        if diagnostics.configured_channel_count is not None:
            transport_parts.append(
                "Configured channels: %d" % diagnostics.configured_channel_count
            )
        if diagnostics.enumeration_error:
            transport_parts.append(
                "VISA enumeration warning: %s" % diagnostics.enumeration_error
            )
        return DeviceInfo(
            category=DeviceCategory.OPTICAL_SWITCH,
            manufacturer=diagnostics.manufacturer or "Santec",
            model=diagnostics.model or self.model or "Unknown optical switch",
            serial_number=diagnostics.serial_number or extract_santec_serial(self.identity),
            raw_identity=diagnostics.raw_identity or self.identity or "",
            resource_address=diagnostics.resource_address or self.address or "",
            state=state,
            error=error or diagnostics.user_message,
            transport_details="; ".join(transport_parts),
            firmware_version=diagnostics.firmware_version,
            configured_channel_count=diagnostics.configured_channel_count,
            discovery_method=diagnostics.discovery_method,
            failure_stage=diagnostics.failure_stage,
            failed_command=diagnostics.failed_command,
            raw_response=diagnostics.raw_failed_response,
            connection_warning=diagnostics.connection_warning,
        )

    def connect(self) -> None:
        """Discover, identify, and validate one supported Santec USB switch."""
        self.resource_manager = pyvisa.ResourceManager()
        self._last_failure = None
        attempted_address = False
        try:
            for address, discovery_method in self._candidate_addresses():
                attempted_address = True
                probe = self._probe_identity(address, discovery_method)
                if probe is None:
                    continue

                model = detect_santec_switch_model(probe.identity)
                profile = SANTEC_SWITCH_PROFILES.get(model)
                diagnostics = self._base_diagnostics(
                    address,
                    discovery_method,
                    probe.identity,
                    probe.write_termination,
                )
                if profile is None:
                    probe.instrument.close()
                    if model:
                        diagnostics = replace(
                            diagnostics,
                            failure_stage=SwitchConnectionStage.MODEL.value,
                            user_message=(
                                "A Santec %s was detected at %s, but Light Workbench "
                                "does not yet have a verified command profile for "
                                "that model." % (model, address)
                            ),
                        )
                    else:
                        diagnostics = replace(
                            diagnostics,
                            failure_stage=SwitchConnectionStage.MODEL.value,
                            user_message=(
                                "An unknown Santec optical switch was detected at %s. "
                                "Identity: %s" % (address, probe.identity)
                            ),
                        )
                    self._last_failure = diagnostics
                    continue

                self.instrument = probe.instrument
                self.address = address
                self.identity = probe.identity
                self.write_termination = probe.write_termination
                self.model = profile.model
                self.profile = profile
                warning = ""
                if (
                    self._manual_address_failed
                    and discovery_method != SwitchDiscoveryMethod.MANUAL.value
                ):
                    warning = (
                        "The saved manual switch address did not respond; Light "
                        "Workbench connected using %s at %s."
                        % (discovery_method.lower(), address)
                    )
                diagnostics = replace(diagnostics, connection_warning=warning)
                self._configured_channel_count = self._read_and_validate_channel_count(
                    diagnostics
                )
                if discovery_method == SwitchDiscoveryMethod.AUTOMATIC_USB.value:
                    self._remember_detected_address(address)
                LOG.info(
                    "Connected %s (%s) at %s using %s and %s",
                    self.model,
                    self.identity,
                    address,
                    discovery_method,
                    self.connection_diagnostics.write_termination,
                )
                self._trace(
                    "switch_connected",
                    manufacturer=diagnostics.manufacturer,
                    model=self.model,
                    device_serial=diagnostics.serial_number,
                    firmware=diagnostics.firmware_version,
                    resource_address=address,
                    discovery_method=discovery_method,
                    configured_channel_count=self._configured_channel_count,
                    write_termination=self.connection_diagnostics.write_termination,
                    status="success",
                )
                return

            if self._last_failure is not None:
                raise SwitchConnectionError(self._last_failure)
            if self._enumeration_error:
                diagnostics = SwitchConnectionDiagnostics(
                    enumeration_error=self._enumeration_error,
                    failure_stage=SwitchConnectionStage.DISCOVERY.value,
                    user_message=(
                        "VISA could not enumerate USB instruments. Light Workbench "
                        "also tried any saved switch address. Check the VISA runtime "
                        "and USB driver. Technical error: %s" % self._enumeration_error
                    ),
                )
            else:
                diagnostics = SwitchConnectionDiagnostics(
                    failure_stage=SwitchConnectionStage.DISCOVERY.value,
                    user_message=(
                        "No Santec OSX USB resource was found. Confirm that the "
                        "switch is powered on, connected by USB, and visible to the "
                        "installed VISA runtime."
                    ),
                )
            if attempted_address and not diagnostics.resource_address:
                diagnostics = replace(
                    diagnostics,
                    resource_address=self.resource_address or self.last_known_address,
                )
            self.connection_diagnostics = diagnostics
            raise SwitchConnectionError(diagnostics)
        except SwitchConnectionError:
            self.close()
            raise
        except Exception:
            self.close()
            raise

    def _remember_detected_address(self, address: str) -> None:
        if self.address_observer is None:
            return
        try:
            self.address_observer(address)
        except Exception as error:
            LOG.warning("Could not remember detected switch address: %s", error)

    def current_channel(self) -> int:
        """Return the physical port after a channel-routing command."""
        self._require_connection()
        response = self.instrument.query(self.profile.current_channel_query).strip()
        self._trace(
            "switch_physical_port_query",
            operation="query",
            command=self.profile.current_channel_query,
            raw_response=response,
            response_length=len(response),
            status="success",
        )
        try:
            return int(response)
        except ValueError as error:
            raise RuntimeError(
                "%s did not confirm the routed physical port. Command: %s. "
                "Response: %r"
                % (self.model, self.profile.current_channel_query, response)
            ) from error

    def configured_channel_count(self) -> int:
        """Return the positive channel count validated during connection."""
        self._require_connection()
        if self._configured_channel_count is None:
            self._configured_channel_count = self._read_and_validate_channel_count(
                self.connection_diagnostics
            )
        return self._configured_channel_count

    def set_channel(self, channel: int) -> int:
        """Select a logical channel and return its verified physical port."""
        self._require_connection()
        if channel < MIN_SWITCH_CHANNEL:
            raise ValueError(
                "Switch channel must be %d or greater." % MIN_SWITCH_CHANNEL
            )

        command = self.profile.channel_command % channel
        started = time.perf_counter()
        try:
            self.instrument.write(command)
        except Exception as error:
            self._trace(
                "switch_route_failed",
                operation="write",
                command=command,
                logical_channel=channel,
                status="error",
                error=str(error),
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            raise
        time.sleep(SWITCH_SETTLING_TIME_SECONDS)
        physical_port = self.current_channel()
        self._trace(
            "switch_route_completed",
            operation="set_channel",
            command=command,
            logical_channel=channel,
            physical_port=physical_port,
            status="success",
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
        return physical_port

    def close(self) -> None:
        """Release both the instrument session and VISA resource manager."""
        if self.instrument is not None:
            self.instrument.close()
            self.instrument = None

        if self.resource_manager is not None:
            self.resource_manager.close()
            self.resource_manager = None
        self._trace("switch_closed", status="success")


__all__ = [
    "MIN_SWITCH_CHANNEL",
    "OSX150",
    "SantecSwitchProfile",
    "SANTEC_SWITCH_PROFILES",
    "SANTEC_USB_PRODUCT_ID",
    "SANTEC_USB_RESOURCE_QUERY",
    "SANTEC_USB_VENDOR_ID",
    "SWITCH_SETTLING_TIME_SECONDS",
    "SwitchConnectionDiagnostics",
    "SwitchConnectionError",
    "SwitchConnectionStage",
    "SwitchDiscoveryMethod",
    "detect_santec_switch_model",
    "extract_santec_serial",
]
