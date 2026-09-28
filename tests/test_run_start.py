import unittest

from application.run_start import (
    HardwareRunPreparation,
    build_hardware_run_request,
    prepare_hardware_run,
)


class RunStartPreparationTests(unittest.TestCase):
    def test_full_pass_is_normalized_without_hardware_access(self):
        preparation = prepare_hardware_run(
            retest=False,
            requested_channels=None,
            channel_mode="Full configured pass",
            manual_channel_order=True,
        )

        self.assertIsNone(preparation.channels)
        self.assertTrue(preparation.full_pass)
        self.assertTrue(preparation.manual_channel_order)
        self.assertIsNotNone(preparation.plan)

    def test_retest_preserves_requested_channels_without_a_new_plan(self):
        preparation = prepare_hardware_run(
            retest=True,
            requested_channels=[7, 3],
            channel_mode="Full configured pass",
        )

        self.assertEqual(preparation.channels, [7, 3])
        self.assertIsNone(preparation.plan)
        self.assertFalse(preparation.full_pass)

    def test_request_transfers_adapters_and_resume_flags(self):
        meter = object()
        switch = object()
        preparation = HardwareRunPreparation(
            channels=None,
            plan=None,
            full_pass=True,
            manual_channel_order=False,
        )

        request = build_hardware_run_request(
            preparation,
            meter=meter,
            switch=switch,
            reference_powers={1310: 0.72, 1550: 0.28},
            existing_channels=[1, 2],
            resume_existing=True,
            live_write_mode=True,
        )

        self.assertIs(request.power_meter_factory(), meter)
        self.assertIs(request.switch_factory(), switch)
        self.assertTrue(request.resume_existing)
        self.assertTrue(request.resume_full_pass)
        self.assertTrue(request.live_write_mode)
        self.assertEqual(request.existing_channels, [1, 2])
        self.assertEqual(request.live_write_interval, 0.25)


if __name__ == "__main__":
    unittest.main()
