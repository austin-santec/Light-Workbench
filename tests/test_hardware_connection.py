import threading
import unittest

from application.hardware_connection import HardwareConnectionManager
from application.measurement_worker import MeasurementWorker
from domain.hardware_connection import HardwareBusyError, HardwareCapability
from domain.models import ConnectionState
from hardware.factory import HardwareFactory


class FakeMeter:
    description = "Fake OP815"
    usb_serial = "METER-1"

    def __init__(self, fail=False):
        self.fail = fail
        self.fail_measurement = False
        self.connect_count = 0
        self.close_count = 0
        self.remote = False
        self.call_threads = []

    def connect(self):
        self.call_threads.append(threading.get_ident())
        self.connect_count += 1
        if self.fail:
            raise RuntimeError("meter unavailable")
        self.remote = True

    def measure_both_wavelengths(self):
        self.call_threads.append(threading.get_ident())
        if self.fail_measurement:
            raise RuntimeError("meter communication lost")
        return {1310: -1.0, 1550: -2.0}

    def measure_reference_wavelengths(self):
        self.call_threads.append(threading.get_ident())
        return {1310: -0.1, 1550: 0.1}

    def close(self):
        self.call_threads.append(threading.get_ident())
        self.close_count += 1
        self.remote = False


class FakeSwitch:
    def __init__(self, fail=False):
        self.fail = fail
        self.fail_routing = False
        self.connect_count = 0
        self.close_count = 0
        self.call_threads = []

    def connect(self):
        self.call_threads.append(threading.get_ident())
        self.connect_count += 1
        if self.fail:
            raise RuntimeError("switch unavailable")

    def configured_channel_count(self):
        self.call_threads.append(threading.get_ident())
        return 48

    def set_channel(self, channel):
        self.call_threads.append(threading.get_ident())
        if self.fail_routing:
            raise RuntimeError("switch communication lost")
        return channel

    def close(self):
        self.call_threads.append(threading.get_ident())
        self.close_count += 1


class FakeLaser:
    description = "Fake laser"
    serial_number = "LASER-1"

    def __init__(self):
        self.outputs = []
        self.close_count = 0

    def connect(self):
        pass

    def set_wavelength(self, _wavelength):
        pass

    def set_output(self, enabled):
        self.outputs.append(enabled)

    def close(self):
        self.close_count += 1


