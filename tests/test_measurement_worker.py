import unittest

from PyQt5.QtWidgets import QApplication

from measurement_worker import MeasurementWorker


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


if __name__ == "__main__":
    unittest.main()
