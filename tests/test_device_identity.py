import unittest

from domain.models import ConnectionState, DeviceCategory, DeviceInfo
from hardware.device_identity import device_info_for


class LegacyMeter:
    description = "Legacy OP815"
    usb_serial = "METER-1"


class DeviceIdentityTests(unittest.TestCase):
    def test_device_info_is_vendor_neutral_and_transient(self):
        info = DeviceInfo(
            category=DeviceCategory.POWER_METER,
            manufacturer="Santec",
            model="OP815",
            serial_number="METER-1",
            state=ConnectionState.CONNECTED,
        )

        self.assertEqual(info.category, DeviceCategory.POWER_METER)
        self.assertEqual(info.state, ConnectionState.CONNECTED)
        self.assertEqual(info.with_state(ConnectionState.ERROR).error, "")
        self.assertEqual(info.state, ConnectionState.CONNECTED)

    def test_older_adapter_falls_back_to_existing_identity_fields(self):
        info = device_info_for(
            LegacyMeter(),
            DeviceCategory.POWER_METER,
            state=ConnectionState.CONNECTING,
        )

        self.assertEqual(info.model, "Legacy OP815")
        self.assertEqual(info.serial_number, "METER-1")
        self.assertEqual(info.state, ConnectionState.CONNECTING)


if __name__ == "__main__":
    unittest.main()
