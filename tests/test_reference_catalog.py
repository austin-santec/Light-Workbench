import csv
import tempfile
import unittest
from pathlib import Path

from domain.measurement_attempts import new_measurement_attempt
from domain.models import MeasurementRecord
from domain.reference import ReferenceMethod, new_reference_snapshot
from domain.reference_catalog import ReferenceCatalog
from infrastructure.csv_run_loader import load_run_csv
from infrastructure.run_persistence import RunRecorder, load_run_json


class ReferenceCatalogTests(unittest.TestCase):
    def test_deduplicates_snapshots_and_preserves_first_use_labels(self):
        first = new_reference_snapshot(-0.04, 0.14, method=ReferenceMethod.CALCULATED)
        second = new_reference_snapshot(-0.06, 0.12, method=ReferenceMethod.CALCULATED)
        catalog = ReferenceCatalog()

        self.assertEqual(catalog.label_for(first.as_dict()), "Ref 1")
        self.assertEqual(catalog.label_for(first.as_dict()), "Ref 1")
        self.assertEqual(catalog.label_for(second.as_dict()), "Ref 2")
        self.assertEqual([entry.reference_key for entry in catalog.entries()], ["Ref 1", "Ref 2"])

    def test_conflicting_snapshot_data_is_rejected(self):
        first = new_reference_snapshot(-0.04, 0.14, method=ReferenceMethod.CALCULATED)
        changed = first.as_dict()
        changed["references_by_wavelength"]["1310"] = -0.05
        catalog = ReferenceCatalog()
        catalog.register(first.as_dict())

        with self.assertRaisesRegex(ValueError, "conflicting data"):
            catalog.register(changed)

    def test_csv_links_current_rows_and_retains_historical_reference_catalog(self):
        first = new_reference_snapshot(-0.04, 0.14, method=ReferenceMethod.CALCULATED)
        second = new_reference_snapshot(-0.06, 0.12, method=ReferenceMethod.CALCULATED)
        first_record = MeasurementRecord(1, 0.9, 0.64, 1, first.as_dict())
        second_record = MeasurementRecord(1, 0.8, 0.60, 1, second.as_dict())
        first_attempt = new_measurement_attempt(first_record, run_id="run")
        second_attempt = new_measurement_attempt(
            second_record,
            prior=first_attempt,
            run_id="run",
        )

        with tempfile.TemporaryDirectory() as directory:
            recorder = RunRecorder(root=directory, run_id="run")
            recorder.save(
                [second_record],
                measurement_attempts=[first_attempt, second_attempt],
            )
            payload = load_run_json(recorder.json_path)
            self.assertEqual(
                [item["reference_key"] for item in payload["reference_catalog"]],
                ["Ref 1", "Ref 2"],
            )

            with Path(recorder.csv_path).open(newline="", encoding="utf-8") as stream:
                rows = list(csv.reader(stream))
            header = rows[0]
            measurement_row = rows[1]
            self.assertEqual(measurement_row[header.index("Reference used")], "Ref 2")
            self.assertEqual(
                [row[header.index("Reference")] for row in rows[1:] if row[header.index("Reference")]],
                ["Ref 1", "Ref 2"],
            )

            loaded = load_run_csv(recorder.csv_path)
            self.assertEqual(
                loaded.measurements[0].reference_snapshot["snapshot_id"],
                second.snapshot_id,
            )


if __name__ == "__main__":
    unittest.main()
