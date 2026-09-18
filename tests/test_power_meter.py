import unittest

from power_meter import SantecPowerMeter, SimulatedPowerMeter


class FakeOP815:
    description = "Fake OP815"
    usb_serial = "FAKE-123"

    def __init__(self):
        self.connected = False
        self.closed = False

    def connect(self):
        self.connected = True

    def measure_both_wavelengths(self):
        return {1310: -1.25, 1550: -1.05}

    def close(self):
        self.closed = True


class PowerMeterTests(unittest.TestCase):
    def test_santec_adapter_delegates_without_changing_driver(self):
        driver = FakeOP815()
        meter = SantecPowerMeter(driver=driver)

        self.assertEqual(meter.description, "Fake OP815")
        self.assertEqual(meter.usb_serial, "FAKE-123")
        meter.connect()
        self.assertTrue(driver.connected)
        self.assertEqual(
            meter.measure_both_wavelengths(),
            {1310: -1.25, 1550: -1.05},
        )
        meter.close()
        self.assertTrue(driver.closed)

    def test_simulated_meter_requires_connection(self):
        meter = SimulatedPowerMeter([{1310: -1.0, 1550: -1.1}])

        with self.assertRaises(RuntimeError):
            meter.measure_both_wavelengths()

        meter.connect()
        self.assertEqual(
            meter.measure_both_wavelengths(),
            {1310: -1.0, 1550: -1.1},
        )

    def test_simulated_meter_reuses_last_reading(self):
        meter = SimulatedPowerMeter([{1310: -1.0, 1550: -1.1}])
        meter.connect()

        first_reading = meter.measure_both_wavelengths()
        second_reading = meter.measure_both_wavelengths()

        self.assertEqual(second_reading, first_reading)
        self.assertIsNot(second_reading, first_reading)

    def test_simulated_meter_rejects_missing_wavelength(self):
        meter = SimulatedPowerMeter([{1310: -1.0}])
        meter.connect()

        with self.assertRaisesRegex(ValueError, "1550"):
            meter.measure_both_wavelengths()


if __name__ == "__main__":
    unittest.main()
