import math
import unittest
from pathlib import Path

from domain.coc_preparation import (
    CocSourceRun,
    infer_front_panel_channel_count,
    prepare_coc,
)
from domain.models import MeasurementRecord


CRITERIA = {
    "model": "OSX-150",
    "profile_name": "OSX-150 standard",
    "revision": "1",
    "too_good_below_db": 0.5,
    "warning_enabled": True,
    "warning_above_db": 2.25,
    "fail_above_db": 2.5,
}


def source(run_number, measurements, criteria=None, **metadata):
    values = {
        "Main board serial": "18901",
        "Part number": "OSX-150-1A-036-09-FA-00B-2FD",
        "Switch serial": "20263547099",
        "Operating band": "O band",
        "Run number": str(run_number),
    }
    values.update(metadata)
    return CocSourceRun(
        run_number,
        Path("Run-%d.csv" % run_number),
        tuple(measurements),
        values,
        dict(criteria or CRITERIA),
    )


class CocPreparationTests(unittest.TestCase):
    def test_base_run_only_preserves_logical_order_and_criteria(self):
        result = prepare_coc(
            source(
                1,
                [
                    MeasurementRecord(3, 1.3, 1.4, 3),
                    MeasurementRecord(1, 1.0, 1.1, 1),
                    MeasurementRecord(2, 1.1, 1.2, 2),
                ],
            ),
            3,
        )

        self.assertTrue(result.eligible)
        self.assertEqual([item.record.channel for item in result.channels], [1, 2, 3])
        self.assertEqual(result.supplemental_run_number, None)
        self.assertEqual(result.effective_criteria, CRITERIA)

    def test_unit_18901_style_replacements_create_complete_passing_report(self):
        baseline = [
            MeasurementRecord(channel, 1.0, 1.1, channel)
            for channel in range(1, 45)
        ]
        baseline[8] = MeasurementRecord(9, 2.4535, 2.0716, 9)
        baseline[19] = MeasurementRecord(20, 2.6424, 2.6015, 20)
        supplemental = [
            MeasurementRecord(9, 1.1379, 1.7147, 43),
            MeasurementRecord(20, 0.8637, 1.6157, 41),
        ]

        result = prepare_coc(
            source(1, baseline),
            36,
            supplemental_run=source(2, supplemental),
            completed_replacements=(
                {"current_port": 9, "replacement_port": 43},
                {"current_port": 20, "replacement_port": 41},
            ),
        )

        self.assertTrue(result.eligible)
        self.assertEqual([item.record.channel for item in result.channels], list(range(1, 37)))
        self.assertEqual(
            [
                (item.record.channel, item.source_run_number, item.physical_port)
                for item in result.overridden_channels
            ],
            [(9, 2, 43), (20, 2, 41)],
        )
        self.assertEqual(result.failures, ())
        self.assertEqual(result.optimization_channels, ())

    def test_complete_wavelength_pair_comes_from_supplemental_run(self):
        base = source(1, [MeasurementRecord(1, 2.4, 2.4, 1)])
        supplemental = source(2, [MeasurementRecord(1, 1.0, 1.1, 1)])
        result = prepare_coc(base, 1, supplemental_run=supplemental)
        self.assertEqual(result.measurements[0].loss_1310, 1.0)
        self.assertEqual(result.measurements[0].loss_1550, 1.1)

    def test_supplemental_replaces_only_matching_logical_channels(self):
        result = prepare_coc(
            source(
                1,
                [
                    MeasurementRecord(1, 1.0, 1.1, 1),
                    MeasurementRecord(2, 2.0, 2.1, 2),
                ],
            ),
            2,
            supplemental_run=source(
                2,
                [MeasurementRecord(2, 0.8, 0.9, 2)],
            ),
        )

        self.assertEqual(
            [(item.record.channel, item.source_run_number) for item in result.channels],
            [(1, 1), (2, 2)],
        )
        self.assertEqual([item.record.channel for item in result.overridden_channels], [2])

    def test_missing_negative_nonfinite_and_strict_limit_are_blocked(self):
        result = prepare_coc(
            source(
                1,
                [
                    MeasurementRecord(1, -0.0001, 1.0, 1),
                    MeasurementRecord(2, 2.5, math.inf, 2),
                ],
            ),
            3,
        )
        self.assertFalse(result.eligible)
        self.assertEqual(result.missing_channels, (3,))
        self.assertTrue(any(item.code == "negative_reading" for item in result.invalid_readings))
        self.assertTrue(any(item.code == "non_finite_reading" for item in result.invalid_readings))
        self.assertTrue(any(item.channel == 2 and item.value_db == 2.5 for item in result.failures))

    def test_formal_limit_uses_four_decimal_strict_less_than_comparison(self):
        below = prepare_coc(
            source(1, [MeasurementRecord(1, 2.4999, 2.4999, 1)]),
            1,
        )
        equal = prepare_coc(
            source(1, [MeasurementRecord(1, 2.5, 1.0, 1)]),
            1,
        )
        rounds_to_equal = prepare_coc(
            source(1, [MeasurementRecord(1, 2.49996, 1.0, 1)]),
            1,
        )
        above = prepare_coc(
            source(1, [MeasurementRecord(1, 2.5001, 1.0, 1)]),
            1,
        )

        self.assertTrue(below.eligible)
        self.assertFalse(equal.eligible)
        self.assertFalse(rounds_to_equal.eligible)
        self.assertFalse(above.eligible)

    def test_same_physical_port_retest_is_valid(self):
        result = prepare_coc(
            source(1, [MeasurementRecord(1, 1.2, 1.3, 1)]),
            1,
            supplemental_run=source(2, [MeasurementRecord(1, 1.0, 1.1, 1)]),
        )

        self.assertTrue(result.eligible)
        self.assertEqual(result.channels[0].source_run_number, 2)

    def test_different_reference_snapshots_are_allowed(self):
        result = prepare_coc(
            source(
                1,
                [MeasurementRecord(1, 1.2, 1.3, 1, {"snapshot_id": "base"})],
            ),
            1,
            supplemental_run=source(
                2,
                [MeasurementRecord(1, 1.0, 1.1, 1, {"snapshot_id": "retest"})],
            ),
        )

        self.assertTrue(result.eligible)
        self.assertEqual(
            result.channels[0].record.reference_snapshot["snapshot_id"],
            "retest",
        )

    def test_unrecorded_physical_port_change_is_blocked(self):
        result = prepare_coc(
            source(1, [MeasurementRecord(1, 1.0, 1.1, 1)]),
            1,
            supplemental_run=source(2, [MeasurementRecord(1, 0.9, 1.0, 43)]),
        )
        self.assertFalse(result.eligible)
        self.assertTrue(
            any(item.code == "unrecorded_physical_port_change" for item in result.validation_issues)
        )

    def test_incompatible_switch_serial_is_blocked(self):
        result = prepare_coc(
            source(1, [MeasurementRecord(1, 1.0, 1.1, 1)]),
            1,
            supplemental_run=source(
                2,
                [MeasurementRecord(1, 0.9, 1.0, 1)],
                **{"Switch serial": "different"},
            ),
        )
        self.assertFalse(result.eligible)
        self.assertTrue(
            any(item.code == "incompatible_switch_serial" for item in result.validation_issues)
        )

    def test_incompatible_unit_part_band_and_criteria_are_reported(self):
        supplemental = source(
            2,
            [MeasurementRecord(1, 0.9, 1.0, 1)],
            criteria={**CRITERIA, "fail_above_db": 2.4},
            **{
                "Main board serial": "different-unit",
                "Part number": "different-part",
                "Operating band": "C band",
            },
        )
        result = prepare_coc(
            source(1, [MeasurementRecord(1, 1.0, 1.1, 1)]),
            1,
            supplemental_run=supplemental,
        )
        codes = {item.code for item in result.validation_issues}

        self.assertFalse(result.eligible)
        self.assertIn("incompatible_main_board_serial", codes)
        self.assertIn("incompatible_part_number", codes)
        self.assertIn("incompatible_operating_band", codes)
        self.assertIn("incompatible_criteria", codes)

    def test_incompatible_or_unsupported_model_is_blocked(self):
        result = prepare_coc(
            source(
                1,
                [MeasurementRecord(1, 1.0, 1.1, 1)],
                criteria={**CRITERIA, "model": "OSX-100"},
            ),
            1,
        )

        self.assertFalse(result.eligible)
        self.assertTrue(
            any(item.code == "unsupported_coc_model" for item in result.validation_issues)
        )

    def test_optimization_recommendation_excludes_active_ports(self):
        result = prepare_coc(
            source(
                1,
                [
                    MeasurementRecord(1, 2.3, 2.2, 1),
                    MeasurementRecord(2, 1.0, 1.0, 2),
                    MeasurementRecord(3, 0.8, 0.9, 3),
                ],
            ),
            2,
        )
        self.assertTrue(result.eligible)
        self.assertEqual(result.optimization_channels, (1,))
        self.assertEqual(len(result.optimization_recommendations), 1)
        self.assertEqual(
            result.optimization_recommendations[0]["candidate_physical_port"],
            3,
        )

    def test_optimization_band_without_viable_candidate_has_no_recommendation(self):
        result = prepare_coc(
            source(1, [MeasurementRecord(1, 2.3, 2.2, 1)]),
            1,
        )

        self.assertTrue(result.eligible)
        self.assertEqual(result.optimization_channels, (1,))
        self.assertEqual(result.optimization_recommendations, ())

    def test_channels_above_front_panel_count_are_excluded(self):
        result = prepare_coc(
            source(
                1,
                [
                    MeasurementRecord(1, 1.0, 1.1, 1),
                    MeasurementRecord(2, 1.1, 1.2, 2),
                    MeasurementRecord(3, 0.5, 0.6, 3),
                ],
            ),
            2,
        )

        self.assertEqual([item.record.channel for item in result.channels], [1, 2])

    def test_source_measurements_are_not_mutated(self):
        records = [MeasurementRecord(1, 1.0, 1.1, 1)]
        base = source(1, records)
        before = base.measurements
        prepare_coc(base, 1)
        self.assertEqual(base.measurements, before)

    def test_part_number_count_is_inferred_only_from_known_shape(self):
        self.assertEqual(
            infer_front_panel_channel_count("OSX-150-1A-036-09-FA-00B-2FD"),
            36,
        )
        self.assertIsNone(infer_front_panel_channel_count("OSX-150-UNKNOWN-36"))


if __name__ == "__main__":
    unittest.main()
