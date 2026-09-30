import csv
import json
import tempfile
import unittest
from pathlib import Path

from domain.diagnostic_analysis import DiagnosticReading, MANUAL_METHOD
from domain.diagnostic_trace import DiagnosticTraceEvent
from infrastructure.diagnostic_export import export_diagnostic_history


def sample_reading():
    return DiagnosticReading(
        reading_number=1,
        timestamp="2026-09-29 12:00:00.000",
        method=MANUAL_METHOD,
        channel=3,
        physical_port=103,
        measured_1310=-0.94,
        reference_1310=-0.04,
        insertion_loss_1310=0.90,
        measured_1550=-0.50,
        reference_1550=0.14,
        insertion_loss_1550=0.64,
    )


class DiagnosticExportTests(unittest.TestCase):
    def test_exports_complete_history_to_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.csv"
            export_diagnostic_history(path, [sample_reading()])

            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))

        self.assertEqual(rows[0]["Method"], "Manual")
        self.assertEqual(rows[0]["Channel"], "3")
        self.assertEqual(rows[0]["1310 IL (dB)"], "0.9000")

    def test_exports_structured_history_to_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.json"
            export_diagnostic_history(path, [sample_reading()])
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["readings"][0]["channel"], 3)
        self.assertEqual(payload["readings"][0]["insertion_loss_1550"], 0.64)

    def test_empty_history_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no diagnostic readings"):
            export_diagnostic_history("unused.csv", [])

    def test_csv_can_include_companion_hardware_trace(self):
        event = DiagnosticTraceEvent(
            timestamp="2026-09-29T12:00:00.000+00:00",
            session_id="session-1",
            event="read_power",
            measurement_id=1,
            method=MANUAL_METHOD,
            channel=3,
            physical_port=103,
            requested_wavelength_nm=1310,
            actual_wavelength_nm=1310,
            wavelength_index=0,
            wavelength_count=2,
            source_id=0,
            source_enabled=True,
            operation="ReadPower",
            status="success",
            status_code=1,
            raw_power_dbm=-0.94,
            reference_power_dbm=-0.04,
            elapsed_ms=2.5,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.csv"
            export_diagnostic_history(
                path,
                [sample_reading()],
                include_hardware_trace=True,
                trace_events=[event],
                trace_metadata={
                    "application_version": "1.10.0",
                    "meter_description": "OP815",
                    "meter_serial": "meter-1",
                },
            )
            trace_path = Path(directory) / "diagnostic-hardware-trace.csv"
            with trace_path.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))

        self.assertEqual(rows[0]["Measurement ID"], "1")
        self.assertEqual(rows[0]["Raw power (dBm)"], "-0.9400")
        self.assertEqual(rows[0]["Meter serial"], "meter-1")

    def test_json_adds_trace_without_changing_reading_shape(self):
        event = DiagnosticTraceEvent(
            timestamp="2026-09-29T12:00:00.000+00:00",
            session_id="session-1",
            event="measurement_completed",
            measurement_id=1,
            method=MANUAL_METHOD,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.json"
            export_diagnostic_history(
                path,
                [sample_reading()],
                include_hardware_trace=True,
                trace_events=[event],
                trace_metadata={"session_id": "session-1"},
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertIn("hardware_trace", payload)
        self.assertEqual(payload["hardware_trace"]["events"][0]["measurement_id"], 1)
        self.assertNotIn("trace_measurement_id", payload["readings"][0])


if __name__ == "__main__":
    unittest.main()
