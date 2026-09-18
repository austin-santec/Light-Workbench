"""Timing helpers for real switch-test sessions only."""

import time
from datetime import datetime


def format_timestamp(value=None):
    """Format a local timestamp consistently in run metadata."""
    value = value or datetime.now()
    return value.strftime("%Y-%m-%d %H:%M:%S")


def format_duration(seconds):
    """Format elapsed seconds as an hours-capable HH:MM:SS value."""
    total_seconds = max(0, int(round(float(seconds or 0))))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return "%02d:%02d:%02d" % (hours, minutes, seconds)


def parse_duration(value):
    """Parse the displayed HH:MM:SS duration format."""
    try:
        parts = [int(part) for part in str(value or "").split(":")]
        if len(parts) != 3 or parts[0] < 0 or not 0 <= parts[1] < 60 or not 0 <= parts[2] < 60:
            return 0.0
        return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    except (TypeError, ValueError):
        return 0.0


class SwitchTestTimer:
    """Accumulate elapsed time across hardware switch-test sessions.

    The timer is deliberately independent of Live IL and Red Light Test. The
    application creates and starts it only from the real hardware-run path.
    """

    def __init__(
        self,
        metadata,
        sessions=None,
        now_function=None,
        monotonic_function=None,
    ):
        self.metadata = metadata
        self.sessions = sessions if sessions is not None else []
        self._now = now_function or datetime.now
        self._monotonic = monotonic_function or time.monotonic
        self._active_session = None
        self._active_monotonic = None
        self.total_seconds = parse_duration(
            self.metadata.get("Switch test total duration")
        )
        if not self.total_seconds:
            self.total_seconds = sum(
                float(session.get("duration_seconds") or 0)
                for session in self.sessions
            )

    @property
    def active(self):
        return self._active_session is not None

    def start_session(self):
        """Record a first start or a later continuation."""
        if self.active:
            return False

        now = self._now()
        timestamp = format_timestamp(now)
        if self.metadata.get("Switch test start time"):
            continuations = self.metadata.get("Switch test continuation times", "")
            continuation_values = [
                value.strip() for value in str(continuations).split(";") if value.strip()
            ]
            continuation_values.append(timestamp)
            self.metadata["Switch test continuation times"] = "; ".join(
                continuation_values
            )
        else:
            self.metadata["Switch test start time"] = timestamp
            self.metadata.setdefault("Switch test continuation times", "")

        session_count = len(self.sessions) + 1
        try:
            session_count = max(
                session_count,
                int(self.metadata.get("Switch test session count", 0)) + 1,
            )
        except (TypeError, ValueError):
            pass
        self.metadata["Switch test session count"] = str(session_count)
        self.metadata["Switch test stop time"] = ""
        self.metadata["Switch test total duration"] = format_duration(
            self.total_seconds
        )

        self._active_session = {
            "start_time": timestamp,
            "stop_time": None,
            "duration_seconds": None,
        }
        self.sessions.append(self._active_session)
        self._active_monotonic = self._monotonic()
        return True

    def stop_session(self):
        """Close the current session and persist its accumulated duration."""
        if not self.active:
            return False

        elapsed = max(0.0, self._monotonic() - self._active_monotonic)
        self.total_seconds += elapsed
        self._active_session["stop_time"] = format_timestamp(self._now())
        self._active_session["duration_seconds"] = round(elapsed, 3)
        self.metadata["Switch test stop time"] = self._active_session["stop_time"]
        self.metadata["Switch test total duration"] = format_duration(
            self.total_seconds
        )
        self._active_session = None
        self._active_monotonic = None
        return True
