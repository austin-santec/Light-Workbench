import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from application.measurement_persistence_workflow import MeasurementPersistenceWorkflow
from domain.database_records import (
    AssignmentSpec,
    RunSpec,
    SwitchSpec,
    UnitSpec,
)
from infrastructure.database.memory_repositories import InMemoryRepositories


NOW = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)
REFERENCE = {
    "snapshot_id": "ref-1",
    "method": "calculated",
    "values_dbm": {"1310": -0.04, "1550": 0.14},
}


class _FailOnceRepository:
    def __init__(self, delegate):
        self.delegate = delegate
        self.calls = 0

    def append_next(self, pending):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("database unavailable")
        return self.delegate.append_next(pending)


class MeasurementPersistenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepositories()
        unit = self.repository.get_or_create(UnitSpec("unit", front_panel_channel_count=48))
        switch = self.repository.get_or_create(SwitchSpec("switch", "OSX-150", 51))
        assignment = self.repository.install(
            AssignmentSpec(unit.unit_id, switch.switch_id, NOW, "AT", {1: 1})
        )
        self.sm_run = self.repository.create(
            RunSpec(
                assignment.assignment_id,
                1,
                uuid4(),
                NOW,
                "AT",
                "SM",
                "O band",
                "test",
            )
        )
        self.mm_run = self.repository.create(
            RunSpec(
                assignment.assignment_id,
                2,
                uuid4(),
                NOW,
                "AT",
                "MM",
                "O band",
                "test",
            )
        )
        self.workflow = MeasurementPersistenceWorkflow(self.repository)

    def prepare_sm(self, **changes):
        values = {
            "run_id": self.sm_run.run_id,
            "logical_channel": 1,
            "physical_port": 1,
            "wavelength_1_nm": 1310,
            "wavelength_1_il_db": Decimal("0.65444"),
            "wavelength_2_nm": 1550,
            "wavelength_2_il_db": Decimal("0.50005"),
            "reference_snapshot": REFERENCE,
            "written_by": "AT",
            "written_at_utc": NOW,
        }
        values.update(changes)
        return self.workflow.prepare_measurement(**values)

    def test_sm_measurement_commits_both_values_at_four_decimal_precision(self):
        record = self.workflow.commit(self.prepare_sm())
        self.assertEqual(record.wavelength_1_nm, 1310)
        self.assertEqual(record.wavelength_1_il_db, Decimal("0.6544"))
        self.assertEqual(record.wavelength_2_nm, 1550)
        self.assertEqual(record.wavelength_2_il_db, Decimal("0.5001"))
        self.assertEqual(record.attempt_number, 1)

    def test_mm_measurement_round_trips_as_one_complete_row(self):
        pending = self.workflow.prepare_measurement(
            run_id=self.mm_run.run_id,
            logical_channel=1,
            physical_port=1,
            wavelength_1_nm=850,
            wavelength_1_il_db="0.30004",
            wavelength_2_nm=1300,
            wavelength_2_il_db="0.40006",
            reference_snapshot={
                "snapshot_id": "ref-mm",
                "values_dbm": {"850": -0.1, "1300": 0.2},
            },
            written_by="AT",
            written_at_utc=NOW,
        )
        record = self.workflow.commit(pending)
        self.assertEqual(
            (
                record.wavelength_1_nm,
                record.wavelength_1_il_db,
                record.wavelength_2_nm,
                record.wavelength_2_il_db,
            ),
            (850, Decimal("0.3000"), 1300, Decimal("0.4001")),
        )

    def test_incomplete_invalid_and_negative_samples_never_reach_repository(self):
        invalid_changes = (
            {"wavelength_1_il_db": None},
            {"wavelength_2_il_db": Decimal("NaN")},
            {"wavelength_1_il_db": Decimal("-0.0001")},
            {"reference_snapshot": {}},
            {"wavelength_2_nm": 1310},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.prepare_sm(**changes)
        self.assertEqual(self.repository.measurements, {})

    def test_wrong_wavelength_pair_is_rejected_for_run_mode(self):
        pending = self.prepare_sm(wavelength_1_nm=850, wavelength_2_nm=1300)
        with self.assertRaisesRegex(ValueError, "SM measurements require"):
            self.workflow.commit(pending)
        self.assertEqual(self.repository.measurements, {})

    def test_retrying_same_pending_uuid_is_idempotent(self):
        pending = self.prepare_sm(measurement_uuid=uuid4())
        first = self.workflow.commit(pending)
        retry = self.workflow.commit(pending)
        self.assertEqual(retry.measurement_id, first.measurement_id)
        self.assertEqual(len(self.repository.measurements), 1)

    def test_parallel_writes_receive_distinct_attempt_numbers(self):
        pending = [
            self.prepare_sm(measurement_uuid=uuid4())
            for _ in range(12)
        ]
        with ThreadPoolExecutor(max_workers=6) as executor:
            records = tuple(executor.map(self.workflow.commit, pending))
        self.assertEqual(
            sorted(item.attempt_number for item in records),
            list(range(1, 13)),
        )

    def test_failed_commit_remains_pending_and_notifies_only_after_retry(self):
        failing = _FailOnceRepository(self.repository)
        workflow = MeasurementPersistenceWorkflow(failing)
        pending = self.prepare_sm(measurement_uuid=uuid4())
        accepted = []

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            workflow.commit(pending, accepted.append)
        self.assertEqual(accepted, [])
        self.assertEqual(self.repository.current_for_run(self.sm_run.run_id), ())

        record = workflow.commit(pending, accepted.append)
        self.assertEqual(accepted, [record])
        self.assertEqual(record.attempt_number, 1)

    def test_prepared_but_unwritten_reading_is_not_persisted(self):
        pending = self.prepare_sm()
        self.assertIsNotNone(pending.measurement_uuid)
        self.assertFalse(hasattr(pending, "raw_power_dbm"))
        self.assertEqual(self.repository.history_for_run(self.sm_run.run_id), ())

    def test_extra_candidate_is_atomic_and_exists_only_after_explicit_commit(self):
        pending = self.prepare_sm(logical_channel=49, physical_port=49)
        self.assertEqual(self.repository.history_for_run(self.sm_run.run_id), ())

        record = self.workflow.commit(pending)

        self.assertEqual(record.logical_channel, 49)
        self.assertEqual(record.physical_port, 49)
        self.assertEqual(len(self.repository.history_for_run(self.sm_run.run_id)), 1)

    def test_terminal_run_rejects_new_measurement(self):
        pending = self.prepare_sm()
        self.repository.finish(self.sm_run.run_id, "stopped", NOW)
        with self.assertRaisesRegex(ValueError, "in-progress"):
            self.workflow.commit(pending)
        self.assertEqual(self.repository.history_for_run(self.sm_run.run_id), ())


if __name__ == "__main__":
    unittest.main()
