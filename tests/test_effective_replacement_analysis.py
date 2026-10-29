import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from domain.database_records import (
    MEASUREMENT_ROLE_EXTRA_CANDIDATE,
    MeasurementRecord,
    ReplacementRecord,
    RunRecord,
    RunVoidInfo,
)
from domain.effective_replacement_analysis import (
    RESULT_FAIL_NO_VIABLE_RECOVERY,
    RESULT_INCOMPLETE_INPUT,
    RESULT_OPTIMIZED,
    RESULT_PASS_NO_VIABLE_OPTIMIZATION,
    RESULT_RECOMMENDATIONS_AVAILABLE,
    RESULT_REVIEW_REQUIRED,
    RESULT_VERIFICATION_REQUIRED,
    build_effective_replacement_projection,
)
from domain.limit_profiles import LimitProfile


START = datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc)


def profile():
    return LimitProfile(
        model="OSX-150",
        profile_name="OSX-150 SM",
        revision="1",
        too_good_below_db=0.5,
        warning_enabled=True,
        warning_above_db=2.25,
        fail_above_db=2.5,
        wavelength_mode="SM",
        minimum_replacement_improvement_db=0.2,
    ).validate()


def run(run_id, number, *, assignment=5, status="included", started=None):
    started = started or START + timedelta(hours=number)
    void_info = None
    if status == "excluded":
        void_info = RunVoidInfo(started, "AT", "Invalid reference")
    return RunRecord(
        run_id=run_id,
        assignment_id=assignment,
        run_number=number,
        client_run_uuid=uuid4(),
        run_started_at_utc=started,
        tested_by="AT",
        wavelength_mode="SM",
        operating_band="O band",
        application_version="test",
        measurement_hardware={},
        limit_snapshot=profile().as_dict(),
        completion_status="complete",
        run_ended_at_utc=started + timedelta(minutes=30),
        analysis_status=status,
        void_info=void_info,
        front_panel_channel_count=2,
    )


def measurement(mid, source_run, logical, physical, loss, *, minute=1):
    extra = int(logical) > int(source_run.front_panel_channel_count)
    return MeasurementRecord(
        measurement_id=mid,
        measurement_uuid=uuid4(),
        run_id=source_run.run_id,
        logical_channel=None if extra else logical,
        physical_port=physical,
        attempt_number=1,
        wavelength_1_nm=1310,
        wavelength_1_il_db=Decimal(str(loss)),
        wavelength_2_nm=1550,
        wavelength_2_il_db=Decimal(str(loss + 0.01)),
        reference_snapshot={"reference_id": "ref-1"},
        written_at_utc=source_run.run_started_at_utc + timedelta(minutes=minute),
        written_by="AT",
        measurement_role=(
            MEASUREMENT_ROLE_EXTRA_CANDIDATE if extra else "logical_channel"
        ),
    )


