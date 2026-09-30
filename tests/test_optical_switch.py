import unittest
from unittest.mock import patch

from domain.models import ConnectionState, DeviceCategory
from hardware.optical_switch import (
    OSX150 as HardwareOSX150,
    detect_santec_switch_model,
)
from osx150_driver import OSX150


class OpticalSwitchAdapterTests(unittest.TestCase):
    def test_legacy_module_reexports_hardware_adapter(self):
        self.assertIs(OSX150, HardwareOSX150)

    def test_santec_resource_filter_requires_expected_usb_identity(self):
        self.assertTrue(
            HardwareOSX150._is_santec_usb_resource(
                "USB0::0x2428::0xD00D::SWITCH::INSTR"
            )
        )
        self.assertFalse(
            HardwareOSX150._is_santec_usb_resource(
                "USB0::0x1111::0xD00D::SWITCH::INSTR"
            )
        )
        self.assertFalse(
            HardwareOSX150._is_santec_usb_resource(
                "TCPIP0::192.0.2.10::inst0::INSTR"
            )
        )

    def test_santec_model_detection_is_ready_for_future_profiles(self):
        self.assertEqual(
            detect_santec_switch_model("SANTEC,OSX-150,SW-1,1.0"),
            "OSX-150",
        )
        self.assertEqual(
            detect_santec_switch_model("SANTEC,OSX-100,SW-2,1.0"),
            "OSX-100",
        )
        self.assertIsNone(detect_santec_switch_model("SANTEC,UNKNOWN,SW-3,1.0"))

    def test_switch_identity_reports_model_and_connection_state(self):
        switch = HardwareOSX150()

        info = switch.get_device_info(state=ConnectionState.CONNECTED)

        self.assertEqual(info.category, DeviceCategory.OPTICAL_SWITCH)
        self.assertEqual(info.model, "OSX-150")
        self.assertEqual(info.state, ConnectionState.CONNECTED)

    def test_supported_profile_connects_and_preserves_identity(self):
        class Instrument:
            def __init__(self, identity):
                self.identity = identity
                self.closed = False

            def query(self, command):
                if command != "*IDN?":
                    raise AssertionError("Unexpected VISA query: %s" % command)
                return self.identity

            def close(self):
                self.closed = True

        class ResourceManager:
            def __init__(self):
                self.instrument = Instrument("SANTEC,OSX-150,SW-150,1.0")

            def list_resources(self):
                return ("USB0::0x2428::0xD00D::SW-150::INSTR",)

            def open_resource(self, _address):
                return self.instrument

            def close(self):
                pass

        switch = HardwareOSX150()
        with patch("hardware.optical_switch.pyvisa.ResourceManager", ResourceManager):
            switch.connect()

        info = switch.get_device_info(state=ConnectionState.CONNECTED)
        self.assertEqual(info.model, "OSX-150")
        self.assertEqual(info.serial_number, "SW-150")
        switch.close()

    def test_recognized_future_profile_is_rejected_with_identity(self):
        class Instrument:
            def query(self, _command):
                return "SANTEC,OSX-100,SW-100,1.0"

            def close(self):
                pass

        class ResourceManager:
            def list_resources(self):
                return ("USB0::0x2428::0xD00D::SW-100::INSTR",)

            def open_resource(self, _address):
                return Instrument()

            def close(self):
                pass

        switch = HardwareOSX150()
        with patch("hardware.optical_switch.pyvisa.ResourceManager", ResourceManager):
            with self.assertRaisesRegex(RuntimeError, "OSX-100.*not yet supported"):
                switch.connect()


if __name__ == "__main__":
    unittest.main()
