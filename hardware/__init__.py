"""Hardware ports used by Light Workbench.

Concrete vendor integrations are loaded lazily by the hardware factory. New
application code should import contracts from ``hardware.interfaces`` rather
than importing a vendor driver directly.
"""

from .interfaces import LaserSource, OpticalSwitch, PowerMeter
from .factory import HardwareFactory
from .simulated import SimulatedLaserSource, SimulatedOpticalSwitch
from .session import OpticalTestSession

__all__ = [
    "HardwareFactory",
    "LaserSource",
    "OpticalSwitch",
    "PowerMeter",
    "OpticalTestSession",
    "SimulatedLaserSource",
    "SimulatedOpticalSwitch",
]
