import unittest

from PyQt5.QtWidgets import QApplication

from application.measurement_worker import MeasurementWorker as ApplicationMeasurementWorker
from domain.models import ConnectionState, DeviceCategory
from domain.extra_ports import PhysicalPortRouteResult, PhysicalPortRouteStatus
from hardware.session import OpticalTestSession
from measurement_worker import MeasurementWorker


class MeasurementWorkerImportTests(unittest.TestCase):
    def test_legacy_module_reexports_application_worker(self):
        self.assertIs(MeasurementWorker, ApplicationMeasurementWorker)


class FakePowerMeter:
    def __init__(self):
        self.connected = False
        self.closed = False

    def connect(self):
        self.connected = True

    def measure_both_wavelengths(self):
        return {1310: -1.0, 1550: -1.1}

    def close(self):
        self.closed = True


class SequencePowerMeter(FakePowerMeter):
    def __init__(self):
        super().__init__()
        self.readings = iter([
            {1310: -1.0, 1550: -1.1},
            {1310: -1.2, 1550: -1.3},
        ])

    def measure_both_wavelengths(self):
        return next(self.readings)


class InvalidThenValidPowerMeter(SequencePowerMeter):
    def __init__(self):
        FakePowerMeter.__init__(self)
        self.readings = iter([
            {1310: 0.8, 1550: -1.1},
            {1310: -1.0, 1550: -1.1},
        ])


class DarkPowerMeter(FakePowerMeter):
    def measure_both_wavelengths(self):
        return {1310: -60.0, 1550: -61.0}


class FakeSwitch:
    def __init__(self):
        self.connected = False
        self.closed = False

    def connect(self):
        self.connected = True

    def set_channel(self, channel):
        return channel + 48

    def close(self):
        self.closed = True


class ExtraPortSwitch(FakeSwitch):
    def __init__(self, route_results=None):
        super().__init__()
        self.logical_routes = []
        self.physical_routes = []
        self.route_results = list(route_results or [])

    def configured_channel_count(self):
        return 8

    def set_channel(self, channel):
        self.logical_routes.append(channel)
        return channel

    def set_physical_port(self, physical_port, maximum_port):
        self.physical_routes.append((physical_port, maximum_port))
        if self.route_results:
            return self.route_results.pop(0)
        return PhysicalPortRouteResult(
            physical_port,
            PhysicalPortRouteStatus.ACKNOWLEDGED,
            response="OK",
            network_address="192.0.2.15",
        )


class CapturingSupportLogger:
    def __init__(self):
        self.events = []

    def record(self, category, event, **fields):
        self.events.append((str(category), event, fields))
        return True


class MeasurementWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_runs_channels_and_cleans_up(self):
        meter = FakePowerMeter()
        switch = FakeSwitch()
        worker = MeasurementWorker(
            meter,
            switch,
            [1, 2],
            {1310: 0.72, 1550: 0.28},
        )
        readings = []
        progress = []
        worker.operator_required.connect(lambda _channel, _port: worker.continue_current())
        worker.reading_ready.connect(lambda *values: readings.append(values))
        worker.reading_ready.connect(lambda *_values: worker.write_current())
        worker.progress_changed.connect(lambda *values: progress.append(values))

        worker.run()

        self.assertEqual(readings[0][:2], (1, 49))
        self.assertEqual(readings[1][:2], (2, 50))
        for reading in readings:
            self.assertAlmostEqual(reading[2], 1.72)
            self.assertAlmostEqual(reading[3], 1.38)
        self.assertEqual(progress, [(1, 2), (2, 2)])
        self.assertTrue(meter.connected)
        self.assertTrue(meter.closed)
        self.assertTrue(switch.connected)
        self.assertTrue(switch.closed)

    def test_completed_signal_is_emitted_after_hardware_cleanup(self):
        meter = FakePowerMeter()
        switch = FakeSwitch()
        worker = MeasurementWorker(
            meter,
            switch,
            [1],
            {1310: 0.72, 1550: 0.28},
        )
        self.assertIsInstance(worker.hardware_session, OpticalTestSession)
        terminal_state = []
        worker.operator_required.connect(
            lambda _channel, _port: worker.continue_current()
        )
        worker.reading_ready.connect(lambda *_values: worker.write_current())
        worker.completed.connect(
            lambda: terminal_state.append((meter.closed, switch.closed))
        )

        worker.run()

        self.assertEqual(terminal_state, [(True, True)])

    def test_device_status_lifecycle_reports_connect_and_disconnect(self):
        worker = MeasurementWorker(
            FakePowerMeter(),
            FakeSwitch(),
            [1],
            {1310: 0.72, 1550: 0.28},
        )
        statuses = []
        worker.device_status_changed.connect(statuses.append)
        worker.operator_required.connect(lambda _channel, _port: worker.continue_current())
        worker.reading_ready.connect(lambda *_values: worker.write_current())

        worker.run()

        self.assertEqual(
            [(status.category, status.state) for status in statuses],
            [
                (DeviceCategory.POWER_METER, ConnectionState.CONNECTING),
                (DeviceCategory.OPTICAL_SWITCH, ConnectionState.CONNECTING),
                (DeviceCategory.POWER_METER, ConnectionState.CONNECTED),
                (DeviceCategory.OPTICAL_SWITCH, ConnectionState.CONNECTED),
                (DeviceCategory.POWER_METER, ConnectionState.DISCONNECTED),
                (DeviceCategory.OPTICAL_SWITCH, ConnectionState.DISCONNECTED),
            ],
        )

    def test_stop_before_operator_continuation(self):
        meter = FakePowerMeter()
        switch = FakeSwitch()
        worker = MeasurementWorker(meter, switch, [1], {1310: 0.72, 1550: 0.28})
        stopped = []
        worker.stopped.connect(lambda: stopped.append(True))
        worker.operator_required.connect(lambda _channel, _port: worker.stop())

        worker.run()

        self.assertEqual(stopped, [True])
        self.assertTrue(meter.closed)
        self.assertTrue(switch.closed)

    def test_live_write_mode_defaults_to_quarter_second_interval(self):
        worker = MeasurementWorker(
            FakePowerMeter(),
            FakeSwitch(),
            [1],
            {1310: 0.72, 1550: 0.28},
            live_write_mode=True,
        )

        self.assertEqual(worker.live_write_interval, 0.25)

    def test_none_channels_uses_switch_configured_count(self):
        meter = FakePowerMeter()
        switch = FakeSwitch()
        switch.configured_channel_count = lambda: 2
        worker = MeasurementWorker(meter, switch, None, {1310: 0.72, 1550: 0.28})
        channels = []
        worker.operator_required.connect(
            lambda channel, _port: (channels.append(channel), worker.continue_current())
        )
        worker.reading_ready.connect(lambda *_values: worker.write_current())

        worker.run()

        self.assertEqual(channels, [1, 2])

    def test_can_read_multiple_times_before_writing(self):
        meter = SequencePowerMeter()
        switch = FakeSwitch()
        worker = MeasurementWorker(meter, switch, [1], {1310: 0.72, 1550: 0.28})
        readings = []
        worker.operator_required.connect(lambda _channel, _port: worker.continue_current())

        def review_reading(*values):
            readings.append(values)
            if len(readings) == 1:
                worker.read_current()
            else:
                worker.write_current()

        worker.reading_ready.connect(review_reading)
        worker.run()

        self.assertEqual(len(readings), 2)
        self.assertAlmostEqual(readings[-1][2], 1.92)
        self.assertAlmostEqual(readings[-1][3], 1.58)

    def test_logging_tracks_complete_temporary_repeat_and_write_events(self):
        logger = CapturingSupportLogger()
        worker = MeasurementWorker(
            SequencePowerMeter(),
            FakeSwitch(),
            [1],
            {1310: 0.72, 1550: 0.28},
            support_logger=logger,
            workflow_id="wf-test",
        )
        readings = []
        worker.operator_required.connect(
            lambda _channel, _port: worker.continue_current()
        )

        def review_reading(*values):
            readings.append(values)
            if len(readings) == 1:
                worker.read_current()
            else:
                worker.write_current()

        worker.reading_ready.connect(review_reading)
        worker.run()

        completed = [
            fields
            for _category, event, fields in logger.events
            if event == "measurement.two_wavelength_completed"
        ]
        self.assertEqual(len(completed), 2)
        self.assertTrue(all(item["both_wavelengths_complete"] for item in completed))
        self.assertTrue(all(item["reading_state"] == "temporary" for item in completed))
        names = [event for _category, event, _fields in logger.events]
        self.assertIn("measurement.repeat_requested", names)
        self.assertIn("measurement.write_requested", names)

    def test_negative_write_is_rejected_and_episode_is_coalesced(self):
        logger = CapturingSupportLogger()
        worker = MeasurementWorker(
            InvalidThenValidPowerMeter(),
            FakeSwitch(),
            [1],
            {1310: 0.72, 1550: 0.28},
            support_logger=logger,
        )
        readings = []
        worker.operator_required.connect(lambda _channel, _port: worker.continue_current())

        def review_reading(*values):
            readings.append(values)
            worker.write_current()

        worker.reading_ready.connect(review_reading)
        worker.run()

        self.assertEqual(len(readings), 2)
        names = [event for _category, event, _fields in logger.events]
        self.assertEqual(
            names.count("measurement.negative_loss_episode_started"), 1
        )
        ended = [
            fields
            for _category, event, fields in logger.events
            if event == "measurement.negative_loss_episode_ended"
        ]
        self.assertEqual(len(ended), 1)
        self.assertEqual(ended[0]["invalid_sample_count"], 1)
        rejected = [
            fields
            for _category, event, fields in logger.events
            if event == "measurement.write_rejected_negative_loss"
        ]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["invalid_wavelength"], "1310")

    def test_live_write_mode_updates_until_operator_writes(self):
        meter = SequencePowerMeter()
        switch = FakeSwitch()
        worker = MeasurementWorker(
            meter,
            switch,
            [1],
            {1310: 0.72, 1550: 0.28},
            live_write_mode=True,
            live_write_interval=0.1,
        )
        readings = []
        worker.operator_required.connect(lambda *_values: None)

        def accept_second_live_reading(*values):
            readings.append(values)
            if len(readings) == 2:
                worker.write_current()

        worker.reading_ready.connect(accept_second_live_reading)
        worker.run()

        self.assertEqual(len(readings), 2)
        self.assertAlmostEqual(readings[0][2], 1.72)
        self.assertAlmostEqual(readings[1][2], 1.92)
        self.assertTrue(meter.closed)
        self.assertTrue(switch.closed)

    def test_full_pass_can_resume_interrupted_channel_after_override(self):
        meter = FakePowerMeter()
        switch = FakeSwitch()
        switch.configured_channel_count = lambda: 3
        worker = MeasurementWorker(
            meter,
            switch,
            None,
            {1310: 0.72, 1550: 0.28},
        )
        routed_channels = []

        def operator_required(channel, _port):
            routed_channels.append(channel)
            if channel == 2 and routed_channels.count(2) == 1:
                worker.change_channel(1, True)
            else:
                worker.continue_current()

        worker.operator_required.connect(operator_required)
        worker.reading_ready.connect(lambda *_values: worker.write_current())

        worker.run()

        self.assertEqual(routed_channels, [1, 2, 1, 2, 3])
        self.assertTrue(meter.closed)
        self.assertTrue(switch.closed)

    def test_full_pass_can_continue_sequentially_from_override(self):
        meter = FakePowerMeter()
        switch = FakeSwitch()
        switch.configured_channel_count = lambda: 4
        worker = MeasurementWorker(
            meter,
            switch,
            None,
            {1310: 0.72, 1550: 0.28},
        )
        routed_channels = []

        def operator_required(channel, _port):
            routed_channels.append(channel)
            if channel == 2 and routed_channels.count(2) == 1:
                worker.change_channel(4, False)
            else:
                worker.continue_current()

        worker.operator_required.connect(operator_required)
        worker.reading_ready.connect(lambda *_values: worker.write_current())

        worker.run()

        self.assertEqual(routed_channels, [1, 2, 4, 2, 3])

    def test_existing_full_pass_retests_selected_start_then_skips_saved_channels(self):
        meter = FakePowerMeter()
        switch = FakeSwitch()
        switch.configured_channel_count = lambda: 4
        worker = MeasurementWorker(
            meter,
            switch,
            None,
            {1310: 0.72, 1550: 0.28},
            existing_channels=[1, 2],
            resume_existing=True,
            resume_full_pass=True,
        )
        routed_channels = []

        worker.continuation_selection_required.connect(
            lambda _count, _completed, _default: worker.select_resume_channel(2)
        )
        worker.operator_required.connect(
            lambda channel, _port: (routed_channels.append(channel), worker.continue_current())
        )
        worker.reading_ready.connect(lambda *_values: worker.write_current())

        worker.run()

        self.assertEqual(routed_channels, [2, 3, 4])

    def test_manual_channel_order_allows_repeated_channels(self):
        meter = FakePowerMeter()
        switch = FakeSwitch()
        switch.configured_channel_count = lambda: 3
        worker = MeasurementWorker(
            meter,
            switch,
            None,
            {1310: 0.72, 1550: 0.28},
            manual_channel_order=True,
        )
        chosen_channels = iter([2, 1, 2, 3])
        routed_channels = []
        progress = []

        def choose_channel(_count, completed_channels):
            if len(completed_channels) == 3:
                worker.finish_manual_pass()
            else:
                worker.select_next_channel(next(chosen_channels))

        worker.channel_selection_required.connect(choose_channel)
        worker.operator_required.connect(
            lambda channel, _port: (routed_channels.append(channel), worker.continue_current())
        )
        worker.reading_ready.connect(lambda *_values: worker.write_current())
        worker.progress_changed.connect(lambda *values: progress.append(values))

        worker.run()

        self.assertEqual(routed_channels, [2, 1, 2, 3])
        self.assertEqual(progress, [(1, 3), (2, 3), (2, 3), (3, 3)])
        self.assertTrue(meter.closed)
        self.assertTrue(switch.closed)

    def test_full_pass_uses_front_panel_count_then_sequential_extra_ports(self):
        switch = ExtraPortSwitch([
            PhysicalPortRouteResult(3, PhysicalPortRouteStatus.ACKNOWLEDGED),
            PhysicalPortRouteResult(4, PhysicalPortRouteStatus.FAILED, detail="absent"),
        ])
        worker = MeasurementWorker(
            FakePowerMeter(),
            switch,
            None,
            {1310: 0.72, 1550: 0.28},
            front_panel_channel_count=2,
            offer_extra_ports=True,
            maximum_physical_port_probe=8,
        )
        readings = []
        worker.extra_port_offer_required.connect(
            lambda _count: worker.choose_extra_port_testing(True)
        )
        worker.operator_required.connect(
            lambda _channel, _port: worker.continue_current()
        )

        def accept_reading(*values):
            readings.append(values)
            worker.write_current()

        worker.reading_ready.connect(accept_reading)
        worker.extra_port_issue.connect(
            lambda *_args: worker.extra_port_action("no_more")
        )
        worker.run()

        self.assertEqual(switch.logical_routes, [1, 2])
        self.assertEqual(switch.physical_routes, [(3, 8), (4, 8)])
        self.assertEqual([reading[0] for reading in readings], [1, 2, 3])

    def test_finish_run_declines_extra_ports_without_cli_route(self):
        switch = ExtraPortSwitch()
        worker = MeasurementWorker(
            FakePowerMeter(), switch, None, {1310: 0.72, 1550: 0.28},
            front_panel_channel_count=2, offer_extra_ports=True,
        )
        offers = []
        worker.extra_port_offer_required.connect(
            lambda count: (offers.append(count), worker.choose_extra_port_testing(False))
        )
        worker.operator_required.connect(lambda *_args: worker.continue_current())
        worker.reading_ready.connect(lambda *_args: worker.write_current())
        worker.run()

        self.assertEqual(offers, [2])
        self.assertEqual(switch.physical_routes, [])

    def test_continued_full_pass_skips_existing_extra_ports(self):
        switch = ExtraPortSwitch([
            PhysicalPortRouteResult(4, PhysicalPortRouteStatus.ACKNOWLEDGED),
            PhysicalPortRouteResult(6, PhysicalPortRouteStatus.FAILED, detail="absent"),
        ])
        worker = MeasurementWorker(
            FakePowerMeter(),
            switch,
            None,
            {1310: 0.72, 1550: 0.28},
            resume_existing=True,
            front_panel_channel_count=2,
            offer_extra_ports=True,
            run_mode="continue",
            existing_extra_physical_ports=[3, 5],
            maximum_physical_port_probe=8,
        )
        worker.extra_port_offer_required.connect(
            lambda _count: worker.choose_extra_port_testing(True)
        )
        worker.operator_required.connect(
            lambda _channel, _port: worker.continue_current()
        )
        worker.reading_ready.connect(lambda *_args: worker.write_current())
        worker.extra_port_issue.connect(
            lambda *_args: worker.extra_port_action("no_more")
        )

        worker.run()

        self.assertEqual(switch.physical_routes, [(4, 8), (6, 8)])

    def test_retry_does_not_advance_or_accept_a_provisional_candidate(self):
        switch = ExtraPortSwitch()
        worker = MeasurementWorker(
            FakePowerMeter(), switch, None, {1310: 0.72, 1550: 0.28},
            front_panel_channel_count=1, offer_extra_ports=True,
            maximum_physical_port_probe=3,
        )
        extra_visits = []
        worker.extra_port_offer_required.connect(
            lambda _count: worker.choose_extra_port_testing(True)
        )

        def operator(channel, _port):
            if channel == 2:
                extra_visits.append(channel)
                if len(extra_visits) == 1:
                    worker.extra_port_action("retry")
                else:
                    worker.extra_port_action("no_more")
            else:
                worker.continue_current()

        worker.operator_required.connect(operator)
        worker.reading_ready.connect(lambda *_args: worker.write_current())
        worker.run()

        self.assertEqual(switch.physical_routes, [(2, 3), (2, 3)])
        self.assertEqual(extra_visits, [2, 2])

    def test_unverified_route_requires_explicit_confirmation(self):
        switch = ExtraPortSwitch([
            PhysicalPortRouteResult(2, PhysicalPortRouteStatus.UNVERIFIED),
        ])
        worker = MeasurementWorker(
            FakePowerMeter(), switch, None, {1310: 0.72, 1550: 0.28},
            front_panel_channel_count=1, offer_extra_ports=True,
            maximum_physical_port_probe=2,
        )
        confirmations = []
        worker.extra_port_offer_required.connect(
            lambda _count: worker.choose_extra_port_testing(True)
        )
        worker.extra_port_confirmation_required.connect(
            lambda port, _result: (
                confirmations.append(port),
                worker.extra_port_action("proceed_unverified"),
            )
        )
        worker.operator_required.connect(lambda *_args: worker.continue_current())
        worker.reading_ready.connect(lambda *_args: worker.write_current())
        worker.extra_port_issue.connect(
            lambda *_args: worker.extra_port_action("stop")
        )
        worker.run()

        self.assertEqual(confirmations, [2])

    def test_dark_extra_candidate_is_discarded_without_reading_ready(self):
        switch = ExtraPortSwitch()
        worker = MeasurementWorker(
            DarkPowerMeter(), switch, None, {1310: 0.72, 1550: 0.28},
            front_panel_channel_count=1, offer_extra_ports=True,
            maximum_physical_port_probe=3,
        )
        readings = []
        issues = []
        worker.extra_port_offer_required.connect(
            lambda _count: worker.choose_extra_port_testing(True)
        )
        worker.operator_required.connect(lambda *_args: worker.continue_current())

        def handle_reading(*values):
            readings.append(values)
            worker.write_current()

        def handle_issue(_port, kind, _message):
            issues.append(kind)
            worker.extra_port_action("no_more")

        worker.reading_ready.connect(handle_reading)
        worker.extra_port_issue.connect(handle_issue)
        worker.run()

        # The front-panel sample is intentionally dark in this artificial
        # test and retains legacy behavior; only the extra candidate is gated.
        self.assertEqual([item[0] for item in readings], [1])
        self.assertEqual(issues, ["invalid_signal"])


if __name__ == "__main__":
    unittest.main()
