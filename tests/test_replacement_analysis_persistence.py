import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from application.replacement_analysis_persistence import (
    RESULT_RECOMMENDATIONS_AVAILABLE,
    ReplacementAnalysisPersistenceWorkflow,
)
from domain.database_records import (
    AssignmentSpec,
    MEASUREMENT_ROLE_EXTRA_CANDIDATE,
    MeasurementSpec,
    ReplacementSpec,
    RunSpec,
    SwitchSpec,
    UnitSpec,
)
from infrastructure.database.memory_repositories import InMemoryRepositories


NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


class ReplacementAnalysisPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepositories()
        unit = self.repository.get_or_create(
            UnitSpec(
                "S-ANALYSIS",
                part_number="OSX-150-1A-048-09-FA-00B-3H",
                front_panel_channel_count=48,
                unit_model="OSX-150",
            )
        )
        switch = self.repository.get_or_create(SwitchSpec("SW-ANALYSIS", "OSX-150", 49))
        assignment = self.repository.install(
            AssignmentSpec(unit.unit_id, switch.switch_id, NOW, "AT", {1: 1, 2: 2})
        )
        self.run = self.repository.create(
            RunSpec(
                assignment_id=assignment.assignment_id,
                run_number=1,
                client_run_uuid=uuid4(),
                run_started_at_utc=NOW,
                tested_by="AT",
                wavelength_mode="SM",
                operating_band="O band",
                application_version="test",
                measurement_hardware={"ilm": {"model": "OP815"}},
                limit_snapshot={"model": "OSX-150", "failure_db": 2.5},
                front_panel_channel_count=48,
            )
        )
        self.repository.append_attempt(
            MeasurementSpec(
                uuid4(), self.run.run_id, 1, 1, 1310, Decimal("2.6"),
                1550, Decimal("2.6"), {"snapshot_id": "ref"}, NOW, "AT", 1,
            )
        )
        self.extra_measurement = self.repository.append_attempt(
            MeasurementSpec(
                uuid4(), self.run.run_id, None, 1, 1310, Decimal("0.7"),
                1550, Decimal("0.8"), {"snapshot_id": "ref"}, NOW, "AT", 49,
                MEASUREMENT_ROLE_EXTRA_CANDIDATE,
            )
        )
        self.repository.append_attempt(
            MeasurementSpec(
                uuid4(), self.run.run_id, 2, 2, 1310, Decimal("0.7"),
                1550, Decimal("0.8"), {"snapshot_id": "ref"}, NOW, "AT", 2,
            )
        )

    def _result(self):
        return {
            "applicable": True,
            "status": "Performed",
            "designed_channel_count": 1,
            "extra_ports": [49],
            "missing_channels": [],
            "warning_limit_db": 2.25,
            "optimization_limit_db": 2.25,
            "fail_limit_db": 2.5,
            "too_good_below_db": 0.5,
            "minimum_improvement_db": 0.2,
            "bottom_spare_count": 2,
            "bottom_spares": [],
            "remaining_extras": [],
            "recommendations": [
                {
                    "logical_channel": 1,
                    "category": "required",
                    "current_physical_port": 1,
                    "candidate_physical_port": 49,
                    "current_loss_1310_db": 2.6,
                    "current_loss_1550_db": 2.6,
                    "candidate_loss_1310_db": 0.7,
                    "candidate_loss_1550_db": 0.8,
                    "current_worst_loss_db": 2.6,
                    "candidate_worst_loss_db": 0.8,
                    "improvement_db": 1.8,
                    "current_measurement_id": 1,
                    "candidate_measurement_id": self.extra_measurement.measurement_id,
                }
            ],
        }

    def test_analysis_history_is_restored_and_recommendation_can_be_linked(self):
        workflow = ReplacementAnalysisPersistenceWorkflow(self.repository)
        saved = workflow.save_result(
            run_id=self.run.run_id,
            result=self._result(),
            analyzed_by="AT",
            application_version="test",
            front_panel_channel_count=1,
            wavelengths=(1310, 1550),
            criteria={"model": "OSX-150", "revision": "test"},
            measurement_count=2,
        )

        self.assertEqual(saved.record.result_status, RESULT_RECOMMENDATIONS_AVAILABLE)
        self.assertEqual(len(saved.recommendations), 1)
        recommendation_id = saved.recommendations[0].recommendation_id
        restored = workflow.latest_for_run(self.run.run_id)
        self.assertEqual(restored.record.analysis_id, saved.record.analysis_id)
        self.assertEqual(restored.to_result_dict()["recommendations"][0]["recommendation_id"], recommendation_id)
        self.assertEqual(len(workflow.history_for_run(self.run.run_id)), 1)

        replacement = self.repository.append(
            ReplacementSpec(
                self.run.assignment_id,
                1,
                1,
                49,
                "Optimization",
                "AT",
                NOW,
                self.run.run_id,
                source_recommendation_id=recommendation_id,
            )
        )
        self.assertEqual(replacement.source_recommendation_id, recommendation_id)

    def test_new_measurement_marks_saved_analysis_stale(self):
        workflow = ReplacementAnalysisPersistenceWorkflow(self.repository)
        workflow.save_result(
            run_id=self.run.run_id,
            result=self._result(),
            analyzed_by="AT",
            application_version="test",
            front_panel_channel_count=1,
            wavelengths=(1310, 1550),
            criteria={"model": "OSX-150"},
            measurement_count=2,
        )
        self.assertTrue(
            workflow.latest_for_run(self.run.run_id).is_current(
                workflow.current_high_watermark(self.run.run_id)
            )
        )
        self.repository.append_attempt(
            MeasurementSpec(
                uuid4(), self.run.run_id, 1, 2, 1310, Decimal("2.4"),
                1550, Decimal("2.4"), {"snapshot_id": "ref"}, NOW, "AT", 1,
            )
        )
        self.assertFalse(
            workflow.latest_for_run(self.run.run_id).is_current(
                workflow.current_high_watermark(self.run.run_id)
            )
        )

    def test_assignment_scoped_snapshot_can_use_measurement_from_an_included_run(self):
        second = self.repository.create(
            RunSpec(
                assignment_id=self.run.assignment_id,
                run_number=2,
                client_run_uuid=uuid4(),
                run_started_at_utc=NOW,
                tested_by="AT",
                wavelength_mode="SM",
                operating_band="O band",
                application_version="test",
                measurement_hardware={"ilm": {"model": "OP815"}},
                limit_snapshot={"model": "OSX-150", "failure_db": 2.5},
                front_panel_channel_count=48,
            )
        )
        considered = sorted(self.repository.measurements)
        result = self._result()
        result["recommendations"] = []
        result["source_snapshot"] = {
            "assignment_id": self.run.assignment_id,
            "context_run_id": second.run_id,
            "included_run_ids": [self.run.run_id, second.run_id],
            "included_run_states": [
                {
                    "run_id": self.run.run_id,
                    "analysis_status": self.run.analysis_status,
                    "superseded_by_run_id": self.run.superseded_by_run_id,
                },
                {
                    "run_id": second.run_id,
                    "analysis_status": second.analysis_status,
                    "superseded_by_run_id": second.superseded_by_run_id,
                },
            ],
            "considered_measurement_ids": considered,
            "measurement_high_watermark_id": max(considered),
            "replacement_ids": [],
            "spare_event_ids": [],
            "state_fingerprint_sha256": "a" * 64,
        }

        saved = ReplacementAnalysisPersistenceWorkflow(self.repository).save_result(
            run_id=second.run_id,
            result=result,
            analyzed_by="AT",
            application_version="test",
            front_panel_channel_count=48,
            wavelengths=(1310, 1550),
            criteria={"model": "OSX-150"},
            measurement_count=3,
        )

        self.assertEqual(saved.record.run_id, second.run_id)
        self.assertTrue(saved.is_current("a" * 64))
        self.assertFalse(saved.is_current("legacy-nonnumeric-state"))


if __name__ == "__main__":
    unittest.main()
