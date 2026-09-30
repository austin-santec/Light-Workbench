"""Application-facing integrated ILM and simulated power-meter adapters."""

from collections.abc import Iterable, Mapping

from hardware.interfaces import (
    WAVELENGTHS_NM,
    PowerMeter,
    validate_wavelength_readings,
)
from op815_driver import OP815


class SantecPowerMeter:
    """Application adapter around the unchanged OP815 DLL driver."""

    def __init__(self, dll_path=None, driver=None):
        self._driver = driver if driver is not None else OP815(dll_path=dll_path)

    @property
    def description(self):
        return self._driver.description

    @property
    def usb_serial(self):
        return self._driver.usb_serial

    def find_devices(self):
        """List connected OP815 meters without opening remote mode."""
        return self._driver.find_devices()

    def connect(self):
        self._driver.connect()

    def set_trace_callback(self, callback):
        """Enable optional diagnostic tracing on the wrapped OP815 driver."""
        setter = getattr(self._driver, "set_trace_callback", None)
        if setter is not None:
            setter(callback)

    def set_trace_context(self, **context):
        """Attach the current diagnostic measurement context to trace events."""
        setter = getattr(self._driver, "set_trace_context", None)
        if setter is not None:
            setter(**context)

    def set_trace_metadata(self, **metadata):
        """Attach session metadata without changing normal meter behavior."""
        setter = getattr(self._driver, "set_trace_metadata", None)
        if setter is not None:
            setter(**metadata)

    def set_diagnostic_verification(self, enabled):
        """Enable final wavelength checks for Power Measurement Diagnostics."""
        setter = getattr(self._driver, "set_diagnostic_verification", None)
        if setter is not None:
            setter(enabled)

    def measure_both_wavelengths(self):
        return self._driver.measure_both_wavelengths()

    def measure_reference_wavelengths(self):
        return self._driver.measure_reference_wavelengths()

    def close(self):
        self._driver.close()


class SimulatedPowerMeter:
    """Deterministic power meter for tests and UI development.

    When ``readings`` is supplied, each measurement consumes the next mapping.
    After the final mapping, the last mapping is reused. Without supplied
    readings, the default values produce 1.7200 dB at 1310 nm and 1.3800 dB at
    1550 nm with the application's current reference powers.
    """

    def __init__(self, readings: Iterable[Mapping[int, float]] | None = None):
        self.description = "Simulated OP815"
        self.usb_serial = "SIMULATED"
        self._readings = iter(readings or ({1310: -1.0, 1550: -1.1},))
        self._last_reading = None
        self.connected = False

    def connect(self):
        self.connected = True

    def measure_both_wavelengths(self):
        if not self.connected:
            raise RuntimeError("Simulated power meter is not connected.")

        try:
            reading = next(self._readings)
        except StopIteration:
            if self._last_reading is None:
                raise RuntimeError("The simulated power meter has no readings.")
            reading = self._last_reading

        validate_wavelength_readings(reading, WAVELENGTHS_NM)

        self._last_reading = dict(reading)
        return dict(self._last_reading)

    def measure_reference_wavelengths(self):
        return self.measure_both_wavelengths()

    def close(self):
        self.connected = False


__all__ = ["PowerMeter", "SantecPowerMeter", "SimulatedPowerMeter"]
