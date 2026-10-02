import unittest
from unittest.mock import patch

from pyvisa.errors import VisaIOError

from domain.models import ConnectionState, DeviceCategory
from hardware.optical_switch import (
    OSX150 as HardwareOSX150,
    SANTEC_USB_RESOURCE_QUERY,
    SwitchConnectionError,
    detect_santec_switch_model,
    resolve_santec_switch_profile,
)
from osx150_driver import OSX150


class OpticalSwitchAdapterTests(unittest.TestCase):
    def test_legacy_module_reexports_hardware_adapter(self):
        self.assertIs(OSX150, HardwareOSX150)

    def test_santec_resource_filter_requires_expected_usb_identity(self):
        self.assertTrue(
            HardwareOSX150._is_santec_usb_resource(
                "USB0::0x2428::0xD00D::SWITCH::INSTR"
            )
        )
        self.assertFalse(
            HardwareOSX150._is_santec_usb_resource(
                "USB0::0x1111::0xD00D::SWITCH::INSTR"
            )
        )
        self.assertFalse(
            HardwareOSX150._is_santec_usb_resource(
                "TCPIP0::192.0.2.10::inst0::INSTR"
            )
        )

    def test_santec_model_detection_is_ready_for_future_profiles(self):
        self.assertEqual(
            detect_santec_switch_model("SANTEC,OSX-150,SW-1,1.0"),
            "OSX-150",
        )
        self.assertEqual(
            detect_santec_switch_model("SANTEC,OSX-100,SW-2,1.0"),
            "OSX-100",
        )
        self.assertIsNone(detect_santec_switch_model("SANTEC,UNKNOWN,SW-3,1.0"))
        self.assertEqual(
            detect_santec_switch_model("SANTEC,OSX,19107,02.12.67"),
            None,
        )

        generic = resolve_santec_switch_profile("SANTEC,OSX,19107,02.12.67")
        self.assertEqual(generic.model, "OSX-100")
        self.assertEqual(generic.detection_method, "legacy_generic_osx")
        self.assertIsNotNone(generic.profile)
        for raw_model in ("OSX-100", "OSX100", "OSX 100"):
            resolution = resolve_santec_switch_profile(
                "SANTEC,%s,SW-100,02.12.67" % raw_model
            )
            self.assertEqual(resolution.model, "OSX-100")
            self.assertEqual(resolution.detection_method, "explicit_model")

    def test_switch_identity_reports_model_and_connection_state(self):
        switch = HardwareOSX150()

        info = switch.get_device_info(state=ConnectionState.CONNECTED)

        self.assertEqual(info.category, DeviceCategory.OPTICAL_SWITCH)
        self.assertEqual(info.model, "Santec optical switch")
        self.assertEqual(info.state, ConnectionState.CONNECTED)

    def test_supported_profile_connects_and_preserves_identity(self):
        trace_events = []
        class Instrument:
            def __init__(self, identity):
                self.identity = identity
                self.closed = False

            def query(self, command):
                if command == "*IDN?":
                    return self.identity
                if command == "CFG:SWT:END?":
                    return "48"
                if command == "CLOSe?":
                    return "2"
                raise AssertionError("Unexpected VISA query: %s" % command)

            def write(self, command):
                self.last_write = command

            def close(self):
                self.closed = True

        class ResourceManager:
            def __init__(self):
                self.instrument = Instrument("SANTEC,OSX-150,SW-150,1.0")

            def list_resources(self, query):
                self.query = query
                return ("USB0::0x2428::0xD00D::SW-150::INSTR",)

            def open_resource(self, _address):
                return self.instrument

            def close(self):
                pass

        switch = HardwareOSX150(trace_callback=trace_events.append)
        with patch("hardware.optical_switch.pyvisa.ResourceManager", ResourceManager):
            switch.connect()

        info = switch.get_device_info(state=ConnectionState.CONNECTED)
        self.assertEqual(info.model, "OSX-150")
        self.assertEqual(info.serial_number, "SW-150")
        self.assertEqual(info.firmware_version, "1.0")
        self.assertEqual(info.configured_channel_count, 48)
        self.assertEqual(switch.resource_manager.query, SANTEC_USB_RESOURCE_QUERY)
        self.assertEqual(switch.write_termination, "\n")
        with patch("hardware.optical_switch.time.sleep"):
            self.assertEqual(switch.set_channel(2), 2)
        names = [item["event"] for item in trace_events]
        self.assertIn("switch_identity_probe", names)
        self.assertIn("switch_configuration_validated", names)
        self.assertIn("switch_connected", names)
        self.assertIn("switch_route_completed", names)
        switch.close()

    def test_crlf_firmware_reopens_after_lf_timeout_and_retains_ending(self):
        class Instrument:
            def __init__(self):
                self.closed = False
                self.commands = []

            def query(self, command):
                self.commands.append((command, self.write_termination))
                if self.write_termination != "\r\n":
                    raise VisaIOError(-1073807339)
                if command == "*IDN?":
                    return "SANTEC,OSX-150,NEW-FW,03.01.02"
                if command == "CLOSe?":
                    return "3"
                if command == "CFG:SWT:END?":
                    return "48"
                raise AssertionError(command)

            def write(self, command):
                self.commands.append((command, self.write_termination))

            def close(self):
                self.closed = True

        class ResourceManager:
            def __init__(self):
                self.sessions = []
                self.closed = False

            def list_resources(self, query):
                self.query = query
                return ("USB0::0x2428::0xD00D::SWITCH::INSTR",)

            def open_resource(self, _address):
                session = Instrument()
                self.sessions.append(session)
                return session

            def close(self):
                self.closed = True

        manager = ResourceManager()
        switch = HardwareOSX150()
        with patch("hardware.optical_switch.pyvisa.ResourceManager", return_value=manager):
            switch.connect()
        self.assertEqual(len(manager.sessions), 2)
        self.assertTrue(manager.sessions[0].closed)
        self.assertFalse(manager.sessions[1].closed)
        self.assertEqual(switch.write_termination, "\r\n")
        self.assertIn("SCPI write ending: CRLF", switch.get_device_info().transport_details)
        with patch("hardware.optical_switch.time.sleep"):
            self.assertEqual(switch.set_channel(3), 3)
        self.assertIn(("CLOSe 3", "\r\n"), manager.sessions[1].commands)
        switch.close()
        self.assertTrue(manager.sessions[1].closed)
        self.assertTrue(manager.closed)

    def test_direct_address_works_when_enumeration_is_empty(self):
        class Instrument:
            def query(self, command):
                return "SANTEC,OSX-150,SW-1,03.01.02" if command == "*IDN?" else "1"

            def close(self):
                pass

        class ResourceManager:
            def __init__(self):
                self.opened = []

            def list_resources(self):
                raise AssertionError("Direct VISA connection must precede enumeration")

            def open_resource(self, address):
                self.opened.append(address)
                return Instrument()

            def close(self):
                pass

        manager = ResourceManager()
        address = "USB0::0x2428::0xD00D::SW-1::INSTR"
        switch = HardwareOSX150(resource_address=address)
        with patch("hardware.optical_switch.pyvisa.ResourceManager", return_value=manager):
            switch.connect()
        self.assertEqual(manager.opened, [address])
        self.assertEqual(switch.get_device_info().resource_address, address)
        switch.close()

    def test_connection_does_not_query_current_channel(self):
        class Instrument:
            def __init__(self):
                self.closed = False

            def query(self, command):
                if command == "*IDN?":
                    return "SANTEC,OSX-150,SW-1,03.01.02"
                if command == "CFG:SWT:END?":
                    return "48"
                raise AssertionError("Unsafe startup query: %s" % command)

            def close(self):
                self.closed = True

        class ResourceManager:
            def __init__(self):
                self.sessions = []

            def list_resources(self, query):
                return ("USB0::0x2428::0xD00D::SWITCH::INSTR",)

            def open_resource(self, _address):
                instrument = Instrument()
                self.sessions.append(instrument)
                return instrument

            def close(self):
                pass

        manager = ResourceManager()
        switch = HardwareOSX150()
        with patch("hardware.optical_switch.pyvisa.ResourceManager", return_value=manager):
            switch.connect()
        self.assertEqual(len(manager.sessions), 1)
        self.assertIs(switch.instrument, manager.sessions[0])
        self.assertEqual(switch.write_termination, "\n")
        switch.close()

    def test_failed_probes_release_all_sessions_and_manager(self):
        class Instrument:
            def __init__(self):
                self.closed = False

            def query(self, _command):
                raise VisaIOError(-1073807339)

            def close(self):
                self.closed = True

        class ResourceManager:
            def __init__(self):
                self.sessions = []
                self.closed = False

            def list_resources(self, query):
                raise VisaIOError(-1073807339)

            def open_resource(self, _address):
                session = Instrument()
                self.sessions.append(session)
                return session

            def close(self):
                self.closed = True

        manager = ResourceManager()
        switch = HardwareOSX150(resource_address="USB0::SWITCH::INSTR")
        with patch("hardware.optical_switch.pyvisa.ResourceManager", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "either LF or CRLF"):
                switch.connect()
        self.assertEqual(len(manager.sessions), 2)
        self.assertTrue(all(session.closed for session in manager.sessions))
        self.assertTrue(manager.closed)

    def test_stale_direct_address_falls_back_to_discovered_switch(self):
        found = "USB0::0x2428::0xD00D::FOUND::INSTR"
        stale = "USB0::0x2428::0xD00D::STALE::INSTR"

        class Instrument:
            def query(self, command):
                return "SANTEC,OSX-150,FOUND,03.00.85" if command == "*IDN?" else "1"

            def close(self):
                pass

        class ResourceManager:
            def __init__(self):
                self.opened = []

            def list_resources(self, query):
                return (found,)

            def open_resource(self, address):
                self.opened.append(address)
                if address == stale:
                    raise VisaIOError(-1073807343)
                return Instrument()

            def close(self):
                pass

        manager = ResourceManager()
        switch = HardwareOSX150(resource_address=stale)
        with patch("hardware.optical_switch.pyvisa.ResourceManager", return_value=manager):
            switch.connect()
        self.assertEqual(manager.opened, [stale, stale, found])
        self.assertEqual(switch.address, found)
        switch.close()

    def test_explicit_osx_100_profile_connects_and_reports_legacy_metadata(self):
        class Instrument:
            def query(self, command):
                if command == "*IDN?":
                    return "SANTEC,OSX-100,SW-100,02.12.67"
                if command == "CFG:SWT:END?":
                    return "100"
                if command == "CLOSe?":
                    return "3"
                raise AssertionError(command)

            def write(self, command):
                self.last_write = command

            def close(self):
                pass

        class ResourceManager:
            def list_resources(self, query):
                return ("USB0::0x2428::0xD00D::SW-100::INSTR",)

            def open_resource(self, _address):
                return Instrument()

            def close(self):
                pass

        switch = HardwareOSX150()
        with patch("hardware.optical_switch.pyvisa.ResourceManager", ResourceManager):
            switch.connect()

        info = switch.get_device_info(state=ConnectionState.CONNECTED)
        self.assertEqual(info.model, "OSX-100")
        self.assertEqual(info.serial_number, "SW-100")
        self.assertEqual(info.configured_channel_count, 100)
        self.assertEqual(info.model_detection_method, "explicit_model")
        with patch("hardware.optical_switch.time.sleep"):
            self.assertEqual(switch.set_channel(3), 3)
        self.assertEqual(switch.instrument.last_write, "CLOSe 3")
        switch.close()

    def test_legacy_generic_osx_identity_connects_as_osx_100_with_warning(self):
        events = []

        class Instrument:
            def query(self, command):
                if command == "*IDN?":
                    return "SANTEC,OSX,19107,02.12.67"
                if command == "CFG:SWT:END?":
                    return "100"
                if command == "CLOSe?":
                    return "3"
                raise AssertionError(command)

            def write(self, command):
                self.last_write = command

            def close(self):
                pass

        class ResourceManager:
            def list_resources(self, query):
                return ("USB0::0x2428::0xD00D::SW-100::INSTR",)

            def open_resource(self, _address):
                return Instrument()

            def close(self):
                pass

        switch = HardwareOSX150(trace_callback=events.append)
        with patch("hardware.optical_switch.pyvisa.ResourceManager", ResourceManager):
            switch.connect()

        info = switch.get_device_info(state=ConnectionState.CONNECTED)
        self.assertEqual(info.model, "OSX-100")
        self.assertEqual(info.serial_number, "19107")
        self.assertEqual(info.firmware_version, "02.12.67")
        self.assertEqual(info.configured_channel_count, 100)
        self.assertEqual(info.model_detection_method, "legacy_generic_osx")
        self.assertIn("legacy generic", info.connection_warning)
        self.assertIn("legacy_generic_osx", info.transport_details)
        connected = next(item for item in events if item["event"] == "switch_connected")
        self.assertEqual(connected["model"], "OSX-100")
        self.assertEqual(connected["model_detection_method"], "legacy_generic_osx")
        switch.close()

    def test_unsupported_explicit_osx_model_is_rejected(self):
        class Instrument:
            def query(self, command):
                if command == "*IDN?":
                    return "SANTEC,OSX-200,SW-200,1.0"
                raise AssertionError(command)

            def close(self):
                pass

        class ResourceManager:
            def list_resources(self, query):
                return ("USB0::0x2428::0xD00D::SW-200::INSTR",)

            def open_resource(self, _address):
                return Instrument()

            def close(self):
                pass

        switch = HardwareOSX150()
        with patch("hardware.optical_switch.pyvisa.ResourceManager", ResourceManager):
            with self.assertRaisesRegex(RuntimeError, "OSX-200.*does not yet"):
                switch.connect()

    def test_zero_channel_configuration_preserves_identity_and_blocks_connection(self):
        class Instrument:
            closed = False

            def query(self, command):
                if command == "*IDN?":
                    return "SANTEC,OSX-150,12345678910,03.00.85"
                if command == "CFG:SWT:END?":
                    return "0"
                raise AssertionError(command)

            def close(self):
                self.closed = True

        class ResourceManager:
            def __init__(self):
                self.instrument = Instrument()
                self.closed = False

            def list_resources(self, query):
                self.query = query
                return ("USB0::0x2428::0xD00D::12345678910::INSTR",)

            def open_resource(self, _address):
                return self.instrument

            def close(self):
                self.closed = True

        manager = ResourceManager()
        switch = HardwareOSX150()
        with patch("hardware.optical_switch.pyvisa.ResourceManager", return_value=manager):
            with self.assertRaises(SwitchConnectionError) as caught:
                switch.connect()

        diagnostics = caught.exception.diagnostics
        self.assertEqual(diagnostics.serial_number, "12345678910")
        self.assertEqual(diagnostics.firmware_version, "03.00.85")
        self.assertEqual(diagnostics.configured_channel_count, 0)
        self.assertEqual(diagnostics.failed_command, "CFG:SWT:END?")
        self.assertEqual(diagnostics.raw_failed_response, "0")
        self.assertIn("configuration may have been cleared", str(caught.exception))
        self.assertTrue(manager.instrument.closed)
        self.assertTrue(manager.closed)

    def test_last_known_address_precedes_automatic_discovery_and_is_not_manual(self):
        address = "USB0::0x2428::0xD00D::KNOWN::INSTR"

        class Instrument:
            def query(self, command):
                return (
                    "SANTEC,OSX-150,KNOWN,03.00.85"
                    if command == "*IDN?" else "48"
                )

            def close(self):
                pass

        class ResourceManager:
            def __init__(self):
                self.opened = []

            def list_resources(self, query):
                raise AssertionError("A working last-known address avoids enumeration")

            def open_resource(self, candidate):
                self.opened.append(candidate)
                return Instrument()

            def close(self):
                pass

        manager = ResourceManager()
        switch = HardwareOSX150(last_known_address=address)
        with patch("hardware.optical_switch.pyvisa.ResourceManager", return_value=manager):
            switch.connect()
        self.assertEqual(manager.opened, [address])
        self.assertEqual(switch.get_device_info().discovery_method, "Last-known address")
        switch.close()

    def test_automatic_discovery_remembers_address_only_after_valid_connection(self):
        address = "USB0::0x2428::0xD00D::AUTO::INSTR"
        remembered = []

        class Instrument:
            def query(self, command):
                return (
                    "SANTEC,OSX-150,AUTO,03.00.85"
                    if command == "*IDN?" else "48"
                )

            def close(self):
                pass

        class ResourceManager:
            def list_resources(self, query):
                self.query = query
                return (address,)

            def open_resource(self, _address):
                return Instrument()

            def close(self):
                pass

        manager = ResourceManager()
        switch = HardwareOSX150(address_observer=remembered.append)
        with patch("hardware.optical_switch.pyvisa.ResourceManager", return_value=manager):
            switch.connect()
        self.assertEqual(manager.query, SANTEC_USB_RESOURCE_QUERY)
        self.assertEqual(remembered, [address])
        self.assertEqual(
            switch.get_device_info().discovery_method,
            "Automatic USB discovery",
        )
        switch.close()


if __name__ == "__main__":
    unittest.main()
