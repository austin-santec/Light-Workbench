"""Compatibility facade for hardware power-meter adapters."""

from hardware.interfaces import PowerMeter
from hardware.power_meter import SantecPowerMeter, SimulatedPowerMeter

__all__ = ["PowerMeter", "SantecPowerMeter", "SimulatedPowerMeter"]
