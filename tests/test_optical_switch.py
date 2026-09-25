import unittest

from hardware.optical_switch import OSX150 as HardwareOSX150
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


if __name__ == "__main__":
    unittest.main()
