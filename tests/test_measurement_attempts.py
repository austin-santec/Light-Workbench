import unittest

from domain.measurement_attempts import (
    latest_attempt_for_channel,
    legacy_attempts_for_measurements,
    new_measurement_attempt,
    normalise_attempts,
)
from domain.models import MeasurementRecord


class MeasurementAttemptTests(unittest.TestCase):
    def test_retests_form_an_append_only_chain(self):
        first_record = MeasurementRecord(14, 2.6, 2.4, 14)
        first = new_measurement_attempt(
            first_record,
            operator_initials="AB",
            run_id="run-1",
        )
        second = new_measurement_attempt(
            MeasurementRecord(14, 2.1, 2.0, 41),
            prior=first,
            operator_initials="AB",
            run_id="run-1",
        )

        self.assertEqual(first.attempt_number, 1)
        self.assertEqual(second.attempt_number, 2)
        self.assertEqual(second.replaces_attempt_id, first.attempt_id)
        self.assertEqual(latest_attempt_for_channel([first, second], 14), second)
        self.assertEqual(first.loss_1310_db, 2.6)

    def test_legacy_rows_are_synthesized_once(self):
        measurements = [MeasurementRecord(1, 0.9, 0.8, 1)]
        attempts = normalise_attempts([], measurements, run_id="run-1")
        again = normalise_attempts(attempts, measurements, run_id="run-1")

        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].write_context, "legacy_import")
        self.assertEqual(attempts[0].attempt_number, 1)
        self.assertEqual([item.attempt_id for item in attempts], [item.attempt_id for item in again])

    def test_missing_channel_is_added_without_discarding_loaded_history(self):
        existing = new_measurement_attempt(
            MeasurementRecord(1, 0.9, 0.8, 1), run_id="run-1"
        )
        measurements = [
            MeasurementRecord(1, 0.9, 0.8, 1),
            MeasurementRecord(2, 1.0, 0.9, 2),
        ]

        attempts = normalise_attempts([existing], measurements, run_id="run-1")

        self.assertEqual([item.channel for item in attempts], [1, 2])
        self.assertEqual(attempts[0].attempt_id, existing.attempt_id)

    def test_broken_replacement_links_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing prior"):
            normalise_attempts(
                [
                    {
                        "attempt_id": "attempt-2",
                        "channel": 1,
                        "attempt_number": 2,
                        "loss_1310_db": 1.0,
                        "loss_1550_db": 0.9,
                        "replaces_attempt_id": "attempt-1",
                    }
                ],
                [],
            )


if __name__ == "__main__":
    unittest.main()
