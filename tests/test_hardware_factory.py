import unittest

from hardware.factory import HardwareFactory
from hardware.interfaces import OpticalSwitch, PowerMeter


class FakeMeter:
    description = "Fake meter"
    usb_serial = "FAKE-METER"

    def connect(self):
        pass

    def measure_both_wavelengths(self):
        return {1310: -1.0, 1550: -1.1}

    def measure_reference_wavelengths(self):
        return self.measure_both_wavelengths()

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


class HardwareFactoryTests(unittest.TestCase):
    def test_factory_creates_configured_capabilities(self):
        factory = HardwareFactory(FakeMeter, FakeSwitch)

        self.assertIsInstance(factory.create_power_meter(), PowerMeter)
        self.assertIsInstance(factory.create_switch(), OpticalSwitch)


if __name__ == "__main__":
    unittest.main()
