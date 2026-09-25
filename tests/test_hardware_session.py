import unittest

from application.hardware_planning import build_hardware_run_plan
from application.hardware_session import HardwareRunSession
from hardware.session import OpticalTestSession


class FakeDevice:
    def __init__(self, name, fail_connect=False):
        self.name = name
        self.fail_connect = fail_connect
        self.connected = False
        self.closed = False
        self.events = []

    def connect(self):
        self.events.append("connect")
        if self.fail_connect:
            raise RuntimeError("%s failed" % self.name)
        self.connected = True

    def close(self):
        self.events.append("close")
        self.closed = True
        self.connected = False


class FakeLaser(FakeDevice):
    description = "Fake laser"
    serial_number = "LASER"

    def set_wavelength(self, _wavelength_nm):
        self.events.append("wavelength")

    def set_output(self, enabled):
        self.events.append("output:%s" % enabled)


class HardwareSessionTests(unittest.TestCase):
    def test_application_session_begin_resets_pending_state_from_plan(self):
        session = HardwareRunSession(
            pending_channel=7,
            pending_physical_port=7,
            pending_reading=(7, 7, 1.0, 1.1),
        )
        plan = build_hardware_run_plan(
            "Full configured pass",
            manual_channel_order=True,
        )

        session.begin(retest=False, plan=plan)

        self.assertTrue(session.full_pass)
        self.assertTrue(session.manual_channel_order)
        self.assertIsNone(session.pending_channel)
        self.assertIsNone(session.pending_reading)

    def test_application_session_tracks_pending_reading_without_writing(self):
        session = HardwareRunSession()
        session.set_configured_channel_count(48)
        session.set_pending_channel(13, 49)
        session.set_pending_reading(13, 49, 1.25, 1.35)

        self.assertEqual(session.configured_channel_count, 48)
        self.assertEqual(session.pending_reading, (13, 49, 1.25, 1.35))

    def test_application_session_clear_pending_discards_uncommitted_reading(self):
        session = HardwareRunSession()
        session.set_pending_channel(2, 2)
        session.set_pending_reading(2, 2, 1.0, 1.0)

        session.clear_pending()

        self.assertIsNone(session.pending_channel)
        self.assertIsNone(session.pending_physical_port)
        self.assertIsNone(session.pending_reading)

    def test_session_connects_and_closes_in_composed_order(self):
        laser = FakeLaser("laser")
        meter = FakeDevice("meter")
        switch = FakeDevice("switch")
        session = OpticalTestSession(meter, switch, laser)

        session.connect()
        self.assertTrue(session.connected)
        session.set_wavelength(1310)
        session.set_laser_output(True)
        session.close()

        self.assertEqual(laser.events, ["connect", "wavelength", "output:True", "close"])
        self.assertEqual(meter.events, ["connect", "close"])
        self.assertEqual(switch.events, ["connect", "close"])

    def test_partial_connect_closes_already_connected_devices(self):
        laser = FakeLaser("laser")
        meter = FakeDevice("meter", fail_connect=True)
        session = OpticalTestSession(meter, laser_source=laser)

        with self.assertRaisesRegex(RuntimeError, "meter failed"):
            session.connect()

        self.assertFalse(session.connected)
        self.assertTrue(laser.closed)
        self.assertEqual(laser.events, ["connect", "close"])


if __name__ == "__main__":
    unittest.main()
