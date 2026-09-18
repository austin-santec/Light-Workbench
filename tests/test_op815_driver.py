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


if __name__ == "__main__":
    unittest.main()
