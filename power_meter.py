"""Power-meter interfaces used by the measurement workflow.

The real adapter delegates to the existing OP815 driver, which continues to
own all ctypes and OP815M.dll behavior. The simulated adapter provides the same
small application-facing contract without requiring hardware.
"""

from collections.abc import Iterable, Mapping
from typing import Protocol

from op815_driver import OP815, WAVELENGTHS_NM


class PowerMeter(Protocol):
    """Application-facing contract for an ILM power meter."""

    description: str | None
    usb_serial: str | None

    def connect(self) -> None:
        """Connect to the meter and prepare it for measurements."""

    def measure_both_wavelengths(self) -> Mapping[int, float]:
        """Return absolute dBm readings keyed by wavelength in nanometers."""

    def measure_reference_wavelengths(self) -> Mapping[int, float]:
        """Return one stabilized absolute reading per wavelength for calibration."""

    def close(self) -> None:
        """Stop measurement activity and release the meter."""


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

    def connect(self):
        self._driver.connect()

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

        missing_wavelengths = set(WAVELENGTHS_NM) - set(reading)
        if missing_wavelengths:
            raise ValueError(
                "Simulated reading is missing wavelength(s): %s"
                % ", ".join(str(wavelength) for wavelength in sorted(missing_wavelengths))
            )

        self._last_reading = dict(reading)
        return dict(self._last_reading)

    def measure_reference_wavelengths(self):
        return self.measure_both_wavelengths()

    def close(self):
        self.connected = False
