"""Monotonic session clock and single-in-flight background checkpoint writer."""

from datetime import datetime, timedelta
from collections.abc import Callable
import threading
import time
from uuid import uuid4

from PyQt5.QtCore import QObject, pyqtSignal

from domain.database_records import utc_now
from domain.run_sessions import RunSessionCheckpoint
from application.database_repositories import RunSessionRepository


class RunSessionClock:
    def __init__(
        self,
        run_id: int,
        *,
        now: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.run_id = run_id
        self.client_session_uuid = uuid4()
        self._now = now
        self._monotonic = monotonic
        self.started_at_utc = now()
        self._started_monotonic = monotonic()
        self._stopped = None

    def checkpoint(self) -> RunSessionCheckpoint:
        if self._stopped is not None:
            return self._stopped
        elapsed = max(0, int((self._monotonic() - self._started_monotonic) * 1000))
        return RunSessionCheckpoint(
            self.run_id, self.client_session_uuid,
            max(self._now(), self.started_at_utc + timedelta(milliseconds=elapsed)),
            elapsed,
        )

    def stop(self) -> RunSessionCheckpoint:
        if self._stopped is None:
            self._stopped = self.checkpoint()
        return self._stopped


class TimingCheckpointWriter(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object, str)

    def __init__(
        self, repository: RunSessionRepository, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self._lock = threading.Lock()
        self._busy = False
        self._closed = threading.Event()

    def submit(self, checkpoint: RunSessionCheckpoint) -> bool:
        with self._lock:
            if self._busy or self._closed.is_set():
                return False
            self._busy = True
        try:
            threading.Thread(target=self._write, args=(checkpoint,), daemon=True).start()
        except RuntimeError as error:
            with self._lock:
                self._busy = False
            if not self._closed.is_set():
                self.failed.emit(checkpoint, str(error))
            return False
        return True

    def close(self) -> None:
        self._closed.set()

    def _write(self, checkpoint):
        try:
            result = self.repository.checkpoint_test_session(checkpoint)
        except Exception as error:  # Background persistence boundary, not hardware.
            if not self._closed.is_set():
                try:
                    self.failed.emit(checkpoint, str(error))
                except RuntimeError:
                    pass  # Qt owner was deleted during shutdown.
        else:
            if not self._closed.is_set():
                try:
                    self.succeeded.emit(result)
                except RuntimeError:
                    pass
        finally:
            with self._lock:
                self._busy = False
