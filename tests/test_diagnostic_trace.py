import unittest

from application.diagnostic_trace import DiagnosticTraceRecorder
from op815_driver import OP815


class DiagnosticTraceTests(unittest.TestCase):
    def test_recorder_keeps_events_in_order_and_updates_meter_metadata(self):
        recorder = DiagnosticTraceRecorder("1.10.0")
        recorder.record(
            {
                "event": "read_power",
                "measurement_id": 7,
                "method": "Manual",
                "meter_description": "OP815",
                "meter_serial": "meter-7",
                "raw_power_dbm": -0.94,
            }
        )
        recorder.record(
            {
                "event": "command",
                "measurement_id": 7,
                "status": "error",
                "status_code": -1,
                "error": "ReadPower failed",
            }
        )

        events = recorder.events()
        self.assertEqual([event.event for event in events], ["read_power", "command"])
        self.assertEqual(events[0].measurement_id, 7)
        self.assertEqual(events[1].status_code, -1)
        self.assertEqual(recorder.metadata()["meter_serial"], "meter-7")

    def test_recorder_ignores_malformed_callback_payload(self):
        recorder = DiagnosticTraceRecorder("1.10.0")
        recorder.record(None)
        recorder.record({"event": "valid"})
        self.assertEqual(len(recorder.events()), 1)
        self.assertEqual(recorder.events()[0].event, "valid")

    def test_op815_trace_callback_cannot_change_driver_operation(self):
        driver = OP815.__new__(OP815)
        events = []
        driver._trace_callback = events.append
        driver._trace_context = {"measurement_id": 3, "method": "Monitoring"}
        driver._trace_metadata = {"application_version": "1.10.0"}
        driver.description = "OP815"
        driver.usb_serial = "meter-3"

        driver._trace(
            "command",
            operation="ReadPower",
            status="error",
            status_code=-1,
            error="ReadPower failed",
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["measurement_id"], 3)
        self.assertEqual(events[0]["meter_serial"], "meter-3")


if __name__ == "__main__":
    unittest.main()
