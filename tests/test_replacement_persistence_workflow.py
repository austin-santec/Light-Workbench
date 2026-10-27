import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from application.replacement_persistence_workflow import (
    ReplacementChangeRequest,
    ReplacementPersistenceWorkflow,
)
from domain.database_records import (
    AssignmentSpec,
    RunSpec,
    SwitchSpec,
    UnitSpec,
)
from infrastructure.database.memory_repositories import InMemoryRepositories


NOW = datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc)


class ReplacementPersistenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryRepositories()
        self.unit = self.repository.get_or_create(
            UnitSpec("unit-routing", front_panel_channel_count=2)
        )
        self.switch = self.repository.get_or_create(
            SwitchSpec("switch-routing", "OSX-150", 5)
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
        self.run = self.repository.create(
            RunSpec(
                self.assignment.assignment_id,
                1,
                uuid4(),
                NOW,
                "AT",
                "SM",
                "O band",
                "test",
            )
        )
        self.workflow = ReplacementPersistenceWorkflow(self.repository)

    def test_repeated_replacements_preserve_history_and_update_current_map(self):
        first = self.workflow.record_replacement(
            assignment_id=self.assignment.assignment_id,
            logical_channel=1,
            previous_physical_port=1,
            replacement_physical_port=4,
            reason="High loss",
            replaced_by="AT",
            related_run_id=self.run.run_id,
            replaced_at_utc=NOW + timedelta(seconds=1),
        )
        second = self.workflow.record_replacement(
            assignment_id=self.assignment.assignment_id,
            logical_channel=1,
            previous_physical_port=4,
            replacement_physical_port=5,
            reason="Replacement port failed",
            replaced_by="JS",
            related_run_id=self.run.run_id,
            replaced_at_utc=NOW + timedelta(seconds=2),
        )

        snapshot = self.workflow.load_assignment(self.assignment.assignment_id)
        self.assertEqual(snapshot.effective_channel_map, {1: 5, 2: 2})
        self.assertEqual(snapshot.replacement_history, (first, second))
        self.assertEqual(
            snapshot.channel_map[0].latest_replacement_id,
            second.replacement_id,
        )
        self.assertEqual(snapshot.channel_map[0].initial_physical_port, 1)

        self.repository.finish(
            self.run.run_id,
            "complete",
            NOW + timedelta(seconds=3),
        )
        self.repository.create(
            RunSpec(
                self.assignment.assignment_id,
                2,
                uuid4(),
                NOW + timedelta(minutes=1),
                "JS",
                "SM",
                "O band",
                "test",
            )
        )
        after_run_change = self.workflow.load_assignment(
            self.assignment.assignment_id
        )
        self.assertEqual(after_run_change.replacement_history, (first, second))
        self.assertEqual(first.related_run_id, self.run.run_id)

    def test_replacement_must_continue_from_current_effective_port(self):
        self.workflow.record_replacement(
            assignment_id=self.assignment.assignment_id,
            logical_channel=1,
            previous_physical_port=1,
            replacement_physical_port=4,
            reason="High loss",
            replaced_by="AT",
            replaced_at_utc=NOW + timedelta(seconds=1),
        )
        with self.assertRaisesRegex(ValueError, "current channel map"):
            self.workflow.record_replacement(
                assignment_id=self.assignment.assignment_id,
                logical_channel=1,
                previous_physical_port=1,
                replacement_physical_port=5,
                reason="Incorrect chain",
                replaced_by="AT",
                replaced_at_utc=NOW + timedelta(seconds=2),
            )

    def test_replacement_rejects_conflicts_capacity_and_unrelated_runs(self):
        with self.assertRaisesRegex(ValueError, "already in use"):
            self.workflow.record_replacement(
                assignment_id=self.assignment.assignment_id,
                logical_channel=1,
                previous_physical_port=1,
                replacement_physical_port=2,
                reason="Conflict",
                replaced_by="AT",
                replaced_at_utc=NOW + timedelta(seconds=1),
            )
        with self.assertRaisesRegex(ValueError, "capacity"):
            self.workflow.record_replacement(
                assignment_id=self.assignment.assignment_id,
                logical_channel=1,
                previous_physical_port=1,
                replacement_physical_port=6,
                reason="Out of range",
                replaced_by="AT",
                replaced_at_utc=NOW + timedelta(seconds=1),
            )

        other_unit = self.repository.get_or_create(
            UnitSpec("other-unit", front_panel_channel_count=1)
        )
        other_switch = self.repository.get_or_create(
            SwitchSpec("other-switch", "OSX-150", 2)
        )
        other_assignment = self.repository.install(
            AssignmentSpec(
                other_unit.unit_id,
                other_switch.switch_id,
                NOW,
                "AT",
                {1: 1},
            )
        )
        other_run = self.repository.create(
            RunSpec(
                other_assignment.assignment_id,
                1,
                uuid4(),
                NOW,
                "AT",
                "SM",
                "O band",
                "test",
            )
        )
        with self.assertRaisesRegex(ValueError, "does not belong"):
            self.workflow.record_replacement(
                assignment_id=self.assignment.assignment_id,
                logical_channel=1,
                previous_physical_port=1,
                replacement_physical_port=4,
                reason="Wrong run",
                replaced_by="AT",
                related_run_id=other_run.run_id,
                replaced_at_utc=NOW + timedelta(seconds=1),
            )

    def test_spare_events_preserve_history_and_derive_active_set(self):
        designated_four = self.workflow.designate_spare(
            self.assignment.assignment_id,
            4,
            "AT",
            recorded_at_utc=NOW + timedelta(seconds=1),
        )
        designated_five = self.workflow.designate_spare(
            self.assignment.assignment_id,
            5,
            "AT",
            recorded_at_utc=NOW + timedelta(seconds=2),
        )
        removed_four = self.workflow.undesignate_spare(
            self.assignment.assignment_id,
            4,
            "JS",
            recorded_at_utc=NOW + timedelta(seconds=3),
        )

        snapshot = self.workflow.load_assignment(self.assignment.assignment_id)
        self.assertEqual(
            snapshot.spare_history,
            (designated_four, designated_five, removed_four),
        )
        self.assertEqual(snapshot.active_spares, (5,))
        with self.assertRaisesRegex(ValueError, "already designated"):
            self.workflow.designate_spare(
                self.assignment.assignment_id,
                5,
                "AT",
                recorded_at_utc=NOW + timedelta(seconds=4),
            )

    def test_replacement_history_isolated_when_switch_is_replaced(self):
        replacement = self.workflow.record_replacement(
            assignment_id=self.assignment.assignment_id,
            logical_channel=1,
            previous_physical_port=1,
            replacement_physical_port=4,
            reason="High loss",
            replaced_by="AT",
            replaced_at_utc=NOW + timedelta(seconds=1),
        )
        next_switch = self.repository.get_or_create(
            SwitchSpec("next-switch", "OSX-150", 5)
        )
        next_assignment = self.repository.replace_active(
            self.assignment.assignment_id,
            AssignmentSpec(
                self.unit.unit_id,
                next_switch.switch_id,
                NOW + timedelta(seconds=2),
                "AT",
                {1: 1, 2: 2},
            ),
            NOW + timedelta(seconds=2),
            "AT",
            "Switch failed",
        )

        old_snapshot = self.workflow.load_assignment(self.assignment.assignment_id)
        new_snapshot = self.workflow.load_assignment(next_assignment.assignment_id)
        self.assertEqual(old_snapshot.replacement_history, (replacement,))
        self.assertEqual(old_snapshot.effective_channel_map, {1: 4, 2: 2})
        self.assertEqual(new_snapshot.replacement_history, ())
        self.assertEqual(new_snapshot.effective_channel_map, {1: 1, 2: 2})
        with self.assertRaisesRegex(ValueError, "active assignment"):
            self.workflow.record_replacement(
                assignment_id=self.assignment.assignment_id,
                logical_channel=1,
                previous_physical_port=4,
                replacement_physical_port=5,
                reason="Too late",
                replaced_by="AT",
                replaced_at_utc=NOW + timedelta(seconds=3),
            )

    def test_editor_model_resolves_recommendation_against_effective_map(self):
        self.workflow.record_replacement(
            assignment_id=self.assignment.assignment_id,
            logical_channel=1,
            previous_physical_port=1,
            replacement_physical_port=4,
            reason="Initial replacement",
            replaced_by="AT",
            replaced_at_utc=NOW + timedelta(seconds=1),
        )
        snapshot = self.workflow.load_assignment(self.assignment.assignment_id)

        model = self.workflow.build_editor_model(
            snapshot=snapshot,
            related_run_id=self.run.run_id,
            recommendations=[
                {
                    "logical_channel": 1,
                    "current_physical_port": 1,
                    "candidate_physical_port": 5,
                    "candidate_loss_1310_db": 1.05,
                    "candidate_loss_1550_db": 1.15,
                    "candidate_worst_loss_db": 1.15,
                    "current_loss_1310_db": 2.40,
                    "current_loss_1550_db": 2.35,
                    "current_worst_loss_db": 2.40,
                    "category": "required",
                    "improvement_db": 1.25,
                }
            ],
            recommended_spares=[3],
            measured_physical_ports=[5],
            default_operator="AT",
        )

        recommendation = model.recommendations[0]
        self.assertEqual(recommendation.logical_channel, 1)
        self.assertEqual(recommendation.current_effective_physical_port, 4)
        self.assertEqual(recommendation.proposed_replacement_physical_port, 5)
        self.assertEqual(recommendation.category, "required")
        self.assertEqual(recommendation.improvement_db, 1.25)
        self.assertEqual(recommendation.default_reason, "")
        self.assertTrue(recommendation.has_measurement_evidence)
        self.assertEqual(recommendation.candidate_loss_1310_db, 1.05)
        self.assertEqual(recommendation.candidate_loss_1550_db, 1.15)
        self.assertEqual(recommendation.candidate_worst_loss_db, 1.15)
        self.assertEqual(recommendation.current_loss_1310_db, 2.40)
        self.assertEqual(recommendation.current_loss_1550_db, 2.35)
        self.assertEqual(recommendation.current_worst_loss_db, 2.40)
        self.assertEqual(model.default_operator, "AT")
        self.assertEqual(model.recommended_spares, (3,))

    def test_atomic_changes_derive_audit_fields_and_persist_notes(self):
        self.workflow.apply_changes(
            assignment_id=self.assignment.assignment_id,
            related_run_id=self.run.run_id,
            replacements=(
                ReplacementChangeRequest(
                    logical_channel=1,
                    replacement_physical_port=4,
                    reason="Formal insertion-loss failure",
                    replaced_by="JS",
                    notes="Rerouted at the front panel",
                ),
            ),
            spares_to_designate=(5,),
            spare_operator="JS",
            recorded_at_utc=NOW + timedelta(seconds=1),
        )

        snapshot = self.workflow.load_assignment(self.assignment.assignment_id)
        record = snapshot.replacement_history[0]
        self.assertEqual(record.assignment_id, self.assignment.assignment_id)
        self.assertEqual(record.related_run_id, self.run.run_id)
        self.assertEqual(record.previous_physical_port, 1)
        self.assertEqual(record.notes, "Rerouted at the front panel")
        self.assertEqual(record.replaced_at_utc, NOW + timedelta(seconds=1))
        self.assertEqual(snapshot.effective_channel_map[1], 4)
        self.assertEqual(snapshot.active_spares, (5,))

    def test_failed_atomic_changes_leave_no_partial_replacement(self):
        with self.assertRaisesRegex(ValueError, "already in use"):
            self.workflow.apply_changes(
                assignment_id=self.assignment.assignment_id,
                related_run_id=self.run.run_id,
                replacements=(
                    ReplacementChangeRequest(1, 4, "First", "AT"),
                    ReplacementChangeRequest(2, 4, "Conflict", "AT"),
                ),
                spare_operator="AT",
                recorded_at_utc=NOW + timedelta(seconds=1),
            )

        snapshot = self.workflow.load_assignment(self.assignment.assignment_id)
        self.assertEqual(snapshot.replacement_history, ())
        self.assertEqual(snapshot.effective_channel_map, {1: 1, 2: 2})

    def test_atomic_correction_or_reversal_appends_instead_of_deleting(self):
        first = self.workflow.apply_changes(
            assignment_id=self.assignment.assignment_id,
            related_run_id=self.run.run_id,
            replacements=(ReplacementChangeRequest(1, 4, "Initial", "AT"),),
            spare_operator="AT",
            recorded_at_utc=NOW + timedelta(seconds=1),
        )
        second = self.workflow.apply_changes(
            assignment_id=self.assignment.assignment_id,
            related_run_id=self.run.run_id,
            replacements=(
                ReplacementChangeRequest(1, 1, "Reversal to original port", "JS"),
            ),
            spare_operator="JS",
            recorded_at_utc=NOW + timedelta(seconds=2),
        )

        self.assertEqual(len(first.replacement_history), 1)
        self.assertEqual(len(second.replacement_history), 2)
        self.assertEqual(second.replacement_history[0].replacement_physical_port, 4)
        self.assertEqual(second.replacement_history[1].previous_physical_port, 4)
        self.assertEqual(second.replacement_history[1].replacement_physical_port, 1)
        self.assertEqual(second.effective_channel_map[1], 1)


if __name__ == "__main__":
    unittest.main()
