import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from config.database_config import DatabaseSettings
from domain.database_records import (
    AssignmentSpec,
    MeasurementSpec,
    MeasurementWriteSpec,
    ReplacementSpec,
    RunStartSpec,
    RunSpec,
    SpareEventSpec,
    SwitchSpec,
    UnitSpec,
)
from infrastructure.database.connection import DatabaseConnectionFactory
from infrastructure.database.memory_repositories import InMemoryRepositories
from infrastructure.database.sql_repositories import SqlRepositories


NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


class RepositoryContractMixin:
    repository = None

    def exercise_repository_contract(self):
        repository = self.repository
        token = uuid4().hex
        unit = repository.get_or_create(
            UnitSpec(
                main_board_serial="unit-" + token,
                part_number="OSX-150-1A-048-09-FA-00B-3H",
                front_panel_channel_count=48,
                unit_model="OSX-150",
            )
        )
        self.assertEqual(
            repository.get_or_create(
                UnitSpec(unit.main_board_serial, front_panel_channel_count=48)
            ).unit_id,
            unit.unit_id,
        )
        self.assertEqual(repository.get_unit(unit.unit_id).unit_id, unit.unit_id)
        self.assertEqual(
            repository.get_by_main_board_serial(unit.main_board_serial).unit_id,
            unit.unit_id,
        )
        switch = repository.get_or_create(
            SwitchSpec("switch-" + token, "OSX-150", 51, "03.01.23")
        )
        self.assertEqual(repository.get_switch(switch.switch_id), switch)
        self.assertEqual(repository.get_by_serial(switch.switch_serial), switch)
        assignment = repository.install(
            AssignmentSpec(unit.unit_id, switch.switch_id, NOW, "AT", {1: 1, 2: 2})
        )
        self.assertEqual(repository.get_active(unit.unit_id), assignment)
        self.assertEqual(
            repository.get_assignment(assignment.assignment_id), assignment
        )

        run_uuid = uuid4()
        run = repository.create(
            RunSpec(
                assignment_id=assignment.assignment_id,
                run_number=1,
                client_run_uuid=run_uuid,
                run_started_at_utc=NOW,
                tested_by="AT",
                wavelength_mode="SM",
                operating_band="O band",
                application_version="test",
                measurement_hardware={"ilm": {"model": "OP815"}},
                limit_snapshot={"too_good_db": 0.5, "failure_db": 2.5},
            )
        )
        self.assertEqual(repository.create(
            RunSpec(
                assignment.assignment_id, 99, run_uuid, NOW, "ignored", "SM",
                "O band", "test"
            )
        ).run_id, run.run_id)
        self.assertEqual(repository.get_by_uuid(run_uuid).run_id, run.run_id)
        self.assertEqual(repository.get(run.run_id), run)
        self.assertEqual(repository.list_for_unit(unit.unit_id), (run,))
        self.assertEqual(
            repository.get_for_unit_run_number(unit.unit_id, 1), run
        )
        self.assertEqual(repository.find_stale_in_progress(NOW + timedelta(seconds=1)), (run,))

        next_run = repository.create_next(
            RunStartSpec(
                assignment_id=assignment.assignment_id,
                client_run_uuid=uuid4(),
                run_started_at_utc=NOW,
                tested_by="AT",
                wavelength_mode="SM",
                operating_band="O band",
                application_version="test",
                measurement_hardware={"ilm": {"model": "OP815"}},
                limit_snapshot={"failure_db": 2.5},
            )
        )
        self.assertEqual(next_run.run_number, 2)
        self.assertEqual(
            repository.create_next(
                RunStartSpec(
                    assignment.assignment_id,
                    next_run.client_run_uuid,
                    NOW,
                    "ignored",
                    "SM",
                    "O band",
                    "test",
                )
            ).run_id,
            next_run.run_id,
        )
        repository.finish(next_run.run_id, "failed", NOW + timedelta(seconds=1))
        self.assertEqual(
            repository.list_for_assignment(assignment.assignment_id),
            (run, repository.get(next_run.run_id)),
        )

        first = repository.append_attempt(
            MeasurementSpec(
                uuid4(), run.run_id, 1, 1, 1310, Decimal("0.6500"),
                1550, Decimal("0.5000"), {"snapshot_id": "ref-1"}, NOW,
                "AT", 1,
            )
        )
        second_uuid = uuid4()
        second = repository.append_attempt(
            MeasurementSpec(
                second_uuid, run.run_id, 1, 2, 1310, Decimal("0.6200"),
                1550, Decimal("0.4800"), {"snapshot_id": "ref-1"},
                NOW + timedelta(seconds=1), "AT", 1,
            )
        )
        self.assertEqual(repository.append_attempt(
            MeasurementSpec(
                second_uuid, run.run_id, 1, 2, 1310, Decimal("9"),
                1550, Decimal("9"), {"snapshot_id": "ignored"}, NOW, "ignored", 1,
            )
        ).measurement_id, second.measurement_id)
        self.assertEqual(repository.history_for_run(run.run_id), (first, second))
        self.assertEqual(repository.current_for_run(run.run_id), (second,))
        self.assertEqual(
            repository.snapshot_for_run(run.run_id),
            ((second,), (first, second)),
        )

        next_uuid = uuid4()
        third = repository.append_next(
            MeasurementWriteSpec(
                next_uuid,
                run.run_id,
                1,
                1310,
                Decimal("0.6100"),
                1550,
                Decimal("0.4700"),
                {"snapshot_id": "ref-1"},
                NOW + timedelta(seconds=2),
                "AT",
                1,
            )
        )
        self.assertEqual(third.attempt_number, 3)
        self.assertEqual(
            repository.append_next(
                MeasurementWriteSpec(
                    next_uuid,
                    run.run_id,
                    1,
                    1310,
                    Decimal("8"),
                    1550,
                    Decimal("8"),
                    {"snapshot_id": "ignored"},
                    NOW,
                    "ignored",
                    1,
                )
            ).measurement_id,
            third.measurement_id,
        )
        self.assertEqual(repository.get_measurement_by_uuid(next_uuid), third)
        self.assertEqual(repository.history_for_run(run.run_id), (first, second, third))
        self.assertEqual(repository.current_for_run(run.run_id), (third,))
        self.assertEqual(
            repository.snapshot_for_run(run.run_id),
            ((third,), (first, second, third)),
        )

        parallel_specs = tuple(
            MeasurementWriteSpec(
                uuid4(),
                run.run_id,
                2,
                1310,
                Decimal("0.7000"),
                1550,
                Decimal("0.5500"),
                {"snapshot_id": "ref-1"},
                NOW + timedelta(seconds=3),
                "AT",
                2,
            )
            for _ in range(6)
        )
        with ThreadPoolExecutor(max_workers=6) as executor:
            parallel_records = tuple(executor.map(repository.append_next, parallel_specs))
        self.assertEqual(
            sorted(item.attempt_number for item in parallel_records),
            list(range(1, 7)),
        )

        replacement = repository.append(
            ReplacementSpec(
                assignment.assignment_id, 1, 1, 49, "Optimization", "AT", NOW,
                run.run_id,
            )
        )
        replacement_again = repository.append(
            ReplacementSpec(
                assignment.assignment_id,
                1,
                49,
                51,
                "Replacement port failed",
                "AT",
                NOW + timedelta(seconds=4),
                run.run_id,
            )
        )
        designated = repository.append_event(
            SpareEventSpec(assignment.assignment_id, 50, "designated", "AT", NOW)
        )
        undesignated = repository.append_event(
            SpareEventSpec(
                assignment.assignment_id,
                50,
                "undesignated",
                "AT",
                NOW + timedelta(seconds=1),
            )
        )
        active_spare = repository.append_event(
            SpareEventSpec(
                assignment.assignment_id,
                49,
                "designated",
                "AT",
                NOW + timedelta(seconds=2),
            )
        )
        self.assertEqual(replacement.previous_physical_port, 1)
        self.assertEqual(replacement_again.previous_physical_port, 49)
        self.assertEqual(
            repository.replacement_history_for_assignment(
                assignment.assignment_id
            ),
            (replacement, replacement_again),
        )
        channel_map = repository.current_channel_map(assignment.assignment_id)
        self.assertEqual(
            tuple(item.effective_physical_port for item in channel_map),
            (51, 2),
        )
        self.assertEqual(
            repository.spare_history_for_assignment(assignment.assignment_id),
            (designated, undesignated, active_spare),
        )
        self.assertEqual(
            repository.active_spares_for_assignment(assignment.assignment_id),
            (49,),
        )
        self.assertEqual(
            repository.routing_snapshot_for_assignment(assignment.assignment_id),
            (
                channel_map,
                (replacement, replacement_again),
                (designated, undesignated, active_spare),
                (49,),
            ),
        )

        finished = repository.finish(run.run_id, "complete", NOW + timedelta(minutes=1))
        self.assertEqual(finished.completion_status, "complete")
        resumed = repository.resume(run.run_id)
        self.assertEqual(resumed.completion_status, "in_progress")
        self.assertIsNone(resumed.run_ended_at_utc)
        finished = repository.finish(
            run.run_id, "complete", NOW + timedelta(minutes=1)
        )
        included = repository.set_analysis_status(run.run_id, "included")
        self.assertEqual(included.analysis_status, "included")
        self.assertEqual(repository.find_stale_in_progress(NOW + timedelta(days=1)), ())
        replacement_switch = repository.get_or_create(
            SwitchSpec("switch-replacement-" + token, "OSX-150", 51, "03.01.23")
        )
        replacement_assignment = repository.replace_active(
            assignment.assignment_id,
            AssignmentSpec(
                unit.unit_id,
                replacement_switch.switch_id,
                NOW + timedelta(minutes=2),
                "AT",
                {1: 1, 2: 2},
            ),
            NOW + timedelta(minutes=2),
            "AT",
            "Switch failed",
        )
        history = repository.history_for_unit(unit.unit_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].removal_reason, "Switch failed")
        self.assertEqual(
            repository.get_active_for_switch(replacement_switch.switch_id),
            replacement_assignment,
        )
        self.assertEqual(
            tuple(
                item.effective_physical_port
                for item in repository.current_channel_map(
                    assignment.assignment_id
                )
            ),
            (51, 2),
        )
        self.assertEqual(
            repository.replacement_history_for_assignment(
                replacement_assignment.assignment_id
            ),
            (),
        )
        self.assertEqual(
            tuple(
                item.effective_physical_port
                for item in repository.current_channel_map(
                    replacement_assignment.assignment_id
                )
            ),
            (1, 2),
        )
        self.assertEqual(
            repository.active_spares_for_assignment(
                replacement_assignment.assignment_id
            ),
            (),
        )
        continued_numbering = repository.create_next(
            RunStartSpec(
                replacement_assignment.assignment_id,
                uuid4(),
                NOW + timedelta(minutes=2),
                "AT",
                "SM",
                "O band",
                "test",
            )
        )
        self.assertEqual(continued_numbering.run_number, 3)
        repository.finish(
            continued_numbering.run_id,
            "stopped",
            NOW + timedelta(minutes=3),
        )
        removed = repository.remove(
            replacement_assignment.assignment_id,
            NOW + timedelta(minutes=4),
            "AT",
            "Removed after test",
        )
        self.assertEqual(removed.removal_reason, "Removed after test")
        self.assertIsNone(repository.get_active(unit.unit_id))
        return token


