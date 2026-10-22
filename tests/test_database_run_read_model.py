import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from application.database_run_read_model import DatabaseRunQueryService
from application.measurement_persistence_workflow import MeasurementPersistenceWorkflow
from domain.coc_preparation import prepare_coc
from domain.database_records import AssignmentSpec, RunSpec, SwitchSpec, UnitSpec
from domain.limit_profiles import LimitProfile
from domain.run_status import COMPLETION_COMPLETE, RESULT_PASS
from infrastructure.database.memory_repositories import InMemoryRepositories


NOW = datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc)
CRITERIA = {
    "model": "OSX-150",
    "wavelength_mode": "SM",
    "profile_name": "OSX-150 SM",
    "revision": "1",
    "too_good_below_db": 0.5,
    "warning_enabled": True,
    "warning_above_db": 2.25,
    "fail_above_db": 2.5,
}
REFERENCE = {
    "snapshot_id": "ref-1",
    "method": "calculated",
    "values_dbm": {"1310": -0.04, "1550": 0.14},
}


class DatabaseRunReadModelTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepositories()
        unit = self.repository.get_or_create(
            UnitSpec(
                "unit-read-model",
                "OSX-150-1A-002-09-FA-00B-3H",
                2,
                "OSX-150",
            )
        )
        switch = self.repository.get_or_create(
            SwitchSpec("switch-read-model", "OSX-150", 5)
        )
        self.assignment = self.repository.install(
            AssignmentSpec(
                unit.unit_id,
                switch.switch_id,
                NOW,
                "AT",
                {1: 1, 2: 2},
            )
        )
        self.run = self.repository.create(
            RunSpec(
                assignment_id=self.assignment.assignment_id,
                run_number=1,
                client_run_uuid=uuid4(),
                run_started_at_utc=NOW,
                tested_by="AT",
                wavelength_mode="SM",
                operating_band="O band",
                application_version="test",
                measurement_hardware={
                    "measurement_classification": "native",
                    "source_wavelengths_nm": [1310, 1550],
                    "source_ids": [0, 1],
                },
                limit_snapshot=CRITERIA,
                part_number_snapshot="OSX-150-1A-002-09-FA-00B-3H",
                front_panel_channel_count=2,
            )
        )
        self.writer = MeasurementPersistenceWorkflow(self.repository)
        self.query = DatabaseRunQueryService(self.repository, self.repository)

    def write(self, channel, first, second, offset, *, physical_port=None):
        pending = self.writer.prepare_measurement(
            run_id=self.run.run_id,
            logical_channel=channel,
            physical_port=physical_port or channel,
            wavelength_1_nm=1310,
            wavelength_1_il_db=Decimal(first),
            wavelength_2_nm=1550,
            wavelength_2_il_db=Decimal(second),
            reference_snapshot=REFERENCE,
            written_by="AT",
            written_at_utc=NOW + timedelta(seconds=offset),
        )
        return self.writer.commit(pending)

    def populate_completed_run(self):
        first_channel_two = self.write(2, "3.0000", "3.1000", 1)
        channel_one = self.write(1, "0.6000", "0.5000", 2)
        retest_channel_two = self.write(2, "1.0000", "1.1000", 3)
        extra = self.write(3, "0.4000", "0.4500", 4)
        self.repository.finish(
            self.run.run_id,
            "complete",
            NOW + timedelta(seconds=5),
        )
        return first_channel_two, channel_one, retest_channel_two, extra

    def test_current_projection_and_history_have_distinct_semantics(self):
        first, _channel_one, retest, _extra = self.populate_completed_run()
        snapshot = self.query.load(self.run.run_id)

        self.assertEqual(
            tuple(record.channel for record in snapshot.measurements),
            (1, 2, 3),
        )
        self.assertEqual(snapshot.measurements[1].ordered_losses, (1.0, 1.1))
        self.assertEqual(
            tuple(attempt.channel for attempt in snapshot.measurement_attempts),
            (2, 1, 2, 3),
        )
        self.assertEqual(len(snapshot.measurement_attempts), 4)
        channel_two_history = [
            attempt
            for attempt in snapshot.measurement_attempts
            if attempt.channel == 2
        ]
        self.assertEqual(
            tuple(item.attempt_number for item in channel_two_history),
            (1, 2),
        )
        self.assertEqual(channel_two_history[0].attempt_id, str(first.measurement_uuid))
        self.assertEqual(channel_two_history[1].attempt_id, str(retest.measurement_uuid))
        self.assertEqual(
            channel_two_history[1].replaces_attempt_id,
            channel_two_history[0].attempt_id,
        )

    def test_all_consumers_use_the_same_latest_projection(self):
        self.populate_completed_run()
        snapshot = self.query.load(self.run.run_id)
        profile = LimitProfile.from_mapping(CRITERIA)

        filtered_table = snapshot.table_records(lambda record: record.channel == 2)
        self.assertEqual(tuple(record.channel for record in filtered_table), (2,))
        self.assertEqual(
            snapshot.copy_raw_data(),
            "1\t0.6000\t0.5000\n2\t1.0000\t1.1000\n3\t0.4000\t0.4500",
        )
        self.assertEqual(snapshot.comparison_records()[2].ordered_losses, (1.0, 1.1))

        analysis = snapshot.analysis(profile)
        self.assertEqual(analysis["total"], 3)
        self.assertEqual(analysis["failed"], 0)

        status = snapshot.status(profile=profile, planned_channels=(1, 2))
        self.assertEqual(status.completion_status, COMPLETION_COMPLETE)
        self.assertEqual(status.result_status, RESULT_PASS)

        coc_source = snapshot.coc_source()
        prepared = prepare_coc(coc_source, 2)
        self.assertTrue(prepared.eligible)
        self.assertEqual(prepared.channels[1].record.ordered_losses, (1.0, 1.1))
        self.assertEqual(coc_source.source_identifier, f"database-run:{self.run.run_id}")

        replacements = snapshot.replacement_analysis(profile)
        self.assertEqual(replacements["extra_ports"], [3])
        self.assertEqual(replacements["missing_channels"], [])

    def test_replacement_analysis_uses_the_profile_minimum_improvement(self):
        self.populate_completed_run()
        snapshot = self.query.load(self.run.run_id)
        criteria = dict(CRITERIA)
        criteria["minimum_replacement_improvement_db"] = 0.7
        profile = LimitProfile.from_mapping(criteria)

        replacements = snapshot.replacement_analysis(profile)

        self.assertEqual(replacements["minimum_improvement_db"], 0.7)
        self.assertEqual(replacements["recommendations"], [])

    def test_prepared_temporary_reading_is_absent_from_all_queries(self):
        self.write(1, "0.6000", "0.5000", 1)
        pending = self.writer.prepare_measurement(
            run_id=self.run.run_id,
            logical_channel=2,
            wavelength_1_nm=1310,
            wavelength_1_il_db="0.7000",
            wavelength_2_nm=1550,
            wavelength_2_il_db="0.6000",
            reference_snapshot=REFERENCE,
            written_by="AT",
            written_at_utc=NOW + timedelta(seconds=2),
        )
        snapshot = self.query.load(self.run.run_id)
        self.assertIsNotNone(pending.measurement_uuid)
        self.assertEqual(tuple(item.channel for item in snapshot.measurements), (1,))
        self.assertEqual(len(snapshot.measurement_attempts), 1)

    def test_assignment_run_list_is_ordered_by_operator_run_number(self):
        later = self.repository.create(
            RunSpec(
                self.assignment.assignment_id,
                3,
                uuid4(),
                NOW + timedelta(minutes=2),
                "AT",
                "SM",
                "O band",
                "test",
                limit_snapshot=CRITERIA,
            )
        )
        middle = self.repository.create(
            RunSpec(
                self.assignment.assignment_id,
                2,
                uuid4(),
                NOW + timedelta(minutes=1),
                "AT",
                "SM",
                "O band",
                "test",
                limit_snapshot=CRITERIA,
            )
        )
        snapshots = self.query.list_for_assignment(self.assignment.assignment_id)
        self.assertEqual(
            tuple(item.run.run_id for item in snapshots),
            (self.run.run_id, middle.run_id, later.run_id),
        )

    def test_missing_run_is_reported(self):
        with self.assertRaisesRegex(ValueError, "Run was not found"):
            self.query.load(999)


if __name__ == "__main__":
    unittest.main()
