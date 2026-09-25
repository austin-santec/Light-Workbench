import unittest

from application.hardware_planning import (
    HardwareRunPlan,
    build_hardware_run_plan,
    parse_hardware_channels,
)
from domain.models import ChannelMode


class HardwarePlanningTests(unittest.TestCase):
    def test_parser_preserves_order_and_removes_duplicates(self):
        self.assertEqual(
            parse_hardware_channels("3, 1-3, 7"),
            [3, 1, 2, 7],
        )

    def test_parser_rejects_invalid_ranges(self):
        with self.assertRaisesRegex(ValueError, "Invalid range"):
            parse_hardware_channels("4-2")

    def test_full_pass_delegates_channel_count_to_switch(self):
        plan = build_hardware_run_plan(
            ChannelMode.FULL_CONFIGURED_PASS,
            manual_channel_order=True,
        )

        self.assertEqual(
            plan,
            HardwareRunPlan(
                mode=ChannelMode.FULL_CONFIGURED_PASS,
                channels=None,
                full_pass=True,
                manual_channel_order=True,
            ),
        )
        self.assertIsNone(plan.worker_channels())

    def test_single_channel_plan_is_normalized(self):
        plan = build_hardware_run_plan("Single channel", single_channel=13)

        self.assertEqual(plan.mode, ChannelMode.SINGLE_CHANNEL)
        self.assertEqual(plan.worker_channels(), [13])
        self.assertFalse(plan.full_pass)
        self.assertFalse(plan.manual_channel_order)

    def test_specific_channel_plan_uses_same_parser(self):
        plan = build_hardware_run_plan(
            2,
            channel_ranges="10-12, 20",
            manual_channel_order=True,
        )

        self.assertEqual(plan.mode, ChannelMode.SPECIFIC_CHANNELS)
        self.assertEqual(plan.worker_channels(), [10, 11, 12, 20])
        self.assertFalse(plan.manual_channel_order)

    def test_invalid_mode_is_reported_before_hardware_setup(self):
        with self.assertRaisesRegex(ValueError, "Unknown hardware channel mode"):
            build_hardware_run_plan("not a mode")


if __name__ == "__main__":
    unittest.main()