class InMemoryRepositoryTests(RepositoryContractMixin, unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepositories()

    def test_complete_repository_contract(self):
        self.exercise_repository_contract()

    def test_duplicate_active_assignment_is_rejected(self):
        unit = self.repository.get_or_create(UnitSpec("unit"))
        first = self.repository.get_or_create(SwitchSpec("switch-1", "OSX-150", 48))
        second = self.repository.get_or_create(SwitchSpec("switch-2", "OSX-150", 48))
        self.repository.install(AssignmentSpec(unit.unit_id, first.switch_id, NOW, "AT", {1: 1}))
        with self.assertRaisesRegex(ValueError, "already has"):
            self.repository.install(
                AssignmentSpec(unit.unit_id, second.switch_id, NOW, "AT", {1: 1})
            )

    def test_failed_operation_does_not_partially_append(self):
        with self.assertRaises(ValueError):
            self.repository.append_event(SpareEventSpec(999, 1, "invalid", "AT", NOW))
        self.assertEqual(self.repository.spare_events, {})


@unittest.skipUnless(
    os.environ.get("LWB_TEST_SQL_CONNECTION_STRING"),
    "Set LWB_TEST_SQL_CONNECTION_STRING to run SQL repository integration tests",
)
class SqlRepositoryIntegrationTests(RepositoryContractMixin, unittest.TestCase):
    def setUp(self):
        connection_string = os.environ["LWB_TEST_SQL_CONNECTION_STRING"]

        def connector(_generated, **kwargs):
            import pyodbc

            return pyodbc.connect(
                connection_string,
                timeout=kwargs.get("timeout", 10),
                autocommit=False,
            )

        self.repository = SqlRepositories(
            DatabaseConnectionFactory(DatabaseSettings(enabled=True), connector)
        )

    def test_complete_repository_contract(self):
        token = self.exercise_repository_contract()
        self._delete_fixture(
            "unit-" + token,
            ("switch-" + token, "switch-replacement-" + token),
        )

    def test_sql_injection_like_serial_is_stored_as_data(self):
        token = uuid4().hex
        unit_serial = "unit-'; DROP TABLE dbo.UNITS;--" + token
        record = self.repository.get_or_create(UnitSpec(unit_serial))
        self.assertEqual(record.main_board_serial, unit_serial)
        self._delete_fixture(unit_serial, ("unused-switch-" + token,))

    def _delete_fixture(self, unit_serial, switch_serials):
        import pyodbc

        connection = pyodbc.connect(
            os.environ["LWB_TEST_SQL_CONNECTION_STRING"], timeout=10
        )
        cursor = connection.cursor()
        try:
            cursor.execute(
                "DELETE FROM dbo.DESIGNATED_SPARES WHERE assignment_id IN "
                "(SELECT assignment_id FROM dbo.UNIT_SWITCH_ASSIGNMENTS WHERE unit_id IN "
                "(SELECT unit_id FROM dbo.UNITS WHERE main_board_serial = ?))",
                unit_serial,
            )
            cursor.execute(
                "DELETE FROM dbo.CHANNEL_REPLACEMENTS WHERE assignment_id IN "
                "(SELECT assignment_id FROM dbo.UNIT_SWITCH_ASSIGNMENTS WHERE unit_id IN "
                "(SELECT unit_id FROM dbo.UNITS WHERE main_board_serial = ?))",
                unit_serial,
            )
            cursor.execute(
                "DELETE FROM dbo.IL_MEASUREMENTS WHERE run_id IN "
                "(SELECT run_id FROM dbo.IL_RUNS WHERE assignment_id IN "
                "(SELECT assignment_id FROM dbo.UNIT_SWITCH_ASSIGNMENTS WHERE unit_id IN "
                "(SELECT unit_id FROM dbo.UNITS WHERE main_board_serial = ?)))",
                unit_serial,
            )
            cursor.execute(
                "DELETE FROM dbo.IL_RUNS WHERE assignment_id IN "
                "(SELECT assignment_id FROM dbo.UNIT_SWITCH_ASSIGNMENTS WHERE unit_id IN "
                "(SELECT unit_id FROM dbo.UNITS WHERE main_board_serial = ?))",
                unit_serial,
            )
            cursor.execute(
                "DELETE FROM dbo.UNIT_SWITCH_ASSIGNMENTS WHERE unit_id IN "
                "(SELECT unit_id FROM dbo.UNITS WHERE main_board_serial = ?)",
                unit_serial,
            )
            for switch_serial in switch_serials:
                cursor.execute(
                    "DELETE FROM dbo.SWITCHES WHERE switch_serial = ?",
                    switch_serial,
                )
            cursor.execute("DELETE FROM dbo.UNITS WHERE main_board_serial = ?", unit_serial)
            connection.commit()
        finally:
            cursor.close()
            connection.close()


if __name__ == "__main__":
    unittest.main()