class HardwareConnectionManagerTests(unittest.TestCase):
    def make_manager(self, meter=None, switch=None, laser=None):
        meter = meter or FakeMeter()
        switch = switch or FakeSwitch()
        factory = HardwareFactory(
            power_meter_factory=lambda: meter,
            switch_factory=lambda: switch,
            laser_source_factory=(lambda: laser) if laser is not None else None,
        )
        return HardwareConnectionManager(factory), meter, switch

    def tearDown(self):
        manager = getattr(self, "manager", None)
        if manager is not None:
            try:
                manager.close_all()
            except Exception:
                pass

    def test_initial_state_is_disconnected(self):
        self.manager, _, _ = self.make_manager()
        self.assertFalse(self.manager.measurement_ready)
        self.assertFalse(self.manager.switch_ready)
        self.assertFalse(self.manager.run_ready)

    def test_connect_all_keeps_one_persistent_instance(self):
        self.manager, meter, switch = self.make_manager()
        results = self.manager.connect_all().result(timeout=2)
        self.assertTrue(all(not error for error in results.values()))
        self.manager.connect_all().result(timeout=2)
        self.assertEqual(meter.connect_count, 1)
        self.assertEqual(switch.connect_count, 1)
        self.assertTrue(self.manager.run_ready)

    def test_logging_failure_does_not_change_connection_or_lease_behavior(self):
        class BrokenLogger:
            trace_fanout = lambda self, _payload: None

            def record(self, *_args, **_kwargs):
                raise RuntimeError("logging unavailable")

        meter = FakeMeter()
        switch = FakeSwitch()
        factory = HardwareFactory(
            power_meter_factory=lambda: meter,
            switch_factory=lambda: switch,
        )
        self.manager = HardwareConnectionManager(
            factory,
            support_logger=BrokenLogger(),
        )

        results = self.manager.connect_all().result(timeout=2)
        self.assertTrue(all(not error for error in results.values()))
        proxy = self.manager.create_switch_proxy(
            object(), "Red Light Test", connect_if_needed=False
        )
        proxy.connect()
        self.assertEqual(proxy.set_channel(3), 3)
        proxy.close()
        self.assertTrue(self.manager.run_ready)

    def test_measurement_and_switch_can_connect_independently(self):
        self.manager, meter, switch = self.make_manager()
        self.manager.connect_measurement_hardware().result(timeout=2)
        self.assertTrue(self.manager.measurement_ready)
        self.assertFalse(self.manager.switch_ready)
        self.assertEqual(meter.connect_count, 1)
        self.assertEqual(switch.connect_count, 0)

        self.manager.disconnect_measurement_hardware().result(timeout=2)
        self.manager.connect_switch().result(timeout=2)
        self.assertFalse(self.manager.measurement_ready)
        self.assertTrue(self.manager.switch_ready)
        self.assertEqual(switch.connect_count, 1)

    def test_partial_failure_keeps_successful_device(self):
        self.manager, meter, _ = self.make_manager(switch=FakeSwitch(fail=True))
        results = self.manager.connect_all().result(timeout=2)
        self.assertEqual(results[HardwareCapability.MEASUREMENT], "")
        self.assertIn("switch unavailable", results[HardwareCapability.OPTICAL_SWITCH])
        self.assertTrue(self.manager.measurement_ready)
        self.assertFalse(self.manager.switch_ready)
        self.assertEqual(meter.close_count, 0)

    def test_meter_failure_does_not_roll_back_switch_success(self):
        self.manager, meter, switch = self.make_manager(meter=FakeMeter(fail=True))
        results = self.manager.connect_all().result(timeout=2)
        self.assertIn("meter unavailable", results[HardwareCapability.MEASUREMENT])
        self.assertEqual(results[HardwareCapability.OPTICAL_SWITCH], "")
        self.assertFalse(self.manager.measurement_ready)
        self.assertTrue(self.manager.switch_ready)
        self.assertEqual(meter.close_count, 1)
        self.assertEqual(switch.close_count, 0)

    def test_proxy_reuses_connection_and_releases_without_disconnect(self):
        self.manager, meter, _ = self.make_manager()
        self.manager.connect_measurement_hardware().result(timeout=2)
        token = object()
        proxy = self.manager.create_power_meter_proxy(
            token,
            "Live IL Reading",
            connect_if_needed=False,
        )
        proxy.connect()
        self.assertFalse(self.manager.measurement_ready)
        self.assertEqual(proxy.measure_both_wavelengths()[1310], -1.0)
        proxy.close()
        self.assertTrue(self.manager.measurement_ready)
        self.assertEqual(meter.connect_count, 1)
        self.assertEqual(meter.close_count, 0)

    def test_tool_proxy_can_connect_only_its_required_device(self):
        self.manager, meter, switch = self.make_manager()
        proxy = self.manager.create_power_meter_proxy(
            object(), "Live IL Reading", connect_if_needed=True
        )
        proxy.connect()
        self.assertEqual(meter.connect_count, 1)
        self.assertEqual(switch.connect_count, 0)
        proxy.close()
        self.assertTrue(self.manager.measurement_ready)
        self.assertFalse(self.manager.switch_ready)

    def test_conflicting_lease_is_rejected(self):
        self.manager, _, _ = self.make_manager()
        self.manager.connect_switch().result(timeout=2)
        first = self.manager.create_switch_proxy(
            object(), "Red Light Test", connect_if_needed=False
        )
        second = self.manager.create_switch_proxy(
            object(), "Hardware run", connect_if_needed=False
        )
        first.connect()
        with self.assertRaisesRegex(HardwareBusyError, "Red Light Test"):
            second.connect()
        first.close()

    def test_disconnect_is_rejected_while_leased(self):
        self.manager, _, _ = self.make_manager()
        proxy = self.manager.create_switch_proxy(
            object(), "Red Light Test", connect_if_needed=True
        )
        proxy.connect()
        results = self.manager.disconnect_switch().result(timeout=2)
        self.assertIn("Red Light Test", results[HardwareCapability.OPTICAL_SWITCH])
        proxy.close()

    def test_individual_disconnect_and_disconnect_all_close_sessions(self):
        self.manager, meter, switch = self.make_manager()
        self.manager.connect_all().result(timeout=2)

        self.manager.disconnect_switch().result(timeout=2)
        self.assertTrue(self.manager.measurement_ready)
        self.assertFalse(self.manager.switch_ready)
        self.assertEqual(switch.close_count, 1)
        self.assertTrue(meter.remote)

        self.manager.connect_switch().result(timeout=2)
        self.manager.disconnect_all().result(timeout=2)
        self.assertFalse(self.manager.measurement_ready)
        self.assertFalse(self.manager.switch_ready)
        self.assertEqual(meter.close_count, 1)
        self.assertFalse(meter.remote)
        self.assertEqual(switch.close_count, 2)

    def test_snapshot_reports_in_use_owner_then_available(self):
        self.manager, _, _ = self.make_manager()
        proxy = self.manager.create_switch_proxy(
            object(), "Red Light Test", connect_if_needed=True
        )
        proxy.connect()
        snapshot = self.manager.snapshot(HardwareCapability.OPTICAL_SWITCH)
        self.assertEqual(snapshot.device_info.state, ConnectionState.IN_USE)
        self.assertEqual(snapshot.owner, "Red Light Test")
        self.assertFalse(snapshot.available)

        proxy.close()
        snapshot = self.manager.snapshot(HardwareCapability.OPTICAL_SWITCH)
        self.assertEqual(snapshot.device_info.state, ConnectionState.CONNECTED)
        self.assertEqual(snapshot.owner, "")
        self.assertTrue(snapshot.available)

    def test_communication_failure_closes_only_affected_device(self):
        self.manager, meter, switch = self.make_manager()
        self.manager.connect_all().result(timeout=2)
        meter_proxy = self.manager.create_power_meter_proxy(
            object(), "Live IL Reading", connect_if_needed=False
        )
        meter.fail_measurement = True
        meter_proxy.connect()

        with self.assertRaisesRegex(RuntimeError, "communication lost"):
            meter_proxy.measure_both_wavelengths()

        meter_snapshot = self.manager.snapshot(HardwareCapability.MEASUREMENT)
        self.assertEqual(meter_snapshot.device_info.state, ConnectionState.ERROR)
        self.assertFalse(self.manager.measurement_ready)
        self.assertTrue(self.manager.switch_ready)
        self.assertEqual(meter.close_count, 1)
        self.assertEqual(switch.close_count, 0)

    def test_native_calls_use_one_owner_thread(self):
        self.manager, meter, switch = self.make_manager()
        self.manager.connect_all().result(timeout=2)
        meter_proxy = self.manager.create_power_meter_proxy(
            object(), "Meter tool", connect_if_needed=False
        )
        switch_proxy = self.manager.create_switch_proxy(
            object(), "Switch tool", connect_if_needed=False
        )
        meter_proxy.connect()
        meter_proxy.measure_both_wavelengths()
        meter_proxy.close()
        switch_proxy.connect()
        switch_proxy.set_channel(2)
        switch_proxy.close()
        self.assertEqual(len(set(meter.call_threads + switch.call_threads)), 1)

    def test_measurement_worker_releases_lease_but_keeps_devices_connected(self):
        self.manager, meter, switch = self.make_manager()
        self.manager.connect_all().result(timeout=2)
        token = object()
        worker = MeasurementWorker(
            self.manager.create_power_meter_proxy(
                token, "Hardware run", connect_if_needed=False
            ),
            self.manager.create_switch_proxy(
                token, "Hardware run", connect_if_needed=False
            ),
            [1],
            {1310: 0.0, 1550: 0.0},
        )
        worker.operator_required.connect(lambda *_args: worker.continue_current())
        worker.reading_ready.connect(lambda *_args: worker.write_current())
        worker.run()

        self.assertTrue(self.manager.run_ready)
        self.assertEqual(meter.connect_count, 1)
        self.assertEqual(switch.connect_count, 1)
        self.assertEqual(meter.close_count, 0)
        self.assertEqual(switch.close_count, 0)

    def test_separate_laser_is_required_and_forced_off(self):
        laser = FakeLaser()
        self.manager, _, _ = self.make_manager(laser=laser)
        self.manager.connect_measurement_hardware().result(timeout=2)
        self.assertTrue(self.manager.measurement_ready)
        self.assertEqual(laser.outputs, [False])
        self.manager.disconnect_measurement_hardware().result(timeout=2)
        self.assertEqual(laser.outputs, [False, False])
        self.assertEqual(laser.close_count, 1)

    def test_close_all_turns_off_laser_and_leaves_meter_remote_mode(self):
        laser = FakeLaser()
        self.manager, meter, switch = self.make_manager(laser=laser)
        self.manager.connect_all().result(timeout=2)

        self.manager.close_all()

        self.assertFalse(meter.remote)
        self.assertEqual(meter.close_count, 1)
        self.assertEqual(switch.close_count, 1)
        self.assertEqual(laser.outputs, [False, False])
        self.assertEqual(laser.close_count, 1)


if __name__ == "__main__":
    unittest.main()
