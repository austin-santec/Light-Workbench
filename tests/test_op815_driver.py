import unittest

from op815_driver import OP815


class OP815CleanupTests(unittest.TestCase):
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
