import unittest
from unittest.mock import patch

from op815_driver import OP815


class OP815CleanupTests(unittest.TestCase):
    def test_complete_measurement_trace_links_both_wavelengths_and_references(self):
        driver = OP815.__new__(OP815)
        events = []
        state = {"wavelength": 1310}
        driver._trace_callback = events.append
        driver._trace_context = {
            "measurement_id": 11,
            "method": "Manual",
            "channel": 3,
            "physical_port": 103,
            "reference_1310_dbm": -0.04,
            "reference_1550_dbm": 0.14,
        }
        driver._trace_metadata = {"application_version": "1.10.0"}
        driver.description = "OP815"
        driver.usb_serial = "meter-11"

        def get_wavelength(wavelength, index, count):
            wavelength._obj.value = state["wavelength"]
            index._obj.value = 0 if state["wavelength"] == 1310 else 1
            count._obj.value = 2
            return 1

        def set_wavelength(wavelength):
            state["wavelength"] = wavelength
            return 1

        def read_power(power):
            power._obj.value = {
                1310: -0.94,
                1550: -0.50,
            }[state["wavelength"]]
            return 1

        driver.get_wavelength = get_wavelength
        driver.set_wavelength = set_wavelength
        driver.source_on = lambda _source_id, _state: 1
        driver.read_power = read_power

        with patch("op815_driver.time.sleep"):
            measurements = driver.measure_both_wavelengths(
                wavelength_settling_seconds=0,
                source_settling_seconds=0,
                source_off_settling_seconds=0,
            )

        read_events = [event for event in events if event["event"] == "read_power"]
        self.assertEqual(measurements, {1310: -0.94, 1550: -0.50})
        self.assertEqual([event["requested_wavelength_nm"] for event in read_events], [1310, 1550])
        self.assertEqual([event["measurement_id"] for event in read_events], [11, 11])
        self.assertEqual(
            [event["reference_power_dbm"] for event in read_events],
            [-0.04, 0.14],
        )
        self.assertEqual([event["source_id"] for event in read_events], [0, 1])

    def test_close_leaves_remote_mode_even_when_source_shutdown_fails(self):
        driver = OP815.__new__(OP815)
        driver.driver_open = True
        driver.remote_enabled = True
        calls = []

        def source_on(_source_id, _state):
            calls.append("source")
            raise RuntimeError("source shutdown failed")

        driver.source_on = source_on
        driver.remote_mode = lambda state: calls.append(("remote", state))
        driver.close_driver = lambda: calls.append("close")

        with self.assertRaisesRegex(RuntimeError, "source shutdown failed"):
            driver.close()

        self.assertIn(("remote", 0), calls)
        self.assertIn("close", calls)
        self.assertFalse(driver.remote_enabled)
        self.assertFalse(driver.driver_open)

    def test_close_releases_usb_device_after_driver_open_failure(self):
        driver = OP815.__new__(OP815)
        driver.usb_device_open = True
        driver.usb_handle = 123
        driver.driver_open = False
        driver.remote_enabled = False
        calls = []
        driver.close_driver = lambda: calls.append("close")

        driver.close()

        self.assertEqual(calls, ["close"])
        self.assertFalse(driver.usb_device_open)
        self.assertIsNone(driver.usb_handle)

    def test_connect_cleans_up_when_open_driver_fails(self):
        driver = OP815.__new__(OP815)
        driver.usb_device_open = False
        driver.usb_handle = None
        driver.driver_open = False
        driver.remote_enabled = False
        driver.select_device = lambda: (0, "OP815", "ILM-1")
        driver.open_usb_device = lambda _index, _handle: 1
        driver.open_driver = lambda _handle: -4
        calls = []
        driver.close_driver = lambda: calls.append("close")

        with self.assertRaisesRegex(RuntimeError, "OpenDriver failed with status -4"):
            driver.connect()

        self.assertEqual(calls, ["close"])
        self.assertFalse(driver.usb_device_open)
        self.assertFalse(driver.driver_open)

    def test_connect_cleans_up_when_remote_mode_fails(self):
        driver = OP815.__new__(OP815)
        driver.usb_device_open = False
        driver.usb_handle = None
        driver.driver_open = False
        driver.remote_enabled = False
        driver.select_device = lambda: (0, "OP815", "ILM-1")
        driver.open_usb_device = lambda _index, _handle: 1
        driver.open_driver = lambda _handle: 1
        driver.remote_mode = lambda _state: -1
        calls = []
        driver.close_driver = lambda: calls.append("close")

        with self.assertRaisesRegex(RuntimeError, "RemoteMode\(1\) failed"):
            driver.connect()

        self.assertEqual(calls, ["close"])
        self.assertFalse(driver.usb_device_open)
        self.assertFalse(driver.driver_open)


if __name__ == "__main__":
    unittest.main()
