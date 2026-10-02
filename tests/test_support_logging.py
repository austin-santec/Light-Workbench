import gzip
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from application.support_logging import SupportLoggingService, TraceEventFanout
from domain.support_events import SUPPORT_LOG_SCHEMA_VERSION
from infrastructure.support_log_writer import (
    RAW_RESPONSE_LIMIT,
    SupportLogWriter,
    sanitize_event_payload,
)


class MutableClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class CapturingWriter:
    active_root = Path("logs")
    active_path = None
    fallback_active = False
    healthy = True
    last_error = ""
    memory_events = ()
    preferred_root = Path("logs")

    def __init__(self):
        self.events = []
        self.closed = False

    def write(self, payload):
        self.events.append(dict(payload))

    def flush(self):
        pass

    def close(self):
        self.closed = True


class BlockingWriter(CapturingWriter):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def write(self, payload):
        self.entered.set()
        self.release.wait(2)
        super().write(payload)


class SupportLogWriterTests(unittest.TestCase):
    def test_daily_jsonl_appends_multiple_sessions_and_has_valid_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "logs"
            fallback = Path(directory) / "fallback"
            clock = MutableClock(datetime(2026, 10, 2, 12, tzinfo=timezone.utc))
            first = SupportLogWriter(root, fallback, now=clock)
            first.write({"event": "first", "value": 1})
            first.close()
            second = SupportLogWriter(root, fallback, now=clock)
            second.write({"event": "second", "value": 2})

            path = root / "light-workbench-2026-10-02.jsonl"
            payloads = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual([item["event"] for item in payloads], ["first", "second"])

    def test_midnight_and_size_rollover(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = MutableClock(datetime(2026, 10, 2, 23, 59, tzinfo=timezone.utc))
            writer = SupportLogWriter(
                Path(directory) / "logs",
                Path(directory) / "fallback",
                now=clock,
                max_file_bytes=40,
            )
            writer.write({"event": "a", "details": "x" * 50})
            writer.write({"event": "b", "details": "x" * 50})
            self.assertTrue(writer.active_path.name.endswith("part02.jsonl"))
            clock.value += timedelta(days=1)
            writer.write({"event": "c"})
            self.assertEqual(
                writer.active_path.name,
                "light-workbench-2026-10-03.jsonl",
            )

    def test_retention_compression_total_limit_and_unrelated_file_safety(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "logs"
            root.mkdir()
            unrelated = root / "operator-notes.txt"
            unrelated.write_text("keep")
            expired = root / "light-workbench-2026-08-01.jsonl"
            expired.write_text("old")
            compressible = root / "light-workbench-2026-09-20.jsonl"
            compressible.write_text("compress me")
            recent = root / "light-workbench-2026-10-01.jsonl"
            recent.write_text("x" * 100)
            clock = MutableClock(datetime(2026, 10, 2, 12, tzinfo=timezone.utc))
            writer = SupportLogWriter(
                root,
                Path(directory) / "fallback",
                now=clock,
                max_total_bytes=50,
            )

            self.assertFalse(expired.exists())
            self.assertFalse(compressible.exists())
            self.assertTrue((root / (compressible.name + ".gz")).exists() or not recent.exists())
            self.assertTrue(unrelated.exists())
            self.assertEqual(unrelated.read_text(), "keep")
            self.assertTrue(all(path.name == unrelated.name or path.stat().st_size <= 50 for path in root.iterdir()))

    def test_retention_removes_only_logs_older_than_thirty_days(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "logs"
            root.mkdir()
            boundary = root / "light-workbench-2026-09-02.jsonl"
            expired = root / "light-workbench-2026-09-01.jsonl"
            boundary.write_text("boundary")
            expired.write_text("expired")
            SupportLogWriter(
                root,
                Path(directory) / "fallback",
                now=MutableClock(datetime(2026, 10, 2, 12, tzinfo=timezone.utc)),
            )
            self.assertTrue(boundary.exists() or boundary.with_suffix(".jsonl.gz").exists())
            self.assertFalse(expired.exists())
            self.assertFalse(expired.with_suffix(".jsonl.gz").exists())

    def test_inactive_log_older_than_seven_days_is_gzip_compressed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "logs"
            root.mkdir()
            source = root / "light-workbench-2026-09-24.jsonl"
            source.write_text('{"event":"old"}\n', encoding="utf-8")
            SupportLogWriter(
                root,
                Path(directory) / "fallback",
                now=MutableClock(datetime(2026, 10, 2, 12, tzinfo=timezone.utc)),
            )
            compressed = source.with_suffix(".jsonl.gz")
            self.assertFalse(source.exists())
            self.assertTrue(compressed.exists())
            with gzip.open(compressed, "rt", encoding="utf-8") as stream:
                self.assertEqual(stream.read(), '{"event":"old"}\n')

    def test_active_file_is_never_removed_by_total_size_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = SupportLogWriter(
                Path(directory) / "logs",
                Path(directory) / "fallback",
                max_total_bytes=1,
            )
            writer.write({"event": "active", "details": "large"})
            active = writer.active_path
            writer._run_maintenance()
            self.assertTrue(active.exists())

    def test_unwritable_preferred_root_uses_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            preferred = Path(directory) / "not-a-directory"
            preferred.write_text("file")
            fallback = Path(directory) / "fallback"
            writer = SupportLogWriter(preferred, fallback)
            writer.write({"event": "fallback"})
            self.assertTrue(writer.fallback_active)
            self.assertEqual(writer.active_root, fallback)
            self.assertTrue(writer.active_path.is_file())

    def test_both_unavailable_uses_bounded_memory_buffer(self):
        with tempfile.TemporaryDirectory() as directory:
            preferred = Path(directory) / "preferred-file"
            fallback = Path(directory) / "fallback-file"
            preferred.write_text("file")
            fallback.write_text("file")
            writer = SupportLogWriter(
                preferred,
                fallback,
                memory_capacity=2,
            )
            for index in range(3):
                writer.write({"event": "memory", "status": index})
            self.assertIsNone(writer.active_root)
            self.assertEqual(len(writer.memory_events), 2)
            self.assertTrue(writer.last_error)

    def test_runtime_disk_failure_switches_to_fallback_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            fallback = Path(directory) / "fallback"
            writer = SupportLogWriter(Path(directory) / "logs", fallback)
            with patch.object(writer, "_path_for_write", side_effect=OSError("disk full")):
                writer.write({"event": "failed-primary"})
            self.assertTrue(writer.fallback_active)
            writer.write({"event": "fallback-write"})
            self.assertTrue(writer.active_path.is_file())

    def test_sanitization_redacts_paths_prohibited_fields_and_long_responses(self):
        profile = Path("C:/Users/TestUser")
        payload = sanitize_event_payload(
            {
                "destination": "C:/Users/TestUser/Documents/run.json",
                "password": "secret",
                "clipboard_contents": "private",
                "raw_response": "R" * (RAW_RESPONSE_LIMIT + 20),
            },
            user_profile=profile,
        )
        self.assertEqual(payload["destination"], "%USERPROFILE%/Documents/run.json")
        self.assertNotIn("password", payload)
        self.assertNotIn("clipboard_contents", payload)
        self.assertEqual(len(payload["raw_response"]), RAW_RESPONSE_LIMIT)

    def test_sanitization_drops_unknown_object_representations(self):
        payload = sanitize_event_payload(
            {"details": object(), "status": "safe"}
        )
        self.assertNotIn("details", payload)
        self.assertEqual(payload["status"], "safe")


class SupportLoggingServiceTests(unittest.TestCase):
    def test_schema_timestamps_identifiers_and_clean_shutdown_flush(self):
        writer = CapturingWriter()
        service = SupportLoggingService(writer, app_instance_id="app-1")
        workflow = service.new_workflow("run")
        operation = service.new_operation_id("measurement")
        service.record(
            "measurement",
            "measurement.completed",
            workflow_id=workflow.workflow_id,
            operation_id=operation,
            measurement_id=operation,
            both_wavelengths_complete=True,
        )
        service.shutdown()

        event = writer.events[0]
        self.assertEqual(event["schema_version"], SUPPORT_LOG_SCHEMA_VERSION)
        self.assertTrue(event["timestamp_utc"].endswith("Z"))
        self.assertEqual(event["app_instance_id"], "app-1")
        self.assertEqual(event["workflow_id"], workflow.workflow_id)
        self.assertEqual(event["operation_id"], operation)
        self.assertTrue(writer.closed)

    def test_concurrent_producers_are_serialized(self):
        writer = CapturingWriter()
        service = SupportLoggingService(writer, queue_capacity=500)
        threads = [
            threading.Thread(
                target=lambda index=index: [
                    service.record("application", "producer.event", status=index)
                    for _ in range(25)
                ]
            )
            for index in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertTrue(service.flush())
        service.shutdown()
        producer_events = [item for item in writer.events if item["event"] == "producer.event"]
        self.assertEqual(len(producer_events), 100)

    def test_bounded_queue_tracks_overflow_and_emits_synthetic_event(self):
        writer = BlockingWriter()
        service = SupportLoggingService(writer, queue_capacity=2)
        service.record("application", "first")
        self.assertTrue(writer.entered.wait(1))
        for index in range(20):
            service.record("application", "overflow", status=index)
        self.assertGreater(service.status().dropped_event_count, 0)
        writer.release.set()
        service.record("application", "after_overflow", level="warning")
        self.assertTrue(service.flush())
        service.shutdown()
        self.assertIn("logging.events_dropped", [item["event"] for item in writer.events])

    def test_hardware_trace_fanout_isolates_subscriber_failure(self):
        received = []
        fanout = TraceEventFanout()
        bad = lambda _payload: (_ for _ in ()).throw(RuntimeError("bad"))
        fanout.subscribe(bad)
        fanout.subscribe(received.append)
        fanout({"event": "read_power"})
        fanout.unsubscribe(bad)
        fanout({"event": "source_state"})
        self.assertEqual([item["event"] for item in received], ["read_power", "source_state"])

    def test_unhandled_exception_record_contains_sanitized_error_context(self):
        writer = CapturingWriter()
        service = SupportLoggingService(writer)
        try:
            raise ValueError("failure in C:/Users/Test/Documents/run.json")
        except ValueError as error:
            service.record_exception(
                "application.unhandled_exception",
                type(error),
                error,
                error.__traceback__,
            )
        self.assertTrue(service.flush())
        service.shutdown()
        event = writer.events[0]
        self.assertEqual(event["level"], "critical")
        self.assertEqual(event["error_type"], "ValueError")
        self.assertIn("ValueError", event["stack_trace"])


if __name__ == "__main__":
    unittest.main()
