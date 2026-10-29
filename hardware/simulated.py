"""Hardware-free adapters for workflow and integration testing."""

from hardware.interfaces import LogicalChannelRouteResult, WAVELENGTHS_NM


class SimulatedLaserSource:
    """Simple separate laser source that records operator commands."""

    description = "Simulated laser source"
    serial_number = "SIMULATED-LASER"

    def __init__(self):
        self.connected = False
        self.output_enabled = False
        self.wavelength_nm = None

    def connect(self):
        self.connected = True

    def set_wavelength(self, wavelength_nm):
        if not self.connected:
            raise RuntimeError("Simulated laser source is not connected.")
        if wavelength_nm not in WAVELENGTHS_NM:
            raise ValueError("Unsupported simulated wavelength: %s" % wavelength_nm)
        self.wavelength_nm = int(wavelength_nm)

    def set_output(self, enabled):
        if not self.connected:
            raise RuntimeError("Simulated laser source is not connected.")
        self.output_enabled = bool(enabled)

    def close(self):
        self.output_enabled = False
        self.connected = False


class SimulatedOpticalSwitch:
    """Deterministic switch adapter for testing routing workflows."""

    description = "Simulated optical switch"
    serial_number = "SIMULATED-SWITCH"

    def __init__(self, channel_count=48):
        if int(channel_count) < 1:
            raise ValueError("Simulated switch channel count must be positive.")
        self.channel_count = int(channel_count)
        self.connected = False
        self.selected_channels = []
        self._current_logical_channel = None

    def connect(self):
        self.connected = True

    def configured_channel_count(self):
        if not self.connected:
            raise RuntimeError("Simulated optical switch is not connected.")
        return self.channel_count

    def set_channel(self, channel):
        if not self.connected:
            raise RuntimeError("Simulated optical switch is not connected.")
        channel = int(channel)
        if not 1 <= channel <= self.channel_count:
            raise ValueError("Simulated switch channel is outside the configured range.")
        self.selected_channels.append(channel)
        self._current_logical_channel = channel
        return LogicalChannelRouteResult(channel, channel)

    def current_logical_channel(self):
        if not self.connected:
            raise RuntimeError("Simulated optical switch is not connected.")
        if self._current_logical_channel is None:
            raise RuntimeError("No simulated logical channel has been selected.")
        return self._current_logical_channel

    def close(self):
        self._current_logical_channel = None
        self.connected = False


__all__ = ["SimulatedLaserSource", "SimulatedOpticalSwitch"]
