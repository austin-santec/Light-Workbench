import unittest

from application.run_start import (
    HardwareRunPreparation,
    build_hardware_run_request,
    evaluate_extra_port_offer_eligibility,
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
            front_panel_channel_count=48,
            offer_extra_ports=True,
            run_mode="continue",
            existing_extra_physical_ports=[49, 50],
            maximum_physical_port_probe=64,
        )

        self.assertIs(request.power_meter_factory(), meter)
        self.assertIs(request.switch_factory(), switch)
        self.assertTrue(request.resume_existing)
        self.assertTrue(request.resume_full_pass)
        self.assertTrue(request.live_write_mode)
        self.assertEqual(request.existing_channels, [1, 2])
        self.assertEqual(request.live_write_interval, 0.25)
        self.assertEqual(request.front_panel_channel_count, 48)
        self.assertTrue(request.offer_extra_ports)
        self.assertEqual(request.run_mode, "continue")
        self.assertEqual(request.existing_extra_physical_ports, [49, 50])
        self.assertEqual(request.maximum_physical_port_probe, 64)

    def test_extra_port_offer_allows_new_and_continued_full_passes(self):
        for run_mode in ("new", "continue"):
            decision = evaluate_extra_port_offer_eligibility(
                full_pass=True,
                manual_channel_order=False,
                retest=False,
                run_mode=run_mode,
                has_part_number=True,
            )
            self.assertTrue(decision.eligible)
            self.assertEqual(decision.reason, "eligible")

    def test_extra_port_offer_rejects_non_full_or_excluded_workflows(self):
        cases = (
            {"full_pass": False, "reason": "not_a_full_pass"},
            {"manual_channel_order": True, "reason": "manual_channel_order"},
            {"retest": True, "reason": "selected_retest"},
            {"run_mode": "unknown", "reason": "unsupported_run_mode"},
            {"has_part_number": False, "reason": "missing_part_number"},
        )
        for case in cases:
            values = {
                "full_pass": True,
                "manual_channel_order": False,
                "retest": False,
                "run_mode": "continue",
                "has_part_number": True,
            }
            expected_reason = case.pop("reason")
            values.update(case)
            decision = evaluate_extra_port_offer_eligibility(**values)
            self.assertFalse(decision.eligible)
            self.assertEqual(decision.reason, expected_reason)


if __name__ == "__main__":
    unittest.main()
