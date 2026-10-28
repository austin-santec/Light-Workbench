import unittest
from datetime import datetime, timedelta, timezone

from application.unit_switch_workflow import (
    AssignmentResolution,
    UnitSwitchAssignmentWorkflow,
)
from domain.database_records import SwitchSpec, UnitSpec
from domain.unit_switch_assignments import (
    AssignmentChangeRequiredError,
    SwitchAlreadyAssignedError,
    validate_initial_channel_map,
)
from infrastructure.database.memory_repositories import InMemoryRepositories


NOW = datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc)


def identity_map(count):
    return {channel: channel for channel in range(1, count + 1)}


class UnitSwitchAssignmentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryRepositories()
        self.workflow = UnitSwitchAssignmentWorkflow(
            self.store, self.store, self.store
        )
        self.unit = UnitSpec(
            "unit-1",
            "OSX-150-1A-048-09-FA-00B-3H",
            48,
            "OSX-150",
        )
        self.switch = SwitchSpec("switch-1", "OSX-150", 51)

    def test_new_installation_then_reconnection_reuses_assignment(self):
        first = self.workflow.resolve(
            self.unit,
            self.switch,
            installed_at_utc=NOW,
            installed_by="AT",
            initial_channel_map=identity_map(48),
        )
        second = self.workflow.resolve(
            self.unit,
            self.switch,
            installed_at_utc=NOW + timedelta(minutes=1),
            installed_by="AT",
            initial_channel_map=identity_map(48),
        )
        self.assertEqual(first.resolution, AssignmentResolution.INSTALLED)
        self.assertEqual(second.resolution, AssignmentResolution.REUSED)
        self.assertEqual(second.assignment.assignment_id, first.assignment.assignment_id)
        self.assertEqual(len(self.store.history_for_unit(first.unit.unit_id)), 1)

    def test_different_switch_requires_explicit_replacement(self):
        self.workflow.resolve(
            self.unit,
            self.switch,
            installed_at_utc=NOW,
            installed_by="AT",
            initial_channel_map=identity_map(48),
        )
        with self.assertRaises(AssignmentChangeRequiredError):
            self.workflow.resolve(
                self.unit,
                SwitchSpec("switch-2", "OSX-150", 51),
                installed_at_utc=NOW + timedelta(minutes=1),
                installed_by="AT",
                initial_channel_map=identity_map(48),
            )

    def test_replacement_closes_old_assignment_and_preserves_history(self):
        original = self.workflow.resolve(
            self.unit,
            self.switch,
            installed_at_utc=NOW,
            installed_by="AT",
            initial_channel_map=identity_map(48),
        )
        changed = self.workflow.replace_switch(
            self.unit,
            SwitchSpec("switch-2", "OSX-150", 51),
            changed_at_utc=NOW + timedelta(hours=1),
            changed_by="AT",
            removal_reason="Failed switch",
            initial_channel_map=identity_map(48),
        )
        history = self.store.history_for_unit(original.unit.unit_id)
        self.assertEqual(changed.resolution, AssignmentResolution.REPLACED)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].removal_reason, "Failed switch")
        self.assertEqual(history[1], changed.assignment)

    def test_switch_cannot_be_active_in_two_units(self):
        self.workflow.resolve(
            self.unit,
            self.switch,
            installed_at_utc=NOW,
            installed_by="AT",
            initial_channel_map=identity_map(48),
        )
        with self.assertRaises(SwitchAlreadyAssignedError):
            self.workflow.resolve(
                UnitSpec("unit-2", front_panel_channel_count=48),
                self.switch,
                installed_at_utc=NOW,
                installed_by="AT",
                initial_channel_map=identity_map(48),
            )

    def test_failed_replacement_keeps_original_assignment_active(self):
        first = self.workflow.resolve(
            self.unit,
            self.switch,
            installed_at_utc=NOW,
            installed_by="AT",
            initial_channel_map=identity_map(48),
        )
        occupied_switch = SwitchSpec("switch-occupied", "OSX-150", 51)
        self.workflow.resolve(
            UnitSpec("unit-2", front_panel_channel_count=48),
            occupied_switch,
            installed_at_utc=NOW,
            installed_by="AT",
            initial_channel_map=identity_map(48),
        )
        with self.assertRaises(SwitchAlreadyAssignedError):
            self.workflow.replace_switch(
                self.unit,
                occupied_switch,
                changed_at_utc=NOW + timedelta(hours=1),
                changed_by="AT",
                removal_reason="Failed switch",
                initial_channel_map=identity_map(48),
            )
        self.assertEqual(self.store.get_active(first.unit.unit_id), first.assignment)

    def test_front_panel_count_and_physical_capacity_remain_distinct(self):
        channel_map = identity_map(48)
        channel_map[48] = 51
        result = validate_initial_channel_map(
            channel_map,
            front_panel_channel_count=48,
            scpi_configured_channel_count=51,
        )
        self.assertEqual(len(result), 48)
        self.assertEqual(result[48], 51)

    def test_invalid_baseline_maps_are_rejected(self):
        cases = (
            (identity_map(47), "incomplete"),
            ({**identity_map(48), 48: 47}, "unique"),
            ({**identity_map(48), 48: 52}, "exceed"),
        )
        for channel_map, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_initial_channel_map(
                        channel_map,
                        front_panel_channel_count=48,
                        scpi_configured_channel_count=51,
                    )


if __name__ == "__main__":
    unittest.main()
