"""PyVISA adapter for the Santec OSX-150 optical switch."""

import re
import time
from dataclasses import dataclass

import pyvisa

from domain.models import ConnectionState, DeviceCategory, DeviceInfo


SWITCH_SETTLING_TIME_SECONDS = 0.25
MIN_SWITCH_CHANNEL = 1
SANTEC_USB_VENDOR_ID = "0x2428"
SANTEC_USB_PRODUCT_ID = "0xD00D"


@dataclass(frozen=True)
class SantecSwitchProfile:
    """Command capabilities for one recognized Santec switch model."""

    model: str
    current_channel_query: str = "CLOSe?"
    configured_channel_query: str = "CFG:SWT:END?"
    channel_command: str = "CLOSe %d"


# Keep recognition and command compatibility in one registry.  OSX-100 is
# intentionally not listed until its command set has been verified.
SANTEC_SWITCH_PROFILES = {
    "OSX-150": SantecSwitchProfile(model="OSX-150"),
}
KNOWN_SANTEC_SWITCH_MODEL_PATTERN = re.compile(r"\bOSX[- ]?\d+\b", re.IGNORECASE)


def detect_santec_switch_model(identity):
    """Extract a model token from a Santec VISA identity string."""
    match = KNOWN_SANTEC_SWITCH_MODEL_PATTERN.search(str(identity or ""))
    return match.group(0).upper().replace(" ", "-") if match else None


def extract_santec_serial(identity):
    """Extract the serial field from the usual comma-separated VISA IDN."""
    fields = [field.strip() for field in str(identity or "").split(",")]
    return fields[2] if len(fields) >= 3 else ""


class OSX150:
    """Manage one Santec OSX-150 connected through USB VISA."""

    def __init__(self):
        self.resource_manager = None
        self.instrument = None
        self.address = None
        self.identity = None
        self.model = "OSX-150"
        self.profile = SANTEC_SWITCH_PROFILES["OSX-150"]

    @staticmethod
    def _is_santec_usb_resource(address):
        """Quickly filter VISA resources using Santec's USB vendor/product IDs."""
        normalized_address = address.upper()
        return (
            normalized_address.startswith("USB")
            and SANTEC_USB_VENDOR_ID.upper() in normalized_address
            and SANTEC_USB_PRODUCT_ID.upper() in normalized_address
        )

    @staticmethod
    def _configure_instrument(instrument):
        """Set timeouts and line endings expected by the switch's SCPI server."""
        instrument.timeout = 2000
        instrument.read_termination = "\n"
        instrument.write_termination = "\n"

    def _require_connection(self):
        if self.instrument is None:
            raise RuntimeError("The %s is not connected." % self.model)

    def get_device_info(
        self,
        state=ConnectionState.DISCONNECTED,
        error="",
    ):
        """Return switch identity and transient connection status."""
        return DeviceInfo(
            category=DeviceCategory.OPTICAL_SWITCH,
            manufacturer="Santec",
            model=self.model or "Unknown optical switch",
            serial_number=extract_santec_serial(self.identity),
            raw_identity=self.identity or "",
            resource_address=self.address or "",
            state=state,
            error=error,
        )

    def connect(self):
        """Find the first supported Santec USB VISA resource.

        The profile registry makes recognition extensible while retaining the
        current OSX-150-only command behavior.  Recognized but unprofiled
        models fail explicitly instead of being treated as compatible.
        """
        self.resource_manager = pyvisa.ResourceManager()
        unsupported_identity = None
        unknown_identity = None

        for address in self.resource_manager.list_resources():
            if not self._is_santec_usb_resource(address):
                continue

            candidate = None
            try:
                candidate = self.resource_manager.open_resource(address)
                self._configure_instrument(candidate)
                identity = candidate.query("*IDN?").strip()
            except pyvisa.errors.VisaIOError:
                if candidate is not None:
                    candidate.close()
                continue

            model = detect_santec_switch_model(identity)
            profile = SANTEC_SWITCH_PROFILES.get(model)
            if profile is not None:
                self.instrument = candidate
                self.address = address
                self.identity = identity
                self.model = profile.model
                self.profile = profile
                return

            if model is not None:
                unsupported_identity = identity
            elif "SANTEC" in identity.upper():
                unknown_identity = identity

            candidate.close()

        if unsupported_identity:
            model = detect_santec_switch_model(unsupported_identity)
            self.model = model or "Unknown optical switch"
            self.identity = unsupported_identity
            raise RuntimeError(
                "Recognized Santec %s, but this model is not yet supported. "
                "Identity: %s" % (self.model, unsupported_identity)
            )
        if unknown_identity:
            self.model = "Unknown optical switch"
            self.identity = unknown_identity
            raise RuntimeError(
                "Unknown Santec optical switch detected. Identity: %s"
                % unknown_identity
            )
        raise RuntimeError("No supported Santec optical switch was detected over USB VISA.")

    def current_channel(self):
        """Return the physical port currently reported by ``CLOSe?``."""
        self._require_connection()
        response = self.instrument.query(self.profile.current_channel_query).strip()
        try:
            return int(response)
        except ValueError:
            raise RuntimeError(
                "The %s returned an invalid channel: %r" % (self.model, response)
            )

    def configured_channel_count(self):
        """Return the configured number of logical test channels.

        This can be smaller than the switch's physical port count. For example,
        a 48-channel test configuration may use ports 49-56 as mapped
        replacements for logical test channels with excessive loss.
        """
        self._require_connection()
        response = self.instrument.query(self.profile.configured_channel_query).strip()
        try:
            channel_count = int(response)
        except ValueError:
            raise RuntimeError(
                "The %s returned an invalid configured channel count: %r"
                % (self.model, response)
            )

        if channel_count < MIN_SWITCH_CHANNEL:
            raise RuntimeError(
                "The %s reports an invalid configured channel count: %d"
                % (self.model, channel_count)
            )

        return channel_count

    def set_channel(self, channel):
        """Select a logical channel and return its reported physical port.

        The command intentionally uses the logical test-channel number. Any
        logical-to-physical replacement mapping configured in the OSX-150 is
        applied by the switch itself.
        """
        self._require_connection()
        if channel < MIN_SWITCH_CHANNEL:
            raise ValueError(
                "Switch channel must be %d or greater." % MIN_SWITCH_CHANNEL
            )

        self.instrument.write(self.profile.channel_command % channel)
        time.sleep(SWITCH_SETTLING_TIME_SECONDS)
        return self.current_channel()

    def close(self):
        """Release both the instrument session and the VISA resource manager."""
        if self.instrument is not None:
            self.instrument.close()
            self.instrument = None

        if self.resource_manager is not None:
            self.resource_manager.close()
            self.resource_manager = None


__all__ = [
    "MIN_SWITCH_CHANNEL",
    "OSX150",
    "SantecSwitchProfile",
    "SANTEC_SWITCH_PROFILES",
    "SANTEC_USB_PRODUCT_ID",
    "SANTEC_USB_VENDOR_ID",
    "SWITCH_SETTLING_TIME_SECONDS",
    "detect_santec_switch_model",
    "extract_santec_serial",
]
