"""Configurable composition of vendor-neutral hardware capabilities."""

from collections.abc import Callable

from hardware.interfaces import LaserSource, OpticalSwitch, PowerMeter
from hardware.session import OpticalTestSession
from osx150_driver import OSX150
from power_meter import SantecPowerMeter


class HardwareFactory:
    """Create the hardware adapters selected for the current workstation.

    The default composition is the current integrated ILM plus OSX-150 switch.
    A future OPM-plus-laser configuration can provide a different meter or
    additional capabilities without adding vendor conditionals to the UI.
    """

    def __init__(
        self,
        power_meter_factory: Callable[[], PowerMeter] = SantecPowerMeter,
        switch_factory: Callable[[], OpticalSwitch] = OSX150,
        laser_source_factory: Callable[[], LaserSource] | None = None,
    ):
        self.power_meter_factory = power_meter_factory
        self.switch_factory = switch_factory
        self.laser_source_factory = laser_source_factory

    def create_power_meter(self) -> PowerMeter:
        """Create the configured power-meter adapter."""
        return self.power_meter_factory()

    def create_switch(self) -> OpticalSwitch:
        """Create the configured optical-switch adapter."""
        return self.switch_factory()

    def create_laser_source(self) -> LaserSource:
        """Create the optional separate laser adapter."""
        if self.laser_source_factory is None:
            raise RuntimeError("No separate laser source is configured.")
        return self.laser_source_factory()

    def create_session(self, include_switch: bool = True) -> OpticalTestSession:
        """Create a composed session for a future multi-instrument workflow."""
        return OpticalTestSession(
            self.create_power_meter(),
            self.create_switch() if include_switch else None,
            self.create_laser_source() if self.laser_source_factory else None,
        )


__all__ = ["HardwareFactory"]
