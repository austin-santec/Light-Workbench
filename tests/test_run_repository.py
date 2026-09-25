import tempfile
import unittest
from pathlib import Path

from infrastructure.run_repository import FileRunRepository
from run_data import MeasurementRecord
from run_persistence import RunRecorder


class FileRunRepositoryTests(unittest.TestCase):
    def test_repository_loads_csv_through_application_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.csv"
            path.write_text(
                "channel,1310 IL,1550 IL\n1,1.2,1.3\n",
                encoding="utf-8",
            )

            run_data = FileRunRepository().load_csv(path)

        self.assertEqual([record.channel for record in run_data.measurements], [1])

    def test_repository_creates_compatible_recorder(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = FileRunRepository()
            recorder = repository.new_recorder(
                root=directory,
                metadata={"Mode": "Test"},
            )
            recorder.save([MeasurementRecord(1, 1.0, 1.1, 1)])

            self.assertIsInstance(recorder, RunRecorder)
            self.assertTrue(recorder.csv_path.is_file())
            self.assertTrue(recorder.json_path.is_file())


if __name__ == "__main__":
    unittest.main()
