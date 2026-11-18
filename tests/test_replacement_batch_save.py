"""Recommendation-linked batches must use one source state for the whole save."""

from dataclasses import replace
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import unittest
from uuid import uuid4

from application.replacement_analysis_persistence import ReplacementAnalysisPersistenceWorkflow
from domain.database_records import (
    AssignmentSpec, MeasurementSpec, MEASUREMENT_ROLE_EXTRA_CANDIDATE,
    ReplacementRecord, ReplacementSpec, RunSpec, SpareEventSpec, SwitchSpec, UnitSpec,
)
from infrastructure.database.memory_repositories import InMemoryRepositories
from infrastructure.database.sql_repositories import SqlRepositories


NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)


def make_batch_fixture():
    repository = InMemoryRepositories()
    unit = repository.get_or_create(UnitSpec("BATCH-TEST", front_panel_channel_count=36))
    switch = repository.get_or_create(SwitchSpec("BATCH-SWITCH", "OSX-150", 36))
    assignment = repository.install(AssignmentSpec(
        unit.unit_id, switch.switch_id, NOW, "AT", {ch: ch for ch in range(1, 37)}
    ))
    run = repository.create(RunSpec(
        assignment.assignment_id, 1, uuid4(), NOW, "AT", "SM", "O band", "test",
        front_panel_channel_count=36,
    ))
    pairs = ((4, 40), (8, 37), (12, 38), (2, 39))
    for channel in range(1, 41):
        is_extra = channel > 36
        loss = "2.8" if channel in {ch for ch, _port in pairs} else "1.0"
        repository.append_attempt(MeasurementSpec(
            uuid4(), run.run_id, None if is_extra else channel, 1,
            1310, Decimal(loss), 1550, Decimal(loss), {"snapshot_id": "test"},
            NOW, "AT", channel,
            MEASUREMENT_ROLE_EXTRA_CANDIDATE if is_extra else "logical_channel",
        ))
    repository.finish(run.run_id, "complete", NOW + timedelta(minutes=1))
    run = repository.get(run.run_id)
    ids = sorted(repository.measurements)
    result = {
        "applicable": True, "status": "Performed", "designed_channel_count": 36,
        "extra_ports": [37, 38, 39, 40], "bottom_spares": [],
        "recommendations": [
            {
                "logical_channel": channel, "category": "required",
                "current_physical_port": channel, "candidate_physical_port": port,
                "current_loss_1310_db": 2.8, "current_loss_1550_db": 2.8,
                "candidate_loss_1310_db": 1.0, "candidate_loss_1550_db": 1.0,
                "current_worst_loss_db": 2.8, "candidate_worst_loss_db": 1.0,
                "improvement_db": 1.8,
                "current_measurement_id": channel, "candidate_measurement_id": port,
            } for channel, port in pairs
        ],
        "source_snapshot": {
            "assignment_id": assignment.assignment_id, "context_run_id": run.run_id,
            "included_run_ids": [run.run_id],
            "included_run_states": [{
                "run_id": run.run_id, "analysis_status": run.analysis_status,
                "superseded_by_run_id": run.superseded_by_run_id,
            }],
            "considered_measurement_ids": ids, "measurement_high_watermark_id": max(ids),
            "replacement_ids": [], "spare_event_ids": [],
            "state_fingerprint_sha256": "a" * 64,
        },
    }
    saved = ReplacementAnalysisPersistenceWorkflow(repository).save_result(
        run_id=run.run_id, result=result, analyzed_by="AT", application_version="test",
        front_panel_channel_count=36, wavelengths=(1310, 1550),
        criteria={"model": "OSX-150"}, measurement_count=40,
    )
    specs = tuple(ReplacementSpec(
        assignment.assignment_id, item.logical_channel, item.current_physical_port,
        item.candidate_physical_port, "High loss", "AT", NOW + timedelta(minutes=2),
        related_run_id=run.run_id, source_recommendation_id=item.recommendation_id,
    ) for item in saved.recommendations)
    return repository, run, specs


