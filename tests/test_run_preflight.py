import unittest

from application.run_preflight import (
    RunPreflightIssueCategory,
    validate_run_preflight,
)
from domain.models import ChannelMode


def complete_metadata():
    return {
        "Main board serial": "19063",
        "Switch serial": "20263546992",
        "Part number": "50-1-A-024",
        "Operating band": "O band",
        "Tested by": "AJ",
    }


def valid_kwargs(**overrides):
    values = {
        "admin_mode": False,
        "metadata": complete_metadata(),
        "run_number": 1,
        "channel_mode": ChannelMode.FULL_CONFIGURED_PASS,
        "single_channel": 1,
        "channel_ranges": "",
        "manual_channel_order": False,
        "hardware_ready": True,
        "reference_valid": True,
        "reference_state": "valid_calculated",
        "reference_method": "calculated",
        "reference_hardware_matches": True,
    }
    values.update(overrides)
    return values


class RunPreflightTests(unittest.TestCase):
    def test_complete_normal_setup_passes(self):
        result = validate_run_preflight(**valid_kwargs())

        self.assertTrue(result.is_valid_for_normal_operator)
        self.assertTrue(result.is_valid_for_admin)
        self.assertIsNotNone(result.plan)

    def test_all_missing_metadata_is_reported_together(self):
        result = validate_run_preflight(
            **valid_kwargs(
                metadata={"Operating band": "O band"},
            )
        )

        self.assertEqual(
            {issue.code for issue in result.metadata_issues},
            {
                "missing_main_board_serial",
                "missing_switch_serial",
                "missing_part_number",
                "missing_tested_by",
            },
        )
        self.assertFalse(result.is_valid_for_normal_operator)

    def test_invalid_run_number_and_operating_band_are_blocking_for_normal_user(self):
        result = validate_run_preflight(
            **valid_kwargs(
                metadata={**complete_metadata(), "Operating band": "invalid"},
                run_number=0,
            )
        )

        self.assertEqual(
            {issue.code for issue in result.issues},
            {"invalid_run_number", "invalid_operating_band"},
        )

    def test_channel_modes_use_existing_planner_rules(self):
        single = validate_run_preflight(
            **valid_kwargs(
                channel_mode=ChannelMode.SINGLE_CHANNEL,
                single_channel=8,
            )
        )
        specific = validate_run_preflight(
            **valid_kwargs(
                channel_mode=ChannelMode.SPECIFIC_CHANNELS,
                channel_ranges="1, 4-6",
            )
        )

        self.assertEqual(single.plan.channels, (8,))
        self.assertEqual(specific.plan.channels, (1, 4, 5, 6))

    def test_missing_or_invalid_channel_selection_is_reported(self):
        missing = validate_run_preflight(
            **valid_kwargs(
                channel_mode=ChannelMode.SPECIFIC_CHANNELS,
                channel_ranges="",
            )
        )
        invalid = validate_run_preflight(
            **valid_kwargs(
                channel_mode=ChannelMode.SPECIFIC_CHANNELS,
                channel_ranges="4-2",
            )
        )

        self.assertEqual(
            missing.issues[0].code,
            "missing_channel_selection",
        )
        self.assertEqual(invalid.issues[0].code, "invalid_channel_selection")

    def test_hardware_and_reference_failures_are_non_bypassable(self):
        result = validate_run_preflight(
            **valid_kwargs(
                admin_mode=True,
                hardware_ready=False,
                reference_valid=False,
                reference_state="invalidated",
            )
        )

        self.assertEqual(
            {issue.code for issue in result.blocking_issues},
            {"hardware_not_ready", "reference_invalidated"},
        )
        self.assertFalse(result.is_valid_for_admin)

    def test_admin_manual_reference_is_authorized_but_missing_metadata_is_bypassable(self):
        result = validate_run_preflight(
            **valid_kwargs(
                admin_mode=True,
                metadata={"Operating band": "O band"},
                reference_method="manual_admin",
            )
        )

        self.assertTrue(result.is_valid_for_admin)
        self.assertFalse(result.is_valid_for_normal_operator)
        self.assertTrue(
            all(
                issue.category is RunPreflightIssueCategory.METADATA
                for issue in result.issues
            )
        )

    def test_display_values_do_not_authorize_a_missing_reference(self):
        result = validate_run_preflight(
            **valid_kwargs(
                reference_valid=False,
                reference_state="not_referenced",
                reference_method="",
            )
        )

        self.assertEqual(
            [issue.code for issue in result.issues],
            ["reference_not_calculated"],
        )

    def test_validation_does_not_mutate_metadata(self):
        metadata = complete_metadata()
        before = dict(metadata)

        validate_run_preflight(**valid_kwargs(metadata=metadata))

        self.assertEqual(metadata, before)


if __name__ == "__main__":
    unittest.main()
