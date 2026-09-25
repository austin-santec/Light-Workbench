import unittest

from replacement_analysis import (
    ReplacementReading,
    analyze_replacements,
    completed_replacement_metadata,
    normalise_completed_replacements,
    parse_extra_readings,
    replacement_metadata,
)
from domain.replacements import ReplacementReading as DomainReplacementReading
from run_data import MeasurementRecord


class ReplacementAnalysisTests(unittest.TestCase):
    def test_legacy_module_reexports_domain_service(self):
        self.assertIs(ReplacementReading, DomainReplacementReading)

    def test_parse_extra_readings(self):
        readings = parse_extra_readings("49, 1.2, 1.1\n50; 0.9; 1.0")
        self.assertEqual([reading.port for reading in readings], [49, 50])
        self.assertAlmostEqual(readings[1].worst_loss, 1.0)

    def test_no_extra_ports_is_not_applicable(self):
        result = analyze_replacements(
            [MeasurementRecord(1, 1.5, 1.6)],
            [],
            designed_channel_count=1,
            warning_limit=2.0,
        )
        self.assertFalse(result["applicable"])
        self.assertEqual(result["bottom_spares"], [])

    def test_replaces_worst_channels_then_chooses_remaining_spares(self):
        production = [
            MeasurementRecord(1, 2.4, 2.1, 1),
            MeasurementRecord(2, 1.995, 1.8, 2),
            MeasurementRecord(3, 1.2, 1.3, 3),
        ]
        extras = [
            ReplacementReading(49, 1.0, 0.9),
            ReplacementReading(50, 1.8, 1.7),
            ReplacementReading(51, 1.1, 1.2),
            ReplacementReading(52, 1.7, 1.7),
        ]
        result = analyze_replacements(
            production,
            extras,
            designed_channel_count=3,
            warning_limit=2.5,
            minimum_improvement=0.05,
            bottom_spare_count=2,
        )

        self.assertEqual(
            [(item["logical_channel"], item["candidate_physical_port"])
             for item in result["recommendations"]],
            [(1, 49), (2, 51)],
        )
        self.assertEqual(
            [item["category"] for item in result["recommendations"]],
            ["optional", "optional"],
        )
        self.assertEqual(
            [item["physical_port"] for item in result["bottom_spares"]],
            [52, 50],
        )
        metadata = replacement_metadata(result)
        self.assertIn("Logical 1 (physical 1", metadata["Replacement recommendation 1"])
        self.assertIn("Physical 49", metadata["Replacement recommendation 1"])
        self.assertTrue(
            metadata["Replacement recommendation 1"].startswith("Optional")
        )
        self.assertEqual(metadata["Optional Replacements"], "2")
        self.assertIn(
            "Physical 52", metadata["Recommended designated spare 1"]
        )

    def test_candidates_must_be_at_or_below_warning_limit(self):
        result = analyze_replacements(
            [MeasurementRecord(1, 2.4, 2.4, 1)],
            [ReplacementReading(2, 2.1, 1.0)],
            designed_channel_count=1,
            warning_limit=2.0,
            minimum_improvement=0.05,
        )
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["bottom_spares"][0]["physical_port"], 2)
        self.assertFalse(result["bottom_spares"][0]["within_warning_limit"])

    def test_replaced_production_port_can_be_designated_spare(self):
        result = analyze_replacements(
            [
                MeasurementRecord(41, 1.5, 1.5, 41),
                MeasurementRecord(42, 1.0, 1.0, 42),
            ],
            [
                ReplacementReading(50, 1.0, 1.0),
                ReplacementReading(51, 3.0, 3.0),
            ],
            designed_channel_count=48,
            warning_limit=2.0,
            minimum_improvement=0.05,
            bottom_spare_count=2,
        )

        self.assertEqual(
            [(item["logical_channel"], item["candidate_physical_port"])
             for item in result["recommendations"]],
            [(41, 50)],
        )
        self.assertEqual(
            [item["physical_port"] for item in result["bottom_spares"]],
            [41, 51],
        )
        self.assertTrue(result["bottom_spares"][0]["within_warning_limit"])
        self.assertFalse(result["bottom_spares"][1]["within_warning_limit"])

    def test_over_limit_channels_are_required_and_within_limit_swaps_optional(self):
        result = analyze_replacements(
            [
                MeasurementRecord(1, 2.2, 1.8, 1),
                MeasurementRecord(2, 1.9, 1.9, 2),
            ],
            [
                ReplacementReading(49, 1.0, 1.0),
                ReplacementReading(50, 1.5, 1.5),
            ],
            designed_channel_count=2,
            warning_limit=2.0,
            minimum_improvement=0.05,
            bottom_spare_count=0,
        )

        self.assertEqual(
            [(item["logical_channel"], item["category"])
             for item in result["recommendations"]],
            [(1, "required"), (2, "optional")],
        )
        metadata = replacement_metadata(result)
        self.assertEqual(metadata["Required replacements"], "1")
        self.assertEqual(metadata["Optional Replacements"], "1")
        self.assertIn("Required replacement recommendation 1", metadata)
        self.assertIn("Optional replacement recommendation 1", metadata)

    def test_completed_replacements_are_normalized_and_exported_as_metadata(self):
        records = normalise_completed_replacements(
            [
                {
                    "current_port": "10",
                    "replacement_port": "49",
                }
            ]
        )
        self.assertEqual(records[0]["replacement_port"], 49)
        metadata = completed_replacement_metadata(records)
        self.assertEqual(metadata["Completed replacements"], "1")
        self.assertEqual(
            metadata["Completed replacement 1"],
            "Current Port 10 -> Replacement Port 49",
        )

    def test_legacy_completed_replacements_load_as_two_port_records(self):
        records = normalise_completed_replacements(
            [
                {
                    "logical_channel": 10,
                    "original_physical_port": 10,
                    "replacement_physical_port": 49,
                }
            ]
        )
        self.assertEqual(records, [{"current_port": 10, "replacement_port": 49}])

    def test_completed_replacements_reject_duplicate_replacement_ports(self):
        with self.assertRaises(ValueError):
            normalise_completed_replacements(
                [
                    {
                        "current_port": 10,
                        "replacement_port": 49,
                    },
                    {
                        "current_port": 11,
                        "replacement_port": 49,
                    },
                ]
            )


if __name__ == "__main__":
    unittest.main()
