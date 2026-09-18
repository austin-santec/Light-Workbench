"""USB VISA driver for the Santec OSX-150 optical switch.

The switch understands SCPI text commands.  PyVISA sends those commands over
USB, while this class provides application-friendly methods for discovering the
switch, selecting a logical test channel, and reading its reported physical
port.
"""

import time

import pyvisa


SWITCH_SETTLING_TIME_SECONDS = 0.25
MIN_SWITCH_CHANNEL = 1
SANTEC_USB_VENDOR_ID = "0x2428"
SANTEC_USB_PRODUCT_ID = "0xD00D"


class OSX150:
    """Manage one Santec OSX-150 connected through USB VISA."""

    def __init__(self):
        self.resource_manager = None
        self.instrument = None
        self.address = None
        self.identity = None

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
            raise RuntimeError("The OSX-150 is not connected.")

    def connect(self):
        """Find the first USB VISA resource that identifies as an OSX-150."""
        self.resource_manager = pyvisa.ResourceManager()

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

            if ",OSX-150," in identity.upper():
                self.instrument = candidate
                self.address = address
                self.identity = identity
                return

            candidate.close()

        raise RuntimeError("No Santec OSX-150 was detected over USB VISA.")

    def current_channel(self):
        """Return the physical port currently reported by ``CLOSe?``."""
        self._require_connection()
        response = self.instrument.query("CLOSe?").strip()
        try:
            return int(response)
        except ValueError:
            raise RuntimeError(
                "The OSX-150 returned an invalid channel: %r" % response
            )

    def configured_channel_count(self):
        """Return the configured number of logical test channels.

        This can be smaller than the switch's physical port count.  For
        example, a 48-channel test configuration may use ports 49-56 as mapped
        replacements for logical test channels with excessive loss.
        """
        self._require_connection()
        response = self.instrument.query("CFG:SWT:END?").strip()
        try:
            channel_count = int(response)
        except ValueError:
            raise RuntimeError(
                "The OSX-150 returned an invalid configured channel count: %r"
                % response
            )

        if channel_count < MIN_SWITCH_CHANNEL:
            raise RuntimeError(
                "The OSX-150 reports an invalid configured channel count: %d"
                % channel_count
            )

        return channel_count

    def set_channel(self, channel):
        """Select a logical channel and return its reported physical port.

        The command intentionally uses the logical test-channel number.  Any
        logical-to-physical replacement mapping configured in the OSX-150 is
        applied by the switch itself.
        """
        self._require_connection()
        if channel < MIN_SWITCH_CHANNEL:
            raise ValueError(
                "Switch channel must be %d or greater." % MIN_SWITCH_CHANNEL
            )

        self.instrument.write("CLOSe %d" % channel)
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
