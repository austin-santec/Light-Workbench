"""Application-facing integrated ILM and simulated power-meter adapters."""

from collections.abc import Iterable, Mapping
from dataclasses import replace

from hardware.interfaces import (
    WAVELENGTHS_NM,
    PowerMeter,
    validate_wavelength_readings,
)
from domain.models import ConnectionState, DeviceCategory, DeviceInfo
from domain.wavelengths import (
    MeasurementConfiguration,
    SM_SOURCE_PROFILE,
    SourceCapabilityProfile,
    measurement_configuration,
)
from op815_driver import OP815


class SantecPowerMeter:
    """Application adapter around the unchanged OP815 DLL driver."""

    def __init__(
        self,
        dll_path=None,
        driver=None,
        source_profile: SourceCapabilityProfile = SM_SOURCE_PROFILE,
    ):
        self._driver = driver if driver is not None else OP815(dll_path=dll_path)
        self._source_profile = source_profile
        self._measurement_configuration = measurement_configuration(
            "SM", source_profile
        )

    @property
    def description(self):
        return self._driver.description

    @property
    def usb_serial(self):
        return self._driver.usb_serial

    def get_device_info(
        self,
        state=ConnectionState.DISCONNECTED,
        error="",
    ):
        """Expose the wrapped driver identity through the hardware boundary."""
        info = self._driver.get_device_info(state=state, error=error)
        return replace(
            info,
            source_profile_id=self._source_profile.profile_id,
            source_profile_origin=self._source_profile.origin,
            source_mode=self._source_profile.mode.value,
            source_ids=self._source_profile.ordered_source_ids,
            source_wavelengths_nm=self._source_profile.ordered_wavelengths_nm,
        )

    def find_devices(self):
        """List connected OP815 meters without opening remote mode."""
        return self._driver.find_devices()

    def connect(self):
        self._driver.connect()
        self.configure_measurement(self._measurement_configuration)

    def source_capability_profile(self):
        return self._source_profile

    def configure_measurement(self, configuration: MeasurementConfiguration):
        if not isinstance(configuration, MeasurementConfiguration):
            raise TypeError("A MeasurementConfiguration is required.")
        self._measurement_configuration = configuration
        setter = getattr(self._driver, "configure_measurement", None)
        if setter is not None:
            setter(configuration)

    def set_trace_callback(self, callback):
        """Enable optional diagnostic tracing on the wrapped OP815 driver."""
        setter = getattr(self._driver, "set_trace_callback", None)
        if setter is not None:
            setter(callback)

    def add_trace_callback(self, callback):
        """Subscribe a trace consumer without replacing diagnostic tracing."""
        setter = getattr(self._driver, "add_trace_callback", None)
        if setter is not None:
            setter(callback)

    def remove_trace_callback(self, callback):
        """Remove one subscribed trace consumer."""
        remover = getattr(self._driver, "remove_trace_callback", None)
        if remover is not None:
            remover(callback)

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

    def __init__(
        self,
        readings: Iterable[Mapping[int, float]] | None = None,
        source_profile: SourceCapabilityProfile = SM_SOURCE_PROFILE,
    ):
        self.description = "Simulated OP815"
        self.usb_serial = "SIMULATED"
        self._readings = iter(readings or ({1310: -1.0, 1550: -1.1},))
        self._last_reading = None
        self.connected = False
        self._source_profile = source_profile
        self._measurement_configuration = measurement_configuration(
            "SM", source_profile
        )

    def connect(self):
        self.connected = True

    def source_capability_profile(self):
        return self._source_profile

    def configure_measurement(self, configuration: MeasurementConfiguration):
        if not configuration.is_supported:
            raise ValueError(
                "The simulated source profile cannot provide the selected mode."
            )
        self._measurement_configuration = configuration

    def get_device_info(
        self,
        state=ConnectionState.DISCONNECTED,
        error="",
    ):
        """Expose a deterministic identity for UI and hardware-free tests."""
        return DeviceInfo(
            category=DeviceCategory.POWER_METER,
            manufacturer="Santec",
            model="Simulated OP815",
            serial_number=self.usb_serial,
            raw_identity=self.description,
            state=state,
            error=error,
            source_profile_id=self._source_profile.profile_id,
            source_profile_origin=self._source_profile.origin,
            source_mode=self._source_profile.mode.value,
            source_ids=self._source_profile.ordered_source_ids,
            source_wavelengths_nm=self._source_profile.ordered_wavelengths_nm,
        )

    def measure_both_wavelengths(self):
        if not self.connected:
            raise RuntimeError("Simulated power meter is not connected.")

        try:
            reading = next(self._readings)
        except StopIteration:
            if self._last_reading is None:
                raise RuntimeError("The simulated power meter has no readings.")
            reading = self._last_reading

        validate_wavelength_readings(
            reading, self._measurement_configuration.opm_wavelengths_nm
        )

        self._last_reading = dict(reading)
        return dict(self._last_reading)

    def measure_reference_wavelengths(self):
        return self.measure_both_wavelengths()

    def close(self):
        self.connected = False


__all__ = ["PowerMeter", "SantecPowerMeter", "SimulatedPowerMeter"]
