"""Lifecycle management for composed optical-test hardware capabilities."""

from hardware.interfaces import LaserSource, OpticalSwitch, PowerMeter


class OpticalTestSession:
    """Own and safely connect a meter, optional laser, and optional switch.

    Integrated ILM workflows can provide only a power meter and switch. A
    separate OPM-plus-laser workflow can provide all three capabilities without
    duplicating connection cleanup rules in each controller.
    """

    def __init__(
        self,
        power_meter: PowerMeter,
        switch: OpticalSwitch | None = None,
        laser_source: LaserSource | None = None,
    ):
        self.power_meter = power_meter
        self.switch = switch
        self.laser_source = laser_source
        self.connected = False
        self._connected_devices = []

    def connect(self) -> None:
        """Connect all configured devices and clean up on partial failure."""
        if self.connected:
            return

        devices = [
            device
            for device in (self.laser_source, self.switch, self.power_meter)
            if device is not None
        ]
        try:
            for device in devices:
                self._connected_devices.append(device)
                device.connect()
        except Exception:
            self.close()
            raise
        self.connected = True

    def close(self) -> None:
        """Close connected devices in reverse ownership order."""
        close_errors = []
        for device in reversed(self._connected_devices):
            try:
                device.close()
            except Exception as error:
                close_errors.append(error)
        self._connected_devices.clear()
        self.connected = False
        if close_errors:
            raise RuntimeError("One or more optical devices failed to close.") from close_errors[0]

    def set_wavelength(self, wavelength_nm: int) -> None:
        """Set a separate laser wavelength when one is configured."""
        if self.laser_source is None:
            raise RuntimeError("No separate laser source is configured.")
        self.laser_source.set_wavelength(wavelength_nm)

    def set_laser_output(self, enabled: bool) -> None:
        """Enable or disable the optional separate laser source."""
        if self.laser_source is None:
            raise RuntimeError("No separate laser source is configured.")
        self.laser_source.set_output(enabled)


__all__ = ["OpticalTestSession"]
