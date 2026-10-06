import tempfile
import unittest
from pathlib import Path

from application.coc_workflow import CocWorkflow
from domain.models import MeasurementRecord
from infrastructure.run_repository import FileRunRepository
from infrastructure.unit_repository import FileUnitRepository


class CocWorkflowTests(unittest.TestCase):
    CRITERIA = {
        "model": "OSX-150",
        "warning_enabled": True,
        "warning_above_db": 2.25,
        "fail_above_db": 2.5,
    }

    def test_load_source_hydrates_physical_port_and_criteria(self):
        with tempfile.TemporaryDirectory() as directory:
            run_directory = Path(directory) / "Run-1-SW1"
            repository = FileRunRepository()
            recorder = repository.new_recorder(
                directory=run_directory,
                metadata={
                    "Run number": "1",
                    "Main board serial": "MB1",
                    "Part number": "OSX-150-1A-001-09-FA-00B-1H",
                    "Switch serial": "SW1",
                    "Operating band": "O band",
                },
                criteria_snapshot={
                    "model": "OSX-150",
                    "profile_name": "standard",
                    "revision": "1",
                    "too_good_below_db": 0.5,
                    "warning_enabled": True,
                    "warning_above_db": 2.25,
                    "fail_above_db": 2.5,
                },
            )
            recorder.save([MeasurementRecord(1, 1.0, 1.1, 43)])

            workflow = CocWorkflow(repository, FileUnitRepository())
            loaded = workflow.load_source(recorder.csv_path)

            self.assertEqual(loaded.run_number, 1)
            self.assertEqual(loaded.measurements[0].physical_port, 43)
            self.assertEqual(loaded.criteria["model"], "OSX-150")

    def test_available_runs_uses_unit_index_and_technician_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            unit_directory = Path(directory) / "Unit-MB1"
            run_repository = FileRunRepository()
            unit_repository = FileUnitRepository()
            for run_number, count in ((1, 3), (2, 1)):
                run_directory = unit_directory / ("Run-%d-SW1" % run_number)
                metadata = {
                    "Run number": str(run_number),
                    "Main board serial": "MB1",
                    "Part number": "OSX-150-1A-003-09-FA-00B-1H",
                    "Switch serial": "SW1",
                    "Operating band": "O band",
                }
                recorder = run_repository.new_recorder(
                    directory=run_directory,
                    metadata=metadata,
                    criteria_snapshot=self.CRITERIA,
                )
                recorder.save(
                    [
                        MeasurementRecord(channel, 1.0, 1.1, channel)
                        for channel in range(1, count + 1)
                    ]
                )
                unit_repository.save_record(
                    unit_directory,
                    metadata,
                    [],
                    [],
                    run_number,
                    run_directory,
                    "SW1",
                )

            options = CocWorkflow(
                run_repository,
                unit_repository,
            ).available_runs(unit_directory)

            self.assertEqual(
                [option.label for option in options],
                ["Run 1 — 3 written readings", "Run 2 — 1 written reading"],
            )


if __name__ == "__main__":
    unittest.main()