class EffectiveReplacementProjectionTests(unittest.TestCase):
    def project(self, context, runs, rows, mapping=None, replacements=()):
        return build_effective_replacement_projection(
            context_run=context,
            runs=runs,
            measurements_by_run={
                item.run_id: tuple(row for row in rows if row.run_id == item.run_id)
                for item in runs
            },
            effective_channel_map=mapping or {1: 1, 2: 2},
            replacements=replacements,
            active_spares=(),
            spare_event_ids=(),
            profile=profile(),
        )

    def test_newest_failure_overrides_older_pass_and_extras_carry_forward(self):
        first = run(1, 1)
        second = run(2, 2)
        rows = (
            measurement(1, first, 1, 1, 1.0),
            measurement(2, first, 2, 2, 1.0),
            measurement(3, first, 3, 3, 1.2),
            measurement(4, second, 2, 2, 2.7),
        )
        result = self.project(second, (first, second), rows)
        self.assertEqual(
            result.analysis_result["result_status"],
            RESULT_RECOMMENDATIONS_AVAILABLE,
        )
        selected = {item.record.logical_channel: item for item in result.front_measurements}
        self.assertEqual(selected[2].record.measurement_id, 4)
        self.assertEqual(result.extra_measurements[0].record.measurement_id, 3)
        self.assertEqual(result.analysis_result["recommendations"][0]["logical_channel"], 2)

    def test_assignment_void_and_future_runs_are_isolated(self):
        context = run(10, 2)
        old_assignment = run(11, 1, assignment=4)
        voided = run(12, 1, status="excluded")
        future = run(13, 3)
        rows = (
            measurement(1, context, 1, 1, 1.0),
            measurement(2, context, 2, 2, 2.7),
            measurement(3, old_assignment, 3, 3, 0.9),
            measurement(4, voided, 3, 3, 0.8),
            measurement(5, future, 3, 3, 0.7),
        )
        result = self.project(context, (old_assignment, voided, context, future), rows)
        self.assertFalse(result.extra_measurements)
        self.assertEqual(
            result.analysis_result["result_status"], RESULT_FAIL_NO_VIABLE_RECOVERY
        )
        reasons = {reason for _run, reason in result.excluded_runs}
        self.assertIn("different assignment", reasons)
        self.assertIn("voided", reasons)
        self.assertIn("later than context run", reasons)

    def test_replacement_requires_post_replacement_matching_measurement(self):
        first = run(1, 1)
        replacement_time = first.run_ended_at_utc + timedelta(minutes=1)
        replacement = ReplacementRecord(
            replacement_id=7,
            assignment_id=5,
            logical_channel=2,
            previous_physical_port=2,
            replacement_physical_port=3,
            reason="High loss",
            replaced_by="AT",
            replaced_at_utc=replacement_time,
            related_run_id=first.run_id,
        )
        rows = (
            measurement(1, first, 1, 1, 1.0),
            measurement(2, first, 2, 2, 2.7),
            measurement(3, first, 3, 3, 1.0),
        )
        waiting = self.project(
            first, (first,), rows, mapping={1: 1, 2: 2}, replacements=(replacement,)
        )
        self.assertEqual(
            waiting.analysis_result["result_status"], RESULT_VERIFICATION_REQUIRED
        )
        self.assertEqual(waiting.verifications[-1].state, "awaiting_retest")

        second = run(2, 2)
        retest = measurement(4, second, 2, 3, 1.1)
        verified = self.project(
            second,
            (first, second),
            rows + (retest,),
            mapping={1: 1, 2: 2},
            replacements=(replacement,),
        )
        self.assertEqual(verified.verifications[-1].state, "verified_passing")
        self.assertEqual(verified.analysis_result["result_status"], RESULT_OPTIMIZED)
        self.assertNotIn(3, [item.record.physical_port for item in verified.extra_measurements])

    def test_too_good_front_panel_measurement_requires_review(self):
        context = run(1, 1)
        rows = (
            measurement(1, context, 1, 1, 0.3),
            measurement(2, context, 2, 2, 1.0),
        )

        result = self.project(context, (context,), rows)

        self.assertEqual(
            result.analysis_result["result_status"], RESULT_REVIEW_REQUIRED
        )
        self.assertIn("Too-good front-panel", result.review_issues[-1])

    def test_warning_without_candidate_passes_without_viable_optimization(self):
        context = run(1, 1)
        rows = (
            measurement(1, context, 1, 1, 2.3),
            measurement(2, context, 2, 2, 1.0),
        )

        result = self.project(context, (context,), rows)

        self.assertEqual(
            result.analysis_result["result_status"],
            RESULT_PASS_NO_VIABLE_OPTIMIZATION,
        )

    def test_missing_required_channel_is_incomplete(self):
        context = run(1, 1)

        result = self.project(
            context,
            (context,),
            (measurement(1, context, 1, 1, 1.0),),
        )

        self.assertEqual(
            result.analysis_result["result_status"], RESULT_INCOMPLETE_INPUT
        )
        self.assertEqual(result.missing_channels, (2,))

    def test_verification_states_follow_latest_post_replacement_measurement(self):
        first = run(1, 1)
        second = run(2, 2)
        replacement = ReplacementRecord(
            replacement_id=7,
            assignment_id=5,
            logical_channel=2,
            previous_physical_port=2,
            replacement_physical_port=3,
            reason="High loss",
            replaced_by="AT",
            replaced_at_utc=first.run_ended_at_utc + timedelta(minutes=1),
            related_run_id=first.run_id,
        )
        base_rows = (
            measurement(1, first, 1, 1, 1.0),
            measurement(2, first, 2, 2, 2.7),
            measurement(3, first, 3, 3, 1.0),
        )
        cases = (
            (2.3, "verified_optimization_warning", RESULT_PASS_NO_VIABLE_OPTIMIZATION),
            (2.7, "verified_failing", RESULT_FAIL_NO_VIABLE_RECOVERY),
            (0.3, "invalid_retest", RESULT_REVIEW_REQUIRED),
        )
        for offset, (loss, state, expected_status) in enumerate(cases, start=4):
            with self.subTest(state=state):
                retest = measurement(offset, second, 2, 3, loss)
                result = self.project(
                    second,
                    (first, second),
                    base_rows + (retest,),
                    replacements=(replacement,),
                )
                self.assertEqual(result.verifications[-1].state, state)
                self.assertEqual(
                    result.analysis_result["result_status"], expected_status
                )

    def test_repeated_replacement_chain_keeps_history_and_uses_latest_mapping(self):
        first = run(1, 1)
        second = run(2, 2)
        third = run(3, 3)
        first_change = ReplacementRecord(
            replacement_id=7,
            assignment_id=5,
            logical_channel=2,
            previous_physical_port=2,
            replacement_physical_port=3,
            reason="First replacement",
            replaced_by="AT",
            replaced_at_utc=first.run_ended_at_utc + timedelta(minutes=1),
            related_run_id=first.run_id,
        )
        second_change = ReplacementRecord(
            replacement_id=8,
            assignment_id=5,
            logical_channel=2,
            previous_physical_port=3,
            replacement_physical_port=4,
            reason="Replacement changed again",
            replaced_by="AT",
            replaced_at_utc=second.run_ended_at_utc + timedelta(minutes=1),
            related_run_id=second.run_id,
        )
        rows = (
            measurement(1, first, 1, 1, 1.0),
            measurement(2, first, 2, 2, 2.7),
            measurement(3, second, 2, 3, 2.4),
            measurement(4, third, 2, 4, 1.0),
        )

        result = self.project(
            third,
            (first, second, third),
            rows,
            replacements=(first_change, second_change),
        )

        self.assertEqual(
            [item.state for item in result.verifications],
            ["superseded_by_later_replacement", "verified_passing"],
        )
        selected = {item.record.logical_channel: item for item in result.front_measurements}
        self.assertEqual(selected[2].record.physical_port, 4)
        self.assertEqual(result.analysis_result["result_status"], RESULT_OPTIMIZED)

    def test_replacement_after_context_does_not_change_historical_mapping(self):
        context = run(1, 1)
        later = run(2, 2)
        replacement = ReplacementRecord(
            replacement_id=8,
            assignment_id=5,
            logical_channel=2,
            previous_physical_port=2,
            replacement_physical_port=3,
            reason="Later replacement",
            replaced_by="AT",
            replaced_at_utc=later.run_started_at_utc + timedelta(minutes=5),
            related_run_id=later.run_id,
        )
        rows = (
            measurement(1, context, 1, 1, 1.0),
            measurement(2, context, 2, 2, 1.1),
        )

        result = self.project(
            context,
            (context, later),
            rows,
            mapping={1: 1, 2: 2},
            replacements=(replacement,),
        )

        self.assertEqual(result.analysis_result["result_status"], RESULT_OPTIMIZED)
        self.assertEqual(
            {item.record.logical_channel: item.record.physical_port
             for item in result.front_measurements},
            {1: 1, 2: 2},
        )
        self.assertFalse(result.verifications)

    def test_source_fingerprint_is_deterministic(self):
        context = run(1, 1)
        rows = (
            measurement(1, context, 1, 1, 1.0),
            measurement(2, context, 2, 2, 1.1),
        )
        first = self.project(context, (context,), rows)
        second = self.project(context, (context,), rows)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(len(first.fingerprint), 64)

    def test_source_snapshot_includes_superseded_attempts(self):
        context = run(1, 1)
        rows = (
            measurement(1, context, 1, 1, 1.2, minute=1),
            measurement(2, context, 1, 1, 1.0, minute=2),
            measurement(3, context, 2, 2, 1.1, minute=3),
        )

        result = self.project(context, (context,), rows)

        self.assertEqual(
            result.source_snapshot["considered_measurement_ids"], [1, 2, 3]
        )
        self.assertEqual(result.source_snapshot["selected_measurement_ids"], [2, 3])
        self.assertEqual(result.source_snapshot["accepted_measurement_count"], 3)
        self.assertEqual(result.source_snapshot["measurement_high_watermark_id"], 3)


if __name__ == "__main__":
    unittest.main()
