import tempfile
import unittest
from pathlib import Path

from domain.limit_profiles import default_limit_profiles
from domain.models import MeasurementRecord
from domain.run_status import (
    COMPLETION_COMPLETE,
    COMPLETION_INCOMPLETE,
    COMPLETION_IN_PROGRESS,
    COMPLETION_INTERRUPTED,
    COMPLETION_UNKNOWN,
    RESULT_COMPOSITE,
    RESULT_FAIL_RECOVERABLE,
    RESULT_FAIL_UNRECOVERABLE,
    RESULT_NOT_EVALUATED,
    RESULT_PASS,
    RESULT_PASS_OPTIMIZATION,
    RESULT_PASS_REVIEW,
    RESULT_REVIEW,
    RESULT_SUPPLEMENTAL,
    assess_run_status,
)
from infrastructure.run_persistence import RunRecorder, load_run_json


PROFILE = default_limit_profiles().for_model_mode("OSX-150", "SM")


def records(values):
    return [MeasurementRecord(channel, first, second, channel) for channel, first, second in values]


class RunStatusTests(unittest.TestCase):
    def test_active_partial_run_is_in_progress(self):
        status = assess_run_status(
            records([(1, 1.0, 1.1)]),
            planned_channels=(1, 2, 3),
            active=True,
            profile=PROFILE,
            front_panel_channel_count=3,
        )
        self.assertEqual(status.completion_status, COMPLETION_IN_PROGRESS)
        self.assertEqual(status.completed_channel_count, 1)
        self.assertEqual(status.result_status, RESULT_NOT_EVALUATED)
        self.assertEqual(status.missing_channels, (2, 3))

    def test_complete_passing_run_is_pass(self):
        status = assess_run_status(
            records([(1, 1.0, 1.1), (2, 1.2, 1.3)]),
            planned_channels=(1, 2),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=2,
        )
        self.assertEqual(status.completion_status, COMPLETION_COMPLETE)
        self.assertEqual(status.result_status, RESULT_PASS)
        self.assertNotIn("COC creation is available.", status.tooltip())

    def test_extra_candidate_is_not_required_for_front_panel_completion(self):
        status = assess_run_status(
            records([(1, 1.0, 1.1), (49, 0.4, 0.5)]),
            planned_channels=(1,),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=1,
        )
        self.assertEqual(status.completion_status, COMPLETION_COMPLETE)
        self.assertEqual(status.completed_channel_count, 1)
        self.assertEqual(status.result_status, RESULT_PASS)

    def test_optimization_and_failure_recovery_are_distinct(self):
        optimized = assess_run_status(
            records([(1, 2.3, 1.0)]),
            planned_channels=(1,),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=1,
            replacement_analysis={"recommendations": [{"logical_channel": 1}]},
        )
        self.assertEqual(optimized.result_status, RESULT_PASS_OPTIMIZATION)

        review = assess_run_status(
            records([(1, 2.3, 1.0)]),
            planned_channels=(1,),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=1,
        )
        self.assertEqual(review.result_status, RESULT_PASS_REVIEW)

        recoverable = assess_run_status(
            records([(1, 2.6, 1.0)]),
            planned_channels=(1,),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=1,
            replacement_analysis={"recommendations": [{"logical_channel": 1}]},
        )
        self.assertEqual(recoverable.result_status, RESULT_FAIL_RECOVERABLE)

        unrecoverable = assess_run_status(
            records([(1, 2.6, 1.0)]),
            planned_channels=(1,),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=1,
        )
        self.assertEqual(unrecoverable.result_status, RESULT_FAIL_UNRECOVERABLE)

    def test_partial_complete_run_reports_composite_pass_when_composite_is_valid(self):
        class Composite:
            eligible = True

        status = assess_run_status(
            records([(1, 1.0, 1.1)]),
            planned_channels=(1,),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=2,
            composite_result=Composite(),
            compatible_run_numbers=(2,),
        )
        self.assertEqual(status.completion_status, COMPLETION_COMPLETE)
        self.assertEqual(status.result_status, RESULT_COMPOSITE)
        self.assertEqual(status.compatible_run_numbers, (2,))
        self.assertIn("partial run", status.detail)
        self.assertIn("Run 2", status.detail)
        self.assertIn("COC creation is available.", status.tooltip())

    def test_partial_run_reports_composite_pass_for_effective_multi_run_projection(self):
        class EffectiveProjection:
            invalid_readings = ()
            validation_issues = ()
            missing_channels = ()
            failures = ()
            optimization_channels = ()
            optimization_recommendations = ()

        status = assess_run_status(
            records([(1, 1.0, 1.1)]),
            planned_channels=(1,),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=2,
            effective_result=EffectiveProjection(),
            effective_run_numbers=(1, 2, 3),
            compatible_run_numbers=(2, 3),
        )
        self.assertEqual(status.result_status, RESULT_COMPOSITE)
        self.assertIn("Runs 1, 2, 3", status.detail)

    def test_effective_projection_reports_measured_recovery_for_failures(self):
        class EffectiveProjection:
            invalid_readings = ()
            validation_issues = ()
            missing_channels = ()
            failures = (object(),)
            optimization_channels = ()
            optimization_recommendations = ({"logical_channel": 1},)

        status = assess_run_status(
            records([(1, 2.6, 1.0)]),
            planned_channels=(1,),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=1,
            effective_result=EffectiveProjection(),
            effective_run_numbers=(1,),
        )

        self.assertEqual(status.result_status, RESULT_FAIL_RECOVERABLE)
        self.assertIn("possible recovery path", status.detail)

    def test_full_run_can_have_a_composite_pass(self):
        class Composite:
            eligible = True

        status = assess_run_status(
            records([(1, 2.6, 1.0), (2, 1.0, 1.0)]),
            planned_channels=(1, 2),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=2,
            composite_result=Composite(),
            compatible_run_numbers=(2,),
        )
        self.assertEqual(status.result_status, RESULT_COMPOSITE)

    def test_invalid_readings_require_review(self):
        status = assess_run_status(
            records([(1, -0.1, 1.0)]),
            planned_channels=(1,),
            terminal_status=COMPLETION_COMPLETE,
            profile=PROFILE,
            front_panel_channel_count=1,
        )
        self.assertEqual(status.result_status, RESULT_REVIEW)

    def test_stop_and_failure_are_different_completion_states(self):
        stopped = assess_run_status(
            records([(1, 1.0, 1.0)]),
            planned_channels=(1, 2),
            terminal_status=COMPLETION_INCOMPLETE,
        )
        failed = assess_run_status(
            records([(1, 1.0, 1.0)]),
            planned_channels=(1, 2),
            terminal_status=COMPLETION_INTERRUPTED,
        )
        self.assertEqual(stopped.completion_status, COMPLETION_INCOMPLETE)
        self.assertEqual(failed.completion_status, COMPLETION_INTERRUPTED)

    def test_legacy_without_a_saved_plan_is_unknown(self):
        status = assess_run_status(records([(1, 1.0, 1.0)]), legacy=True)
        self.assertEqual(status.completion_status, COMPLETION_UNKNOWN)

    def test_run_status_round_trips_in_json(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = RunRecorder(
                directory=Path(directory) / "Run-1",
                metadata={
                    "Run number": "1",
                    "Main board serial": "MB1",
                    "Planned channel count": "2",
                    "planned_channel_count": "2",
                    "completion_status": COMPLETION_COMPLETE,
                    "completion_reason": "Every planned channel has an accepted reading.",
                    "completed_channel_count": "2",
                    "completed_at_utc": "2026-10-13T12:00:00Z",
                },
                criteria_snapshot=PROFILE.as_dict(),
            )
            recorder.save(records([(1, 1.0, 1.0), (2, 1.0, 1.0)]))
            payload = load_run_json(recorder.json_path)

        self.assertEqual(payload["run_status"]["completion_status"], COMPLETION_COMPLETE)
        self.assertEqual(payload["run_status"]["planned_channel_count"], 2)
        self.assertEqual(payload["run_status"]["completed_channel_count"], 2)


if __name__ == "__main__":
    unittest.main()
