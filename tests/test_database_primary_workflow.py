import unittest
from dataclasses import dataclass
from unittest.mock import MagicMock

from application.database_primary_workflow import DatabasePrimaryRunWorkflow
from application.run_lifecycle_workflow import DatabaseRunUnavailableError
from domain.database_records import SwitchSpec, UnitSpec
from domain.unit_switch_assignments import (
    AssignmentChangeRequiredError,
    NewHardwarePairingConfirmationRequired,
)
from infrastructure.database.memory_repositories import InMemoryRepositories


@dataclass(frozen=True)
class _Readiness:
    ready: bool
    operator_message: str = "Database unavailable"


class DatabasePrimaryRunWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.repositories = InMemoryRepositories()
        self.support_events = []

        class _SupportLogger:
            def __init__(self, events):
                self.events = events

            def record(self, category, event, **fields):
                self.events.append((category, event, fields))
                return True

        self.support_logger = _SupportLogger(self.support_events)
        self.workflow = DatabasePrimaryRunWorkflow(
            self.repositories,
            readiness_check=lambda: _Readiness(True),
            support_logger=self.support_logger,
        )

    def _start(self):
        return self.workflow.start_new_run(
            unit_spec=UnitSpec("MB-100", "OSX-150-1A-002-09-FA-00B-3H", 2, "OSX-150"),
            switch_spec=SwitchSpec("SW-100", "OSX-150", 4, "03.01.23"),
            installed_by="AT",
            initial_channel_map={1: 1, 2: 2},
            tested_by="AT",
            station_number=4,
            wavelength_mode="SM",
            operating_band="O band",
            application_version="test",
            measurement_hardware={
                "planned_channels": [1, 2],
                "opm_wavelengths_nm": [1310, 1550],
                "source_wavelengths_nm": [1310, 1550],
                "source_ids": [0, 1],
            },
            limit_snapshot={"model": "OSX-150", "fail_above_db": 2.5},
            part_number_snapshot="OSX-150-1A-002-09-FA-00B-3H",
            front_panel_channel_count=2,
        )

    def test_start_commit_load_and_finish_use_authoritative_repositories(self):
        context = self._start()
        self.assertEqual(context.run.run_number, 1)
        self.assertEqual(context.run.station_number, 4)
        self.assertEqual(context.unit.main_board_serial, "MB-100")

        pending = self.workflow.measurements.prepare_measurement(
            run_id=context.run.run_id,
            logical_channel=1,
            physical_port=1,
            wavelength_1_nm=1310,
            wavelength_1_il_db=0.65,
            wavelength_2_nm=1550,
            wavelength_2_il_db=0.50,
            reference_snapshot={"snapshot_id": "ref-1"},
            written_by="AT",
        )
        record, refreshed = self.workflow.commit_measurement(pending)
        self.assertEqual(record.attempt_number, 1)
        self.assertEqual(len(refreshed.snapshot.measurements), 1)

        self.support_events.clear()
        loaded = self.workflow.load_for_unit("MB-100", 1)
        self.assertEqual(loaded.run.run_id, context.run.run_id)
        self.assertEqual(len(loaded.snapshot.measurement_attempts), 1)
        self.assertEqual(
            tuple((item.run_id, item.run_number) for item in loaded.unit_run_index),
            ((context.run.run_id, 1),),
        )
        self.assertEqual(len(loaded.assignment_run_snapshots), 1)
        self.assertEqual(loaded.assignment_run_snapshots[0], loaded.snapshot)

        self.assertTrue(loaded.load_operation_id.startswith("db-load-"))
        self.assertIsNotNone(loaded.load_summary)
        completed = [
            item
            for item in self.support_events
            if item[1] == "database.run_load_completed"
        ]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0][2]["status"], "success")
        self.assertEqual(completed[0][2]["load_source"], "unit_run_number")
        self.assertIn("database_connection_count", completed[0][2])
        self.assertIn("stage_timings_ms", completed[0][2])

        loaded_by_id = self.workflow.load_run(context.run.run_id)
        refreshed_by_id = self.workflow.refresh(context.run.run_id)
        comparison = self.workflow.load_run(
            context.run.run_id, load_source="comparison"
        )
        for equivalent in (loaded_by_id, refreshed_by_id, comparison):
            self.assertEqual(equivalent.run, loaded.run)
            self.assertEqual(equivalent.snapshot, loaded.snapshot)
            self.assertEqual(equivalent.routing, loaded.routing)
            self.assertEqual(
                equivalent.effective_projection, loaded.effective_projection
            )
        self.assertEqual(loaded_by_id.load_summary.source, "run_id")
        self.assertEqual(refreshed_by_id.load_summary.source, "refresh")
        self.assertEqual(comparison.load_summary.source, "comparison")

        completed = self.workflow.finish_run(context.run.run_id, "complete")
        self.assertEqual(completed.run.completion_status, "complete")
        with self.assertRaisesRegex(ValueError, "in-progress"):
            self.workflow.commit_measurement(
                self.workflow.measurements.prepare_measurement(
                    run_id=context.run.run_id,
                    logical_channel=2,
                    physical_port=2,
                    wavelength_1_nm=1310,
                    wavelength_1_il_db=0.60,
                    wavelength_2_nm=1550,
                    wavelength_2_il_db=0.45,
                    reference_snapshot={"snapshot_id": "ref-1"},
                    written_by="AT",
                )
            )

        resumed = self.workflow.resume_run(context.run.run_id)
        self.assertEqual(resumed.run.completion_status, "in_progress")
        self.assertIsNone(resumed.run.run_ended_at_utc)
        retest, refreshed = self.workflow.commit_measurement(
            self.workflow.measurements.prepare_measurement(
                run_id=context.run.run_id,
                logical_channel=1,
                physical_port=1,
                wavelength_1_nm=1310,
                wavelength_1_il_db=0.60,
                wavelength_2_nm=1550,
                wavelength_2_il_db=0.45,
                reference_snapshot={"snapshot_id": "ref-2"},
                written_by="AT",
            )
        )
        self.assertEqual(retest.attempt_number, 2)
        self.assertEqual(len(refreshed.snapshot.measurement_attempts), 2)

    def test_load_reuses_bulk_history_for_current_and_related_snapshots(self):
        context = self._start()
        pending = self.workflow.measurements.prepare_measurement(
            run_id=context.run.run_id,
            logical_channel=1,
            physical_port=1,
            wavelength_1_nm=1310,
            wavelength_1_il_db=0.65,
            wavelength_2_nm=1550,
            wavelength_2_il_db=0.50,
            reference_snapshot={"snapshot_id": "ref-1"},
            written_by="AT",
        )
        self.workflow.measurements.commit(pending)
        expected = self.workflow.queries.load(context.run.run_id)
        original_snapshot = self.repositories.snapshot_for_run
        self.repositories.snapshot_for_run = MagicMock(
            side_effect=AssertionError("per-run snapshot query must not be used")
        )
        try:
            loaded = self.workflow.load_for_unit("MB-100", 1)
        finally:
            self.repositories.snapshot_for_run = original_snapshot

        self.assertEqual(loaded.snapshot, expected)
        self.assertEqual(loaded.assignment_run_snapshots, (expected,))
        self.assertEqual(
            loaded.snapshot.coc_source(),
            expected.coc_source(),
        )
        self.assertEqual(
            loaded.load_summary.counts["projection_measurement_query_count"],
            1,
        )

    def test_failed_readiness_blocks_start_and_load(self):
        workflow = DatabasePrimaryRunWorkflow(
            self.repositories,
            readiness_check=lambda: _Readiness(False, "SQL Server is offline"),
            support_logger=self.support_logger,
        )
        with self.assertRaisesRegex(DatabaseRunUnavailableError, "offline"):
            workflow.load_for_unit("MB-100", 1)
        failures = [
            item
            for item in self.support_events
            if item[1] == "database.run_load_failed"
        ]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][2]["failure_stage"], "database_readiness")

    def test_unit_run_numbers_continue_across_switch_assignments(self):
        first = self._start()
        self.workflow.finish_run(first.run.run_id, "complete")
        second = self.workflow.start_new_run(
            unit_spec=UnitSpec("MB-100", "OSX-150-1A-002-09-FA-00B-3H", 2, "OSX-150"),
            switch_spec=SwitchSpec("SW-100", "OSX-150", 4),
            installed_by="AT",
            initial_channel_map={1: 1, 2: 2},
            tested_by="AT",
            wavelength_mode="SM",
            operating_band="O band",
            application_version="test",
            measurement_hardware={"planned_channels": [1, 2]},
            limit_snapshot={"model": "OSX-150", "fail_above_db": 2.5},
            part_number_snapshot="OSX-150-1A-002-09-FA-00B-3H",
            front_panel_channel_count=2,
        )
        self.assertEqual(second.run.run_number, 2)

    def test_switch_change_requires_and_records_explicit_reason(self):
        first = self._start()
        self.workflow.finish_run(first.run.run_id, "complete")
        arguments = dict(
            unit_spec=UnitSpec("MB-100", "OSX-150-1A-002-09-FA-00B-3H", 2, "OSX-150"),
            switch_spec=SwitchSpec("SW-200", "OSX-150", 4),
            installed_by="AT",
            initial_channel_map={1: 1, 2: 2},
            tested_by="AT",
            wavelength_mode="SM",
            operating_band="O band",
            application_version="test",
            measurement_hardware={"planned_channels": [1, 2]},
            limit_snapshot={"model": "OSX-150", "fail_above_db": 2.5},
            part_number_snapshot="OSX-150-1A-002-09-FA-00B-3H",
            front_panel_channel_count=2,
        )
        with self.assertRaisesRegex(
            AssignmentChangeRequiredError, "different active switch"
        ):
            self.workflow.start_new_run(**arguments)

        second = self.workflow.start_new_run(
            **arguments,
            switch_replacement_reason="Previous switch failed",
        )
        history = self.repositories.history_for_unit(first.unit.unit_id)
        self.assertEqual(second.run.run_number, 2)
        self.assertEqual(history[0].removal_reason, "Previous switch failed")
        self.assertIsNone(history[1].removed_at_utc)

    def test_new_pairing_requires_one_confirmation_and_stops_old_run(self):
        first = self._start()
        arguments = dict(
            unit_spec=UnitSpec("MB-100", "OSX-150-1A-002-09-FA-00B-3H", 2, "OSX-150"),
            switch_spec=SwitchSpec("SW-200", "OSX-150", 4),
            installed_by="AT",
            initial_channel_map={1: 1, 2: 2},
            tested_by="AT",
            wavelength_mode="SM",
            operating_band="O band",
            application_version="test",
            measurement_hardware={"planned_channels": [1, 2]},
            limit_snapshot={"model": "OSX-150", "fail_above_db": 2.5},
            part_number_snapshot="OSX-150-1A-002-09-FA-00B-3H",
            front_panel_channel_count=2,
        )
        with self.assertRaises(NewHardwarePairingConfirmationRequired) as context:
            self.workflow.start_new_run(**arguments)
        self.assertEqual(context.exception.destination_main_board_serial, "MB-100")
        self.assertIsNone(self.repositories.get_active_for_switch(2))
        self.assertEqual(self.repositories.get(first.run.run_id).completion_status, "in_progress")

        second = self.workflow.start_new_run(
            **arguments,
            allow_new_hardware_pairing=True,
        )
        self.assertEqual(second.run.run_number, 2)
        self.assertNotEqual(second.assignment.assignment_id, first.assignment.assignment_id)
        self.assertEqual(
            dict(second.assignment.initial_channel_map), {1: 1, 2: 2}
        )
        self.assertEqual(
            self.repositories.get(first.run.run_id).completion_status, "stopped"
        )
        self.assertIsNotNone(
            self.repositories.get(first.run.run_id).run_ended_at_utc
        )
        self.assertEqual(
            self.repositories.get_active(first.unit.unit_id).assignment_id,
            second.assignment.assignment_id,
        )

    def test_switch_move_closes_source_and_destination_assignments_together(self):
        source = self._start()
        destination = self.workflow.start_new_run(
            unit_spec=UnitSpec(
                "MB-200", "OSX-150-1A-002-09-FA-00B-3H", 2, "OSX-150"
            ),
            switch_spec=SwitchSpec("SW-200", "OSX-150", 4),
            installed_by="AT",
            initial_channel_map={1: 1, 2: 2},
            tested_by="AT",
            wavelength_mode="SM",
            operating_band="O band",
            application_version="test",
            measurement_hardware={"planned_channels": [1, 2]},
            limit_snapshot={"model": "OSX-150", "fail_above_db": 2.5},
            part_number_snapshot="OSX-150-1A-002-09-FA-00B-3H",
            front_panel_channel_count=2,
        )
        arguments = dict(
            unit_spec=UnitSpec(
                "MB-200", "OSX-150-1A-002-09-FA-00B-3H", 2, "OSX-150"
            ),
            switch_spec=SwitchSpec("SW-100", "OSX-150", 4),
            installed_by="AT",
            initial_channel_map={1: 1, 2: 2},
            tested_by="AT",
            wavelength_mode="SM",
            operating_band="O band",
            application_version="test",
            measurement_hardware={"planned_channels": [1, 2]},
            limit_snapshot={"model": "OSX-150", "fail_above_db": 2.5},
            part_number_snapshot="OSX-150-1A-002-09-FA-00B-3H",
            front_panel_channel_count=2,
        )
        with self.assertRaises(NewHardwarePairingConfirmationRequired):
            self.workflow.start_new_run(**arguments)
        result = self.workflow.start_new_run(
            **arguments,
            allow_new_hardware_pairing=True,
        )
        self.assertEqual(len(result.assignment.initial_channel_map), 2)
        self.assertEqual(
            self.repositories.get(source.run.run_id).completion_status, "stopped"
        )
        self.assertEqual(
            self.repositories.get(destination.run.run_id).completion_status,
            "stopped",
        )
        history = self.repositories.history_for_unit(destination.unit.unit_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(result.run.run_number, 2)


if __name__ == "__main__":
    unittest.main()