class ReplacementBatchSaveTests(unittest.TestCase):
    def setUp(self):
        self.repository, self.run, self.specs = make_batch_fixture()

    def test_four_fresh_recommendations_save_together_and_keep_links(self):
        self.repository.apply_routing_changes(self.specs, ())
        saved = self.repository.replacement_history_for_assignment(self.run.assignment_id)
        self.assertEqual(len(saved), 4)
        self.assertEqual(
            {r.logical_channel: r.replacement_physical_port for r in saved},
            {4: 40, 8: 37, 12: 38, 2: 39},
        )
        self.assertEqual(
            {r.source_recommendation_id for r in saved},
            {s.source_recommendation_id for s in self.specs},
        )

    def test_a_new_measurement_rejects_the_batch_without_partial_changes(self):
        self.repository.resume(self.run.run_id)
        self.repository.append_attempt(MeasurementSpec(
            uuid4(), self.run.run_id, 4, 2, 1310, Decimal("2.9"),
            1550, Decimal("2.9"), {"snapshot_id": "new"}, NOW, "AT", 4,
        ))
        with self.assertRaisesRegex(ValueError, "recommendation is stale"):
            self.repository.apply_routing_changes(self.specs, ())
        self.assertEqual(self.repository.replacements, {})

    def test_a_changed_spare_history_is_still_rejected(self):
        self.repository.append_event(SpareEventSpec(
            self.run.assignment_id, 40, "designated", "AT", NOW
        ))
        with self.assertRaisesRegex(ValueError, "recommendation is stale"):
            self.repository.apply_routing_changes(self.specs, ())
        self.assertEqual(self.repository.replacements, {})
        self.assertEqual(len(self.repository.spare_events), 1)

    def test_invalid_later_candidate_rolls_back_the_entire_batch(self):
        specs = (self.specs[0], replace(self.specs[1], replacement_physical_port=38))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.repository.apply_routing_changes(specs, ())
        self.assertEqual(self.repository.replacements, {})

    def test_a_preexisting_replacement_invalidates_the_old_snapshot(self):
        self.repository.append(replace(self.specs[0], source_recommendation_id=None))
        with self.assertRaisesRegex(ValueError, "replacements are no longer current"):
            self.repository.apply_routing_changes(self.specs[1:], ())
        self.assertEqual(len(self.repository.replacements), 1)

    def test_successful_batch_makes_original_analysis_stale_for_later_saves(self):
        self.repository.apply_routing_changes(self.specs, ())
        with self.assertRaisesRegex(ValueError, "recommendation is stale"):
            self.repository.apply_routing_changes(self.specs, ())
        self.assertEqual(len(self.repository.replacements), 4)


class SqlBatchCursor:
    """Stateful DB-API fake: run the real SQL orchestration and validators."""

    def __init__(self, factory):
        self.factory = factory
        self.rows = []

    def execute(self, sql, *args):
        sql = " ".join(sql.split())
        self.factory.calls.append((sql, args))
        memory = self.factory.memory
        self.rows = []
        if "FROM dbo.REPLACEMENT_ANALYSIS_RECOMMENDATIONS" in sql:
            rec = memory.replacement_analysis_recommendations.get(args[0])
            if rec is not None:
                analysis = memory.replacement_analyses[rec.analysis_id]
                details = json.dumps(dict(analysis.result_details))
                if sql.startswith("SELECT analysis.run_id"):
                    self.rows = [(
                        analysis.run_id, memory.runs[analysis.run_id].assignment_id,
                        analysis.source_measurement_high_watermark_id, details,
                    )]
                else:
                    self.rows = [(
                        rec.analysis_id, rec.logical_channel, rec.candidate_physical_port,
                        analysis.run_id, analysis.source_measurement_high_watermark_id,
                        rec.candidate_measurement_id, details,
                    )]
        elif sql.startswith("SELECT run_id, assignment_id"):
            self.rows = [(r.run_id, r.assignment_id, r.analysis_status, r.superseded_by_run_id)
                         for r in memory.runs.values() if r.run_id in args]
        elif sql.startswith("SELECT assignment_id FROM dbo.IL_RUNS"):
            run = memory.runs.get(args[0])
            self.rows = [(run.assignment_id,)] if run else []
        elif sql.startswith("SELECT measurement_id FROM dbo.IL_MEASUREMENTS"):
            self.rows = [(m.measurement_id,) for m in memory.measurements.values() if m.run_id in args]
        elif sql.startswith("SELECT replacement_id FROM dbo.CHANNEL_REPLACEMENTS"):
            self.rows = [(r.replacement_id,) for r in memory.replacements.values()
                         if r.assignment_id == args[0]
                         and (r.related_run_id is None or r.related_run_id in args[1:])]
        elif sql.startswith("SELECT spare_event_id"):
            self.rows = [(s.spare_event_id,) for s in memory.spare_events.values() if s.assignment_id == args[0]]
        elif "FROM dbo.vw_ConfirmedExtraPorts" in sql:
            self.rows = [(r.measurement.measurement_id,)
                         for r in memory.confirmed_extra_ports_for_assignment(args[0])
                         if r.physical_port == args[1]]
        elif "WHERE source_recommendation_id = ?" in sql:
            self.rows = [(1,) for r in memory.replacements.values() if r.source_recommendation_id == args[0]]
        elif sql.startswith("SELECT TOP (1) replaced_at_utc"):
            self.rows = [(r.replaced_at_utc,) for r in reversed(tuple(memory.replacements.values()))
                         if (r.assignment_id, r.logical_channel) == args]
        elif sql.startswith("INSERT INTO dbo.CHANNEL_REPLACEMENTS"):
            self.factory.insert_count += 1
            if self.factory.insert_count == self.factory.fail_insert:
                raise RuntimeError("Injected insert failure")
            record = ReplacementRecord(memory._next("replacement"), *args)
            memory.replacements[record.replacement_id] = record
            self.rows = [(record.replacement_id,)]
        elif "WHERE replacement.replacement_id = ?" in sql:
            self.rows = [memory.replacements[args[0]]]
        else:
            raise AssertionError(sql)
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class SqlBatchFactory:
    def __init__(self, memory):
        self.memory = memory
        self.calls = []
        self.insert_count = 0
        self.fail_insert = None
        self.commits = 0
        self.rollbacks = 0

    @contextmanager
    def transaction(self):
        before = dict(self.memory.replacements), dict(self.memory.spare_events), dict(self.memory._next_ids)
        try:
            yield SqlBatchCursor(self)
        except Exception:
            self.memory.replacements, self.memory.spare_events, self.memory._next_ids = before
            self.rollbacks += 1
            raise
        else:
            self.commits += 1


