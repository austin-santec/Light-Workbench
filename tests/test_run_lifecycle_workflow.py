import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from application.run_lifecycle_workflow import (
    DatabaseRunUnavailableError,
    RunLifecycleWorkflow,
)
from domain.database_records import (
    AssignmentSpec,
    MeasurementSpec,
    SwitchSpec,
    UnitSpec,
)
from domain.database_run_lifecycle import (
    StaleRunDecision,
    is_normal_production_analysis_eligible,
)
from infrastructure.database.memory_repositories import InMemoryRepositories


NOW = datetime(2026, 10, 14, 16, 0, tzinfo=timezone.utc)


class RunLifecycleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepositories()
        unit = self.repository.get_or_create(
            UnitSpec(
                "unit-150",
                "OSX-150-1A-048-09-FA-00B-3H",
                48,
                "OSX-150",
            )
        )
        switch = self.repository.get_or_create(
            SwitchSpec("switch-150", "OSX-150", 51, "03.01.23")
        )
        self.assignment = self.repository.install(
            AssignmentSpec(unit.unit_id, switch.switch_id, NOW, "AT", {1: 1})
        )
        self.workflow = RunLifecycleWorkflow(
            self.repository,
            lambda: SimpleNamespace(ready=True, operator_message="ready"),
        )

    def start(self, **changes):
        values = {
            "assignment_id": self.assignment.assignment_id,
            "tested_by": "AT",
            "wavelength_mode": "SM",
            "operating_band": "O band",
            "application_version": "test",
            "measurement_hardware": {
                "ilm": {"model": "OP815", "serial": "0016582"}
            },
            "limit_snapshot": {
                "too_good_db": 0.5,
                "warning_db": 2.25,
                "failure_db": 2.5,
            },
            "part_number_snapshot": "OSX-150-1A-048-09-FA-00B-3H",
            "front_panel_channel_count": 48,
            "started_at_utc": NOW,
        }
        values.update(changes)
        return self.workflow.start_run(**values)

    def test_start_requires_successful_database_preflight(self):
        workflow = RunLifecycleWorkflow(
            self.repository,
            lambda: SimpleNamespace(ready=False, operator_message="schema outdated"),
        )
        with self.assertRaisesRegex(DatabaseRunUnavailableError, "schema outdated"):
            workflow.start_run(
                assignment_id=self.assignment.assignment_id,
                tested_by="AT",
                wavelength_mode="SM",
                operating_band="O band",
                application_version="test",
                measurement_hardware={},
                limit_snapshot={},
                part_number_snapshot=None,
                front_panel_channel_count=None,
                started_at_utc=NOW,
            )
        self.assertEqual(self.repository.runs, {})

    def test_uuid_retry_is_idempotent_and_run_numbers_are_allocated(self):
        retry_uuid = uuid4()
        first = self.start(client_run_uuid=retry_uuid)
        retry = self.start(client_run_uuid=retry_uuid, tested_by="ignored")
        second = self.start(client_run_uuid=uuid4())

        self.assertEqual(retry.run_id, first.run_id)
        self.assertEqual((first.run_number, second.run_number), (1, 2))
        self.assertEqual(len(self.repository.runs), 2)
        self.assertEqual(first.completion_status, "in_progress")
        self.assertEqual(first.front_panel_channel_count, 48)
        self.assertEqual(first.measurement_hardware["ilm"]["model"], "OP815")

    def test_completion_is_independent_from_measurement_quality(self):
        run = self.start()
        measurement = self.repository.append_attempt(
            MeasurementSpec(
                uuid4(),
                run.run_id,
                1,
                1,
                1310,
                Decimal("3.0000"),
                1550,
                Decimal("3.1000"),
                {"snapshot_id": "ref-1"},
                NOW + timedelta(seconds=1),
                "AT",
                1,
            )
        )
        complete = self.workflow.finish_run(
            run.run_id, "complete", NOW + timedelta(minutes=1)
        )

        self.assertEqual(complete.completion_status, "complete")
        self.assertEqual(
            self.repository.history_for_run(run.run_id),
            (measurement,),
        )
        self.assertEqual(complete.limit_snapshot["failure_db"], 2.5)

    def test_stopped_run_retains_accepted_measurements(self):
        run = self.start()
        accepted = self.repository.append_attempt(
            MeasurementSpec(
                uuid4(), run.run_id, 1, 1, 1310, Decimal("0.6500"),
                1550, Decimal("0.5000"), {"snapshot_id": "ref-1"},
                NOW + timedelta(seconds=1), "AT", 1,
            )
        )
        stopped = self.workflow.finish_run(
            run.run_id, "stopped", NOW + timedelta(minutes=1)
        )
        self.assertEqual(stopped.completion_status, "stopped")
        self.assertEqual(self.repository.history_for_run(run.run_id), (accepted,))

    def test_failed_run_records_a_terminal_technical_state(self):
        run = self.start()
        failed = self.workflow.finish_run(
            run.run_id, "failed", NOW + timedelta(minutes=1)
        )
        self.assertEqual(failed.completion_status, "failed")
        self.assertEqual(failed.run_ended_at_utc, NOW + timedelta(minutes=1))

    def test_nonproduction_runs_are_excluded_from_production_analysis(self):
        for purpose in ("engineering", "training", "calibration"):
            run = self.start(run_purpose=purpose, client_run_uuid=uuid4())
            self.assertEqual(run.analysis_status, "excluded")
            self.assertEqual(run.analysis_exclusion_reason, f"Run purpose: {purpose}")
            self.assertFalse(is_normal_production_analysis_eligible(run))
            with self.assertRaisesRegex(ValueError, "Only production"):
                self.workflow.set_analysis_status(run.run_id, "included")

    def test_completed_included_production_run_is_analysis_eligible(self):
        run = self.start()
        run = self.workflow.finish_run(
            run.run_id, "complete", NOW + timedelta(minutes=1)
        )
        run = self.workflow.set_analysis_status(run.run_id, "included")
        self.assertTrue(is_normal_production_analysis_eligible(run))

    def test_stale_run_requires_an_explicit_resume_or_close_decision(self):
        run = self.start(started_at_utc=NOW - timedelta(hours=2))
        stale = self.workflow.find_stale_runs(NOW - timedelta(hours=1))
        self.assertEqual(stale, (run,))
        self.assertEqual(self.repository.get(run.run_id).completion_status, "in_progress")

        resumed = self.workflow.resolve_stale_run(run.run_id, StaleRunDecision.RESUME)
        self.assertEqual(resumed.completion_status, "in_progress")
        closed = self.workflow.resolve_stale_run(
            run.run_id,
            StaleRunDecision.CLOSE_STOPPED,
            NOW,
        )
        self.assertEqual(closed.completion_status, "stopped")

    def test_exclusion_requires_a_reason_and_superseding_run_must_differ(self):
        first = self.start()
        second = self.start(client_run_uuid=uuid4())
        with self.assertRaisesRegex(ValueError, "exclusion reason"):
            self.workflow.set_analysis_status(first.run_id, "excluded")
        superseded = self.workflow.set_analysis_status(
            first.run_id,
            "superseded",
            superseded_by_run_id=second.run_id,
        )
        self.assertEqual(superseded.superseded_by_run_id, second.run_id)

    def test_new_run_cannot_start_as_already_superseded(self):
        with self.assertRaisesRegex(ValueError, "cannot begin in superseded"):
            self.start(analysis_status="superseded")


if __name__ == "__main__":
    unittest.main()
