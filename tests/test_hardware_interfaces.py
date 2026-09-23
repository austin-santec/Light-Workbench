import unittest

from hardware.interfaces import (
    LaserSource,
    OpticalSwitch,
    PowerMeter,
    validate_wavelength_readings,
)
from power_meter import SimulatedPowerMeter


class FakeLaser:
    description = "Fake laser"
    serial_number = "LASER-1"

    def connect(self):
        pass

    def set_wavelength(self, wavelength_nm):
        pass

    def set_output(self, enabled):
        pass

    def close(self):
        pass


class FakeSwitch:
    def connect(self):
        pass

    def configured_channel_count(self):
        return 48

    def set_channel(self, channel):
        return channel

    def close(self):
        pass


class HardwareInterfaceTests(unittest.TestCase):
    def test_existing_simulated_meter_satisfies_power_meter_contract(self):
        self.assertIsInstance(SimulatedPowerMeter(), PowerMeter)

    def test_future_laser_and_switch_shapes_satisfy_contracts(self):
        self.assertIsInstance(FakeLaser(), LaserSource)
        self.assertIsInstance(FakeSwitch(), OpticalSwitch)

    def test_reading_validation_requires_current_workflow_wavelengths(self):
        with self.assertRaisesRegex(ValueError, "1550"):
            validate_wavelength_readings({1310: -1.0})


if __name__ == "__main__":
    unittest.main()
