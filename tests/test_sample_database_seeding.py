import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from application.database_primary_workflow import DatabasePrimaryRunWorkflow
from application.sample_database_seeding import (
    SampleDatabaseSeeder,
    SampleScenarioError,
    load_scenario,
    scenario_summary,
)
from domain.coc_preparation import prepare_coc
from domain.limit_profiles import LimitProfile
from domain.replacements import ReplacementReading, analyze_replacements
from domain.run_status import (
    RESULT_COMPOSITE,
    RESULT_FAIL_RECOVERABLE,
    RESULT_SUPPLEMENTAL,
)
from infrastructure.database.memory_repositories import InMemoryRepositories


SCENARIO_ROOT = Path(__file__).resolve().parents[1] / "sample_data" / "scenarios"


class SampleDatabaseSeedingTests(unittest.TestCase):
    def _workflow(self):
        return DatabasePrimaryRunWorkflow(
            InMemoryRepositories(),
            readiness_check=lambda: SimpleNamespace(ready=True, operator_message="ready"),
        )

    def test_approved_scenarios_are_valid_and_deterministic(self):
        scenarios = tuple(load_scenario(path) for path in sorted(SCENARIO_ROOT.glob("*.json")))
        self.assertEqual(len(scenarios), 4)
        self.assertIn("SAMPLE-OSX150-3RUN-COMPOSITE", {item.scenario_id for item in scenarios})
        for scenario in scenarios:
            self.assertTrue(scenario.scenario_id.startswith("SAMPLE-"))
            self.assertEqual(scenario.run_uuid(scenario.runs[0]), scenario.run_uuid(scenario.runs[0]))
            self.assertGreater(scenario_summary(scenario)["measurements"], 0)
            self.assertEqual(scenario.station_number, 99)

    def test_seed_writes_two_runs_and_replacement_history(self):
        scenario = load_scenario(SCENARIO_ROOT / "osx150_two_run_optimization_engineering.json")
        workflow = self._workflow()
        result = SampleDatabaseSeeder(workflow).seed(scenario)
        self.assertEqual(result.action, "seeded")
        self.assertEqual(result.measurement_count, 38)
        self.assertEqual(result.replacement_count, 2)
        self.assertEqual(result.spare_count, 2)
        context = workflow.load_for_unit(scenario.unit.main_board_serial, 2)
        self.assertEqual(context.run.run_purpose, "engineering")
        self.assertEqual(context.run.analysis_status, "included")
        self.assertEqual(context.routing.effective_channel_map[9], 43)
        self.assertEqual(context.routing.effective_channel_map[20], 41)
        self.assertEqual(
            {item.channel: item.physical_port for item in context.snapshot.measurements}[9],
            43,
        )

    def test_coc_demo_combines_the_two_database_runs(self):
        scenario = load_scenario(SCENARIO_ROOT / "osx150_two_run_coc_demo.json")
        workflow = self._workflow()
        SampleDatabaseSeeder(workflow).seed(scenario)
        first = workflow.load_for_unit(scenario.unit.main_board_serial, 1)
        second = workflow.load_for_unit(scenario.unit.main_board_serial, 2)
        first_source = replace(
            first.snapshot.coc_source(),
            metadata={
                **first.snapshot.metadata,
                "Main board serial": scenario.unit.main_board_serial,
                "Switch serial": scenario.switch.switch_serial,
            },
        )
        second_source = replace(
            second.snapshot.coc_source(),
            metadata={
                **second.snapshot.metadata,
                "Main board serial": scenario.unit.main_board_serial,
                "Switch serial": scenario.switch.switch_serial,
            },
        )
        prepared = prepare_coc(
            first_source,
            36,
            supplemental_run=second_source,
            completed_replacements=(
                {"current_port": 9, "replacement_port": 43},
                {"current_port": 20, "replacement_port": 41},
            ),
            designated_spares=(37, 44),
        )
        self.assertTrue(prepared.eligible)
        self.assertEqual(len(prepared.channels), 36)
        self.assertEqual(prepared.overridden_channels[0].physical_port, 43)

    def test_three_run_composite_requires_all_runs(self):
        scenario = load_scenario(
            SCENARIO_ROOT / "osx150_three_run_composite.json"
        )
        self.assertEqual(scenario.unit.main_board_serial, "S-00001")
        self.assertEqual(scenario.switch.switch_serial, "S-00002")
        self.assertEqual(scenario.ilm_serial, "S-00003")
        self.assertEqual(scenario.station_number, 99)
        self.assertTrue(scenario.coc_combination_test)

        workflow = self._workflow()
        result = SampleDatabaseSeeder(workflow).seed(scenario)

        self.assertEqual(result.action, "seeded")
        self.assertEqual(len(result.run_ids), 3)
        self.assertEqual(result.measurement_count, 48)
        contexts = [
            workflow.load_for_unit(scenario.unit.main_board_serial, number)
            for number in (1, 2, 3)
        ]
        self.assertEqual(
            [len(context.snapshot.measurements) for context in contexts],
            [16, 16, 16],
        )
        self.assertEqual(
            [context.run.station_number for context in contexts],
            [99, 99, 99],
        )
        self.assertEqual(
            [context.snapshot.measurements[0].opm_wavelengths_nm for context in contexts],
            [(1310, 1550)] * 3,
        )

    def test_extra_port_scenario_is_ready_for_replacement_analysis(self):
        scenario = load_scenario(
            SCENARIO_ROOT / "osx150_extra_port_replacement_analysis.json"
        )
        self.assertEqual(scenario.unit.main_board_serial, "S-00004")
        self.assertEqual(scenario.switch.switch_serial, "S-00005")
        self.assertEqual(scenario.ilm_serial, "S-00006")
        self.assertEqual(scenario.unit.front_panel_channel_count, 48)
        self.assertEqual(scenario.switch.physical_channel_count, 56)
        self.assertEqual(scenario.replacements, ())
        self.assertEqual(scenario.spares, ())

        workflow = self._workflow()
        result = SampleDatabaseSeeder(workflow).seed(scenario)
        context = workflow.load_for_unit(scenario.unit.main_board_serial, 1)

        self.assertEqual(result.measurement_count, 56)
        self.assertEqual(result.replacement_count, 0)
        self.assertEqual(result.spare_count, 0)
        self.assertEqual(context.run.completion_status, "complete")
        measurements = context.snapshot.measurements
        self.assertEqual(len(measurements), 56)
        failures = {
            record.channel
            for record in measurements
            if record.channel <= 48 and max(record.ordered_losses) > 2.5
        }
        self.assertEqual(failures, {20, 21, 22, 23})
        extras = [record for record in measurements if record.channel > 48]
        self.assertEqual(
            [(record.channel, record.physical_port) for record in extras],
            [(port, port) for port in range(49, 57)],
        )
        self.assertTrue(
            all(max(record.ordered_losses) <= 2.25 for record in extras)
        )

        analysis = analyze_replacements(
            [record for record in measurements if record.channel <= 48],
            [
                ReplacementReading(
                    record.physical_port,
                    record.ordered_losses[0],
                    record.ordered_losses[1],
                )
                for record in extras
            ],
            48,
            2.25,
            0.2,
            fail_limit=2.5,
            model="OSX-150",
            too_good_limit=0.5,
        )
        self.assertEqual(
            {item["logical_channel"] for item in analysis["recommendations"]},
            {20, 21, 22, 23},
        )
        self.assertTrue(
            all(
                49 <= item["candidate_physical_port"] <= 56
                for item in analysis["recommendations"]
            )
        )
        projection = prepare_coc(context.snapshot.coc_source(), 48)
        status = context.snapshot.status(
            profile=LimitProfile.from_mapping(scenario.runs[0].limit_snapshot),
            planned_channels=range(1, 49),
            effective_result=projection,
            effective_run_numbers=projection.source_run_numbers,
        )
        self.assertFalse(projection.eligible)
        self.assertEqual(status.result_status, RESULT_FAIL_RECOVERABLE)

    def test_engineering_sample_runs_can_form_a_combined_coc(self):
        scenario = load_scenario(
            SCENARIO_ROOT / "osx150_two_run_optimization_engineering.json"
        )
        workflow = self._workflow()
        SampleDatabaseSeeder(workflow).seed(scenario)
        first = workflow.load_for_unit(scenario.unit.main_board_serial, 1)
        second = workflow.load_for_unit(scenario.unit.main_board_serial, 2)
        first_source = replace(
            first.snapshot.coc_source(),
            metadata={
                **first.snapshot.metadata,
                "Main board serial": scenario.unit.main_board_serial,
                "Switch serial": scenario.switch.switch_serial,
            },
        )
        second_source = replace(
            second.snapshot.coc_source(),
            metadata={
                **second.snapshot.metadata,
                "Main board serial": scenario.unit.main_board_serial,
                "Switch serial": scenario.switch.switch_serial,
            },
        )
        prepared = prepare_coc(
            first_source,
            36,
            supplemental_run=second_source,
            completed_replacements=(
                {"current_port": 9, "replacement_port": 43},
                {"current_port": 20, "replacement_port": 41},
            ),
            designated_spares=(37, 44),
        )
        self.assertTrue(prepared.eligible)
        self.assertEqual(prepared.base_run_number, 1)
        self.assertEqual(prepared.supplemental_run_number, 2)
        profile = LimitProfile.from_mapping(scenario.runs[0].limit_snapshot)
        base_status = first.snapshot.status(
            profile=profile,
            planned_channels=range(1, 37),
            composite_result=prepared,
            compatible_run_numbers=(2,),
        )
        supplemental_status = second.snapshot.status(
            profile=profile,
            planned_channels=(9, 20),
            composite_result=prepared,
            compatible_run_numbers=(1,),
        )
        self.assertEqual(base_status.result_status, RESULT_COMPOSITE)
        self.assertEqual(supplemental_status.result_status, RESULT_COMPOSITE)

    def test_seed_is_idempotent_and_partial_data_is_refused(self):
        scenario = load_scenario(SCENARIO_ROOT / "osx150_two_run_coc_demo.json")
        workflow = self._workflow()
        seeder = SampleDatabaseSeeder(workflow)
        first = seeder.seed(scenario)
        second = seeder.seed(scenario)
        self.assertEqual(first.action, "seeded")
        self.assertEqual(second.action, "no-op")

        other_values = __import__("json").loads(
            (SCENARIO_ROOT / "osx150_two_run_optimization_engineering.json").read_text(
                encoding="utf-8"
            )
        )
        other_values["scenario_id"] = "SAMPLE-CONFLICT"
        other_values["unit"]["main_board_serial"] = scenario.unit.main_board_serial
        other_values["switch"]["switch_serial"] = "SAMPLE-CONFLICT-SWITCH"
        from application.sample_database_seeding import SampleScenario

        other = SampleScenario.from_mapping(other_values)
        with self.assertRaises(SampleScenarioError):
            seeder.seed(other)

    def test_invalid_sample_identity_is_rejected(self):
        scenario_path = SCENARIO_ROOT / "osx150_two_run_optimization_engineering.json"
        values = __import__("json").loads(scenario_path.read_text(encoding="utf-8"))
        values["unit"]["main_board_serial"] = "REAL-UNIT-DO-NOT-USE"
        with self.assertRaises(SampleScenarioError):
            from application.sample_database_seeding import SampleScenario

            SampleScenario.from_mapping(values)


if __name__ == "__main__":
    unittest.main()
