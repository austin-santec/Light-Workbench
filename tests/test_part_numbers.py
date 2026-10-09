import unittest

from domain.part_numbers import (
    infer_front_panel_channel_count,
    parse_osx_part_number,
    resolve_front_panel_channel_count,
)


class PartNumberTests(unittest.TestCase):
    def test_supported_osx_part_numbers_resolve_channel_field(self):
        cases = {
            "OSX-150-1A-012-09-FA-00B-2HD": 12,
            "OSX-150-2A-012-09-FA-00B-2HD": 12,
            "OSX-150-1A-036-09-FA-00B-3H": 36,
            "OSX-150-1A-048-09-FA-00B-3H": 48,
            "osx-100-1A-008-09-FA-00B-2H": 8,
        }
        for part_number, expected in cases.items():
            with self.subTest(part_number=part_number):
                self.assertEqual(
                    resolve_front_panel_channel_count("  %s  " % part_number),
                    expected,
                )

    def test_parser_returns_model_and_normalized_value(self):
        parsed = parse_osx_part_number(" osx-150-1a-012-09-fa-00b-2hd ")

        self.assertEqual(parsed.model, "OSX-150")
        self.assertEqual(parsed.front_panel_channel_count, 12)
        self.assertEqual(parsed.value, "osx-150-1a-012-09-fa-00b-2hd")

    def test_invalid_part_numbers_do_not_produce_a_guessed_count(self):
        invalid = (
            "",
            "OSX-150-UNKNOWN-36",
            "OSX-150-1A-12-09-FA-00B-2H",
            "OSX-150-1A-000-09-FA-00B-2H",
            "OSX-150-1A-049-09-FA-00B-2H",
            "OSX-150-1A-09-012-FA-00B-2H",
        )
        for part_number in invalid:
            with self.subTest(part_number=part_number):
                self.assertIsNone(infer_front_panel_channel_count(part_number))
                with self.assertRaises(ValueError):
                    resolve_front_panel_channel_count(part_number)


if __name__ == "__main__":
    unittest.main()