class SqlBatchRepository(SqlRepositories):
    def _routing_context(self, cursor, assignment_id, **kwargs):
        assignment, switch = self._factory.memory._routing_context(assignment_id, **kwargs)
        return (assignment_id, switch.switch_id, assignment.installed_at_utc,
                assignment.removed_at_utc, switch.last_reported_scpi_channel_count)

    def _current_channel_map(self, cursor, assignment_id):
        return self._factory.memory.current_channel_map(assignment_id)

    def _routing_snapshot(self, cursor, assignment_id):
        return self._factory.memory.routing_snapshot_for_assignment(assignment_id)

    @staticmethod
    def _replacement(row):
        return row


class SqlReplacementBatchSaveTests(unittest.TestCase):
    def setUp(self):
        self.memory, self.run, self.specs = make_batch_fixture()
        self.factory = SqlBatchFactory(self.memory)
        self.repository = SqlBatchRepository(self.factory)

    def test_sql_checks_every_source_before_any_insert_and_preserves_links(self):
        self.repository.apply_routing_changes(self.specs, ())
        self.assertEqual(len(self.memory.replacements), 4)
        self.assertEqual(self.factory.commits, 1)
        self.assertEqual(self.factory.rollbacks, 0)
        checks = [i for i, (sql, _args) in enumerate(self.factory.calls)
                  if sql.startswith("SELECT analysis.run_id")]
        first_insert = next(i for i, (sql, _args) in enumerate(self.factory.calls)
                            if sql.startswith("INSERT INTO"))
        self.assertEqual(len(checks), 4)
        self.assertLess(max(checks), first_insert)
        self.assertTrue(any("dbo.IL_MEASUREMENTS WITH (HOLDLOCK)" in sql
                            for sql, _args in self.factory.calls))
        self.assertTrue(any("dbo.IL_RUNS WITH (UPDLOCK, HOLDLOCK)" in sql
                            for sql, _args in self.factory.calls))
        self.assertEqual({r.source_recommendation_id for r in self.memory.replacements.values()},
                         {s.source_recommendation_id for s in self.specs})

    def test_sql_rejects_genuinely_stale_history_before_inserts(self):
        self.memory.append_event(SpareEventSpec(self.run.assignment_id, 40, "designated", "AT", NOW))
        with self.assertRaisesRegex(ValueError, "spare history is no longer current"):
            self.repository.apply_routing_changes(self.specs, ())
        self.assertEqual(self.factory.insert_count, 0)
        self.assertEqual(self.factory.rollbacks, 1)

    def test_sql_later_insert_failure_rolls_everything_back(self):
        self.factory.fail_insert = 3
        with self.assertRaisesRegex(RuntimeError, "Injected insert failure"):
            self.repository.apply_routing_changes(self.specs, ())
        self.assertEqual(self.memory.replacements, {})
        self.assertEqual(self.factory.commits, 0)
        self.assertEqual(self.factory.rollbacks, 1)

    def test_sql_revalidates_later_candidate_and_rolls_back(self):
        specs = (self.specs[0], replace(self.specs[1], replacement_physical_port=38))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.repository.apply_routing_changes(specs, ())
        self.assertEqual(self.memory.replacements, {})
        self.assertEqual(self.factory.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
