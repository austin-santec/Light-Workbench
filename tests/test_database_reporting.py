import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QTableWidget

from application.database_reporting import DatabaseReportingService
from application.measurement_persistence_workflow import MeasurementPersistenceWorkflow
from domain.database_records import (
    AssignmentSpec,
    ReplacementSpec,
    RunSpec,
    SwitchSpec,
    UnitSpec,
)
from domain.database_reporting import ReportFilters, format_report_csv
from infrastructure.database.memory_repositories import InMemoryRepositories
from ui.database_reports import (
    CHANNEL_HEADERS,
    DatabaseReportsDialog,
    RUN_HEADERS,
    channel_report_rows,
    run_report_rows,
)


NOW = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)
PROFILE = {
    "model": "OSX-150",
    "wavelength_mode": "SM",
    "profile_name": "OSX-150 SM",
    "revision": "1",
    "too_good_below_db": 0.5,
    "warning_enabled": True,
    "warning_above_db": 2.25,
    "fail_above_db": 2.5,
}


class DatabaseReportingTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepositories()
        self.unit = self.repository.get_or_create(
            UnitSpec("MB-REPORT", "OSX-150-1A-002-09-FA-00B-3H", 2, "OSX-150")
        )
        self.switch = self.repository.get_or_create(
            SwitchSpec("SW-REPORT", "OSX-150", 4, "03.01.23")
        )
        self.assignment = self.repository.install(
            AssignmentSpec(
                self.unit.unit_id,
                self.switch.switch_id,
                NOW,
                "AT",
                {1: 1, 2: 2},
            )
        )
        self.writer = MeasurementPersistenceWorkflow(self.repository)
        self.service = DatabaseReportingService(self.repository)

    def create_run(
        self,
        number,
        *,
        purpose="production",
        analysis="pending",
        operator="AT",
        station=3,
        started=None,
    ):
        run = self.repository.create(
            RunSpec(
                assignment_id=self.assignment.assignment_id,
                run_number=number,
                client_run_uuid=uuid4(),
                run_started_at_utc=started or NOW + timedelta(minutes=number),
                tested_by=operator,
                station_number=station,
                wavelength_mode="SM",
                operating_band="O band",
                application_version="test",
                measurement_hardware={"planned_channels": [1, 2]},
                limit_snapshot=PROFILE,
                run_purpose=purpose,
                analysis_status=analysis,
                part_number_snapshot="OSX-150-1A-002-09-FA-00B-3H",
                front_panel_channel_count=2,
            )
        )
        return run

    def write(self, run, channel, first, second, seconds, physical=None):
        return self.writer.commit(
            self.writer.prepare_measurement(
                run_id=run.run_id,
                logical_channel=channel,
                physical_port=physical or channel,
                wavelength_1_nm=1310,
                wavelength_1_il_db=first,
                wavelength_2_nm=1550,
                wavelength_2_il_db=second,
                reference_snapshot={"snapshot_id": "ref-1"},
                written_by="AT",
                written_at_utc=run.run_started_at_utc + timedelta(seconds=seconds),
            )
        )

    def populate_included_run(self):
        run = self.create_run(1, analysis="included")
        self.write(run, 1, 2.7, 2.6, 1)
        self.write(run, 1, 0.7, 0.6, 2, physical=3)
        self.write(run, 2, 2.3, 2.2, 3)
        self.repository.finish(
            run.run_id,
            "complete",
            run.run_started_at_utc + timedelta(seconds=4),
        )
        self.repository.append(
            ReplacementSpec(
                assignment_id=self.assignment.assignment_id,
                logical_channel=1,
                previous_physical_port=1,
                replacement_physical_port=3,
                reason="Improved loss",
                replaced_by="AT",
                replaced_at_utc=run.run_started_at_utc + timedelta(seconds=5),
                related_run_id=run.run_id,
                notes="Operator replacement details",
            )
        )
        return run

    def test_default_scope_excludes_pending_and_nonproduction_runs(self):
        included = self.populate_included_run()
        pending = self.create_run(2, analysis="pending")
        self.repository.append(
            ReplacementSpec(
                assignment_id=self.assignment.assignment_id,
                logical_channel=1,
                previous_physical_port=3,
                replacement_physical_port=4,
                reason="Pending engineering review",
                replaced_by="AT",
                replaced_at_utc=pending.run_started_at_utc + timedelta(seconds=1),
                related_run_id=pending.run_id,
            )
        )
        self.create_run(3, purpose="engineering", analysis="included")

        report = self.service.search()

        self.assertEqual(tuple(row.run_id for row in report.runs), (included.run_id,))
        self.assertEqual(report.summary.run_count, 1)
        self.assertEqual(report.summary.attempt_count, 3)
        self.assertEqual(report.summary.retest_attempt_count, 1)
        self.assertEqual(report.summary.retested_channel_count, 1)
        self.assertEqual(report.summary.replacement_count, 1)
        self.assertEqual(report.runs[0].replacement_count, 1)

    def test_explicit_troubleshooting_scope_and_filters_include_other_data(self):
        self.populate_included_run()
        pending = self.create_run(2, analysis="pending", operator="BD")
        self.create_run(3, purpose="engineering", analysis="included", operator="BD")

        report = self.service.search(
            ReportFilters(
                tested_by="bd",
                run_purpose="production",
                analysis_status="pending",
                include_all_records=True,
            )
        )

        self.assertEqual(tuple(row.run_id for row in report.runs), (pending.run_id,))

    def test_saved_limit_snapshot_drives_result_and_retest_metrics(self):
        self.populate_included_run()

        row = self.service.search().runs[0]

        self.assertEqual(row.result_status, "pass_review_recommended")
        self.assertEqual(row.failing_channel_count, 0)
        self.assertEqual(row.optimization_channel_count, 1)
        self.assertEqual(row.current_channel_count, 2)
        self.assertEqual(row.retest_attempt_count, 1)
        self.assertEqual(row.station_number, 3)

    def test_station_filter_and_export_column_are_supported(self):
        included = self.populate_included_run()
        other = self.create_run(2, analysis="included", station=4)

        report = self.service.search(
            ReportFilters(station_number=4, include_all_records=True)
        )

        self.assertEqual(tuple(row.run_id for row in report.runs), (other.run_id,))
        self.assertEqual(run_report_rows(report)[0][7], "4")

    def test_channel_history_preserves_superseded_and_current_attempts(self):
        run = self.populate_included_run()

        rows = self.service.channels_for_run(run.run_id)

        channel_one = [row for row in rows if row.logical_channel == 1]
        self.assertEqual(tuple(row.attempt_number for row in channel_one), (1, 2))
        self.assertEqual(tuple(row.is_current for row in channel_one), (False, True))
        self.assertEqual(channel_one[1].physical_port, 3)

    def test_replacement_outcome_uses_related_run_current_reading(self):
        self.populate_included_run()

        replacement = self.service.search().replacements[0]

        self.assertEqual(replacement.related_run_number, 1)
        self.assertEqual(replacement.notes, "Operator replacement details")
        self.assertEqual(replacement.outcome, "Pass")

    def test_report_csv_uses_application_rows_and_quotes_values(self):
        self.populate_included_run()
        report = self.service.search()
        rows = run_report_rows(report)

        output = format_report_csv(RUN_HEADERS, rows)

        self.assertTrue(output.startswith("Unit Serial,Part Number,"))
        self.assertIn("MB-REPORT", output)
        self.assertTrue(output.endswith("\n"))
        channel_output = format_report_csv(
            CHANNEL_HEADERS,
            channel_report_rows(self.service.channels_for_run(report.runs[0].run_id)),
        )
        self.assertIn("Superseded", channel_output)
        self.assertIn("0.7000", channel_output)

    def test_dialog_displays_read_only_runs_and_selected_channel_history(self):
        app = QApplication.instance() or QApplication([])
        self.populate_included_run()

        dialog = DatabaseReportsDialog(self.service)
        dialog.run_table.selectRow(0)
        app.processEvents()

        self.assertEqual(dialog.run_table.rowCount(), 1)
        self.assertEqual(dialog.channel_table.rowCount(), 3)
        self.assertEqual(
            dialog.run_table.editTriggers(),
            QTableWidget.NoEditTriggers,
        )
        self.assertIn("Retests: 1", dialog.summary_label.text())
        dialog.close()

    def test_dialog_report_tabs_follow_light_and_dark_theme(self):
        app = QApplication.instance() or QApplication([])
        self.populate_included_run()

        dialog = DatabaseReportsDialog(self.service)
        self.assertEqual(dialog.tabs.count(), 4)
        self.assertIn("#ffffff", dialog.styleSheet())
        self.assertEqual(dialog.tabs.objectName(), "database_report_tabs")
        self.assertEqual(dialog.tabs.tabBar().objectName(), "database_report_tab_bar")
        dialog.apply_theme(True)
        self.assertIn("#25272b", dialog.styleSheet())
        self.assertIn("#3a3e45", dialog.styleSheet())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
