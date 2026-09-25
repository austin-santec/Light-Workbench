import unittest

from hardware.interfaces import LaserSource, OpticalSwitch
from hardware.simulated import SimulatedLaserSource, SimulatedOpticalSwitch


class SimulatedHardwareTests(unittest.TestCase):
    def test_simulated_switch_routes_channels_and_tracks_selection(self):
        switch = SimulatedOpticalSwitch(3, [101, 102, 103])
        switch.connect()

        self.assertIsInstance(switch, OpticalSwitch)
        self.assertEqual(switch.configured_channel_count(), 3)
        self.assertEqual(switch.set_channel(2), 102)
        self.assertEqual(switch.selected_channels, [2])

        switch.close()
        with self.assertRaises(RuntimeError):
            switch.set_channel(1)

    def test_simulated_laser_validates_connection_and_wavelength(self):
        laser = SimulatedLaserSource()
        self.assertIsInstance(laser, LaserSource)
        with self.assertRaises(RuntimeError):
            laser.set_output(True)

        laser.connect()
        laser.set_wavelength(1310)
        laser.set_output(True)
        self.assertTrue(laser.output_enabled)
        laser.close()
        self.assertFalse(laser.output_enabled)


if __name__ == "__main__":
    unittest.main()
