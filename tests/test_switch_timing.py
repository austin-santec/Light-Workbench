import unittest
from datetime import datetime, timedelta

from switch_timing import SwitchTestTimer
from domain.timing import SwitchTestTimer as DomainSwitchTestTimer


class SwitchTimingTests(unittest.TestCase):
    def test_legacy_module_reexports_domain_timer(self):
        self.assertIs(SwitchTestTimer, DomainSwitchTestTimer)

    def test_sessions_accumulate_and_record_continuations(self):
        current_time = [datetime(2026, 9, 18, 8, 42, 15)]
        current_monotonic = [100.0]
        metadata = {}
        timer = SwitchTestTimer(
            metadata,
            now_function=lambda: current_time[0],
            monotonic_function=lambda: current_monotonic[0],
        )

        self.assertTrue(timer.start_session())
        current_time[0] += timedelta(seconds=65)
        current_monotonic[0] += 65
        self.assertTrue(timer.stop_session())

        current_time[0] += timedelta(minutes=4)
        current_monotonic[0] += 240
        self.assertTrue(timer.start_session())
        current_time[0] += timedelta(seconds=125)
        current_monotonic[0] += 125
        self.assertTrue(timer.stop_session())

        self.assertEqual(metadata["Switch test start time"], "2026-09-18 08:42:15")
        self.assertEqual(
            metadata["Switch test continuation times"],
            "2026-09-18 08:47:20",
        )
        self.assertEqual(metadata["Switch test stop time"], "2026-09-18 08:49:25")
        self.assertEqual(metadata["Switch test total duration"], "00:03:10")
        self.assertEqual(metadata["Switch test session count"], "2")
        self.assertEqual(len(timer.sessions), 2)
        self.assertEqual(timer.sessions[0]["duration_seconds"], 65.0)
        self.assertEqual(timer.sessions[1]["duration_seconds"], 125.0)

    def test_timer_does_not_measure_other_tools(self):
        metadata = {}
        timer = SwitchTestTimer(metadata)
        self.assertFalse(timer.active)
        self.assertEqual(metadata, {})


if __name__ == "__main__":
    unittest.main()
