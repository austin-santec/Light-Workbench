import unittest
from unittest.mock import patch

from domain.models import ConnectionState, DeviceCategory
from op815_driver import OP815


class OP815CleanupTests(unittest.TestCase):
    def test_trace_callback_and_subscriber_receive_same_event_independently(self):
        driver = OP815.__new__(OP815)
        diagnostic_events = []
        support_events = []
        driver._trace_callback = diagnostic_events.append
        driver._trace_subscribers = []
        driver._trace_context = {}
        driver._trace_metadata = {}
        driver.description = "OP815"
        driver.usb_serial = "ILM-1"
        driver.add_trace_callback(support_events.append)

        driver._trace("read_power", raw_power_dbm=-0.5, status="success")
        driver.set_trace_callback(None)
        driver._trace("source_state", source_enabled=False, status="success")

        self.assertEqual([item["event"] for item in diagnostic_events], ["read_power"])
        self.assertEqual(
            [item["event"] for item in support_events],
            ["read_power", "source_state"],
        )

    def test_identity_exposes_detected_description_and_serial(self):
        driver = OP815.__new__(OP815)
        driver.description = "OP815"
        driver.usb_serial = "ILM-1"

        info = driver.get_device_info(state=ConnectionState.CONNECTED)

        self.assertEqual(info.category, DeviceCategory.POWER_METER)
        self.assertEqual(info.manufacturer, "Santec")
        self.assertEqual(info.model, "OP815")
        self.assertEqual(info.serial_number, "ILM-1")
        self.assertEqual(info.state, ConnectionState.CONNECTED)

    def test_complete_measurement_trace_links_both_wavelengths_and_references(self):
        driver = OP815.__new__(OP815)
        events = []
        sequence = []
        state = {"wavelength": 1310}

        def record_trace(event):
            events.append(event)
            sequence.append(("trace", event["event"]))

        driver._trace_callback = record_trace
        driver._trace_context = {
            "measurement_id": 11,
            "method": "Manual",
            "channel": 3,
            "physical_port": 103,
            "reference_1310_dbm": -0.04,
            "reference_1550_dbm": 0.14,
            "actual_wavelength_nm": 1550,
            "wavelength_index": 1,
            "wavelength_count": 2,
            "source_id": 1,
            "source_enabled": True,
            "reference_power_dbm": 0.14,
        }
        driver._trace_metadata = {"application_version": "1.10.0"}
        driver._diagnostic_verification_enabled = True
        driver.description = "OP815"
        driver.usb_serial = "meter-11"

        def get_wavelength(wavelength, index, count):
            wavelength._obj.value = state["wavelength"]
            index._obj.value = 0 if state["wavelength"] == 1310 else 1
            count._obj.value = 2
            return 1

        def set_wavelength(wavelength):
            state["wavelength"] = wavelength
            return 1

        def read_power(power):
            power._obj.value = {
                1310: -0.94,
                1550: -0.50,
            }[state["wavelength"]]
            return 1

        driver.get_wavelength = get_wavelength
        driver.set_wavelength = set_wavelength
        driver.source_on = lambda _source_id, _state: 1
        driver.read_power = read_power

        with patch(
            "op815_driver.time.sleep",
            side_effect=lambda seconds: sequence.append(("sleep", seconds)),
        ):
            measurements = driver.measure_both_wavelengths(
                wavelength_settling_seconds=0,
                source_settling_seconds=0.5,
                source_off_settling_seconds=0,
            )

        read_events = [event for event in events if event["event"] == "read_power"]
        verification_events = [
            event for event in events if event["event"] == "verified_before_read"
        ]
        self.assertEqual(measurements, {1310: -0.94, 1550: -0.50})
        self.assertEqual([event["requested_wavelength_nm"] for event in read_events], [1310, 1550])
        self.assertEqual([event["measurement_id"] for event in read_events], [11, 11])
        self.assertEqual(
            [event["reference_power_dbm"] for event in read_events],
            [-0.04, 0.14],
        )
        self.assertEqual([event["source_id"] for event in read_events], [0, 1])
        self.assertEqual(
            [(event["requested_wavelength_nm"], event["actual_wavelength_nm"])
             for event in verification_events],
            [(1310, 1310), (1550, 1550)],
        )
        self.assertTrue(all(event["status"] == "success" for event in verification_events))
        for verification_event in verification_events:
            verification_position = events.index(verification_event)
            following_reads = [
                event for event in read_events
                if events.index(event) > verification_position
            ]
            self.assertTrue(following_reads)
            self.assertEqual(
                following_reads[0]["requested_wavelength_nm"],
                verification_event["requested_wavelength_nm"],
            )
        verification_positions = [
            index
            for index, entry in enumerate(sequence)
            if entry == ("trace", "verified_before_read")
        ]
        for verification_position in verification_positions:
            self.assertEqual(sequence[verification_position - 2], ("sleep", 0.5))
            self.assertEqual(
                sequence[verification_position - 1],
                ("trace", "get_wavelength"),
            )

        first_sample_start = next(
            event for event in events
            if event["event"] == "wavelength_measurement_started"
        )
        self.assertNotIn("actual_wavelength_nm", first_sample_start)
        self.assertNotIn("source_enabled", first_sample_start)

    def test_normal_measurement_tolerates_vendor_index_convention(self):
        driver = OP815.__new__(OP815)
        state = {"wavelength": 1310}
        driver._trace_callback = None
        driver._trace_context = {}
        driver._trace_metadata = {}
        driver._diagnostic_verification_enabled = False

        def get_wavelength(wavelength, index, count):
            wavelength._obj.value = state["wavelength"]
            index._obj.value = 1 if state["wavelength"] == 1310 else 2
            count._obj.value = 2
            return 1

        driver.get_wavelength = get_wavelength
        driver.set_wavelength = lambda wavelength: state.update(wavelength=wavelength) or 1
        driver.source_on = lambda _source_id, _state: 1
        driver.read_power = lambda power: setattr(
            power._obj,
            "value",
            -0.94 if state["wavelength"] == 1310 else -0.50,
        ) or 1

        with patch("op815_driver.time.sleep"):
            measurements = driver.measure_both_wavelengths()

        self.assertEqual(measurements, {1310: -0.94, 1550: -0.50})

    def test_normal_measurement_still_rejects_actual_wavelength_mismatch(self):
        driver = OP815.__new__(OP815)
        read_calls = []
        driver._trace_callback = None
        driver._trace_context = {}
        driver._trace_metadata = {}
        driver._diagnostic_verification_enabled = False
        driver.get_wavelength = lambda wavelength, index, count: (
            setattr(wavelength._obj, "value", 1550),
            setattr(index._obj, "value", 1),
            setattr(count._obj, "value", 2),
            1,
        )[-1]
        driver.set_wavelength = lambda _wavelength: 1
        driver.source_on = lambda _source_id, _state: 1
        driver.read_power = lambda _power: read_calls.append(True) or 1

        with patch("op815_driver.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "selected 1550 nm"):
                driver.measure_wavelength(
                    1310,
                    wavelength_settling_seconds=0,
                    source_settling_seconds=0,
                    source_off_settling_seconds=0,
                )

        self.assertEqual(read_calls, [])

    def test_diagnostic_trace_reports_index_discrepancy_as_warning(self):
        driver = OP815.__new__(OP815)
        events = []
        driver._trace_callback = events.append
        driver._trace_context = {}
        driver._trace_metadata = {}
        driver._diagnostic_verification_enabled = True
        driver.get_wavelength = lambda wavelength, index, count: (
            setattr(wavelength._obj, "value", 1310),
            setattr(index._obj, "value", 1),
            setattr(count._obj, "value", 2),
            1,
        )[-1]
        driver.set_wavelength = lambda _wavelength: 1
        driver.source_on = lambda _source_id, _state: 1
        driver.read_power = lambda power: setattr(power._obj, "value", -0.94) or 1

        with patch("op815_driver.time.sleep"):
            power = driver.measure_wavelength(
                1310,
                wavelength_settling_seconds=0,
                source_settling_seconds=0,
                source_off_settling_seconds=0,
                verify_before_read=True,
            )

        self.assertEqual(power, -0.94)
        verification = [
            event for event in events if event["event"] == "verified_before_read"
        ]
        self.assertEqual(len(verification), 1)
        self.assertEqual(verification[0]["status"], "warning")
        self.assertIn("index 1 of 2", verification[0]["details"])
        metadata_warnings = [
            event
            for event in events
            if event["event"] == "wavelength_metadata_warning"
        ]
        self.assertEqual(len(metadata_warnings), 1)

    def test_final_wavelength_mismatch_blocks_read_power(self):
        driver = OP815.__new__(OP815)
        events = []
        state = {"wavelength": 1310, "get_calls": 0, "read_calls": 0}
        driver._trace_callback = events.append
        driver._trace_context = {"measurement_id": 12}
        driver._trace_metadata = {}
        driver.description = None
        driver.usb_serial = None

        def get_wavelength(wavelength, index, count):
            state["get_calls"] += 1
            reported = (1310, 1550)[state["get_calls"] - 1]
            wavelength._obj.value = reported
            index._obj.value = 0 if reported == 1310 else 1
            count._obj.value = 2
            return 1

        driver.get_wavelength = get_wavelength
        driver.set_wavelength = lambda wavelength: state.update(wavelength=wavelength) or 1
        driver.source_on = lambda _source_id, _state: 1

        def read_power(_power):
            state["read_calls"] += 1
            return 1

        driver.read_power = read_power

        with patch("op815_driver.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "selected 1550 nm"):
                driver.measure_wavelength(
                    1310,
                    wavelength_settling_seconds=0,
                    source_settling_seconds=0,
                    source_off_settling_seconds=0,
                    verify_before_read=True,
                )

        self.assertEqual(state["read_calls"], 0)
        verification = [
            event for event in events if event["event"] == "verified_before_read"
        ]
        self.assertEqual(len(verification), 1)
        self.assertEqual(verification[0]["status"], "error")
        self.assertEqual(verification[0]["actual_wavelength_nm"], 1550)

    def test_final_wavelength_query_error_blocks_read_power(self):
        driver = OP815.__new__(OP815)
        events = []
        state = {"get_calls": 0, "read_calls": 0}
        driver._trace_callback = events.append
        driver._trace_context = {}
        driver._trace_metadata = {}
        driver.description = None
        driver.usb_serial = None

        def get_wavelength(wavelength, index, count):
            state["get_calls"] += 1
            if state["get_calls"] == 2:
                raise RuntimeError("verification query failed")
            wavelength._obj.value = 1310
            index._obj.value = 0
            count._obj.value = 2
            return 1

        driver.get_wavelength = get_wavelength
        driver.set_wavelength = lambda _wavelength: 1
        driver.source_on = lambda _source_id, _state: 1
        driver.read_power = lambda _power: state.update(read_calls=state["read_calls"] + 1) or 1

        with patch("op815_driver.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "verification query failed"):
                driver.measure_wavelength(
                    1310,
                    wavelength_settling_seconds=0,
                    source_settling_seconds=0,
                    source_off_settling_seconds=0,
                    verify_before_read=True,
                )

        self.assertEqual(state["read_calls"], 0)
        verification = [
            event for event in events if event["event"] == "verified_before_read"
        ]
        self.assertEqual(len(verification), 1)
        self.assertEqual(verification[0]["status"], "error")
        self.assertIn("verification query failed", verification[0]["error"])

    def test_close_leaves_remote_mode_even_when_source_shutdown_fails(self):
        driver = OP815.__new__(OP815)
        driver.driver_open = True
        driver.remote_enabled = True
        calls = []

        def source_on(_source_id, _state):
            calls.append("source")
            raise RuntimeError("source shutdown failed")

        driver.source_on = source_on
        driver.remote_mode = lambda state: calls.append(("remote", state))
        driver.close_driver = lambda: calls.append("close")

        with self.assertRaisesRegex(RuntimeError, "source shutdown failed"):
            driver.close()

        self.assertIn(("remote", 0), calls)
        self.assertIn("close", calls)
        self.assertFalse(driver.remote_enabled)
        self.assertFalse(driver.driver_open)

    def test_close_releases_usb_device_after_driver_open_failure(self):
        driver = OP815.__new__(OP815)
        driver.usb_device_open = True
        driver.usb_handle = 123
        driver.driver_open = False
        driver.remote_enabled = False
        calls = []
        driver.close_driver = lambda: calls.append("close")

        driver.close()

        self.assertEqual(calls, ["close"])
        self.assertFalse(driver.usb_device_open)
        self.assertIsNone(driver.usb_handle)

    def test_connect_cleans_up_when_open_driver_fails(self):
        driver = OP815.__new__(OP815)
        driver.usb_device_open = False
        driver.usb_handle = None
        driver.driver_open = False
        driver.remote_enabled = False
        driver.select_device = lambda: (0, "OP815", "ILM-1")
        driver.open_usb_device = lambda _index, _handle: 1
        driver.open_driver = lambda _handle: -4
        calls = []
        driver.close_driver = lambda: calls.append("close")

        with self.assertRaisesRegex(RuntimeError, "OpenDriver failed with status -4"):
            driver.connect()

        self.assertEqual(calls, ["close"])
        self.assertFalse(driver.usb_device_open)
        self.assertFalse(driver.driver_open)

    def test_connect_cleans_up_when_remote_mode_fails(self):
        driver = OP815.__new__(OP815)
        driver.usb_device_open = False
        driver.usb_handle = None
        driver.driver_open = False
        driver.remote_enabled = False
        driver.select_device = lambda: (0, "OP815", "ILM-1")
        driver.open_usb_device = lambda _index, _handle: 1
        driver.open_driver = lambda _handle: 1
        driver.remote_mode = lambda _state: -1
        calls = []
        driver.close_driver = lambda: calls.append("close")

        with self.assertRaisesRegex(RuntimeError, "RemoteMode\(1\) failed"):
            driver.connect()

        self.assertEqual(calls, ["close"])
        self.assertFalse(driver.usb_device_open)
        self.assertFalse(driver.driver_open)


if __name__ == "__main__":
    unittest.main()
