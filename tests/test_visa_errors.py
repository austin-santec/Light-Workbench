import unittest

from pyvisa.errors import VisaIOError

from hardware.optical_switch import SantecOpticalSwitch, SantecSwitchProfile
from hardware.visa_errors import (
    SwitchCommunicationError,
    SwitchVisaErrorCategory,
    classify_switch_visa_error,
)


class SwitchVisaErrorTests(unittest.TestCase):
    def test_system_error_does_not_claim_physical_disconnect(self):
        classification = classify_switch_visa_error(
            VisaIOError(-1073807360),
            operation="routing logical channel 3",
            command="CLOSe 3",
            model="OSX-150",
        )

        self.assertEqual(
            classification.category, SwitchVisaErrorCategory.SYSTEM_ERROR
        )
        self.assertEqual(classification.status_name, "VI_ERROR_SYSTEM_ERROR")
        self.assertEqual(classification.disconnection_certainty, "suspected")
        self.assertIn("may have been disconnected", classification.operator_message)
        self.assertNotIn("was disconnected", classification.operator_message)

    def test_specific_statuses_have_distinct_operator_guidance(self):
        cases = (
            (
                -1073807194,
                SwitchVisaErrorCategory.CONNECTION_LOST,
                "connection was lost",
            ),
            (
                -1073807343,
                SwitchVisaErrorCategory.RESOURCE_NOT_FOUND,
                "resource is no longer available",
            ),
            (-1073807339, SwitchVisaErrorCategory.TIMEOUT, "did not respond"),
            (
                -1073807346,
                SwitchVisaErrorCategory.INVALID_SESSION,
                "session is no longer valid",
            ),
        )

        for status_code, category, expected_text in cases:
            with self.subTest(status_code=status_code):
                classification = classify_switch_visa_error(
                    VisaIOError(status_code),
                    operation="querying the active physical port",
                )
                self.assertEqual(classification.category, category)
                self.assertIn(expected_text, classification.operator_message)

    def test_switch_route_wraps_visa_error_and_traces_classification(self):
        class Instrument:
            def write(self, _command):
                raise VisaIOError(-1073807360)

        switch = SantecOpticalSwitch(trace_callback=None)
        events = []
        switch.add_trace_callback(events.append)
        switch.instrument = Instrument()
        switch.address = "USB0::0x2428::0xD00D::SWITCH::INSTR"
        switch.model = "OSX-150"
        switch.profile = SantecSwitchProfile(model="OSX-150")

        with self.assertRaises(SwitchCommunicationError) as caught:
            switch.set_channel(3)

        error = caught.exception
        self.assertEqual(
            error.classification.category, SwitchVisaErrorCategory.SYSTEM_ERROR
        )
        self.assertEqual(error.classification.status_code, -1073807360)
        communication = [
            event for event in events if event["event"] == "switch_communication_failed"
        ]
        self.assertEqual(len(communication), 1)
        self.assertEqual(communication[0]["status_code"], -1073807360)
        self.assertEqual(communication[0]["error_category"], "system_error")
        self.assertEqual(communication[0]["command"], "CLOSe 3")

    def test_current_channel_query_wraps_connection_lost(self):
        class Instrument:
            def query(self, _command):
                raise VisaIOError(-1073807194)

        switch = SantecOpticalSwitch()
        switch.instrument = Instrument()
        switch.model = "OSX-100"
        switch.profile = SantecSwitchProfile(model="OSX-100")

        with self.assertRaises(SwitchCommunicationError) as caught:
            switch.current_channel()

        self.assertEqual(
            caught.exception.classification.category,
            SwitchVisaErrorCategory.CONNECTION_LOST,
        )
        self.assertIn("connection was lost", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
