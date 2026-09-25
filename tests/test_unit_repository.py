import tempfile
import unittest
from pathlib import Path

from infrastructure.unit_repository import FileUnitRepository


class FileUnitRepositoryTests(unittest.TestCase):
    def test_repository_resolves_and_persists_unit_records(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = FileUnitRepository()
            unit_directory = repository.unit_directory_for_metadata(
                directory,
                {"Main board serial": "17688"},
            )
            run_directory = repository.run_directory_for_number(
                unit_directory,
                1,
                "SW123",
            )
            repository.save_record(
                unit_directory,
                {"Main board serial": "17688", "Part number": "OSX-150"},
                [],
                [49, 50],
                1,
                run_directory,
                switch_serial="SW123",
            )

            record = repository.load_record(unit_directory)

        self.assertEqual(record["unit_metadata"]["Main board serial"], "17688")
        self.assertEqual(record["designated_spares"], [49, 50])
        self.assertEqual(record["runs"][0]["switch_serial"], "SW123")

    def test_repository_infers_numbered_run_unit_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = FileUnitRepository()
            unit_directory = Path(directory) / "Unit-17688"
            run_directory = repository.run_directory_for_number(unit_directory, 2)
            csv_path = run_directory / "Run-2.csv"

            self.assertIsNone(repository.infer_unit_directory(csv_path))
            unit_directory.mkdir(parents=True)
            (unit_directory / "unit.json").write_text("{}", encoding="utf-8")

            self.assertEqual(repository.infer_unit_directory(csv_path), unit_directory)


if __name__ == "__main__":
    unittest.main()
