"""Asynchronous application boundary for main-board part-number lookup."""

from collections.abc import Callable
from pathlib import Path
import threading

from PyQt5.QtCore import QObject, pyqtSignal


def classify_part_lookup_error(error: Exception) -> str:
    """Return a stable support category for the existing lookup exceptions."""
    message = str(error).casefold()
    if isinstance(error, FileNotFoundError):
        return "lookup_folder_unavailable"
    if isinstance(error, LookupError):
        if "more than one" in message:
            return "multiple_matches"
        if "does not contain a part number" in message:
            return "missing_part_number"
        return "no_matching_serial"
    if isinstance(error, ValueError):
        return "invalid_serial"
    if isinstance(error, OSError):
        return "filesystem_error"
    return "unexpected_error"


class PartNumberLookupController(QObject):
    """Run network-backed part lookup without blocking the Qt UI thread."""

    succeeded = pyqtSignal(int, str, str)
    failed = pyqtSignal(int, str, str, str)

    def __init__(
        self,
        lookup_function: Callable[[str, str | Path], str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._lookup_function = lookup_function
        self._lock = threading.Lock()
        self._next_request_id = 0
        self._closed = threading.Event()

    def start(self, serial: str, lookup_root: str | Path) -> int:
        """Start one daemon lookup and return its monotonically increasing ID."""
        with self._lock:
            self._next_request_id += 1
            request_id = self._next_request_id
        thread = threading.Thread(
            target=self._run_lookup,
            args=(request_id, str(serial), Path(lookup_root)),
            name="part-number-lookup-%d" % request_id,
            daemon=True,
        )
        thread.start()
        return request_id

    def close(self) -> None:
        """Suppress results after the owning window has closed."""
        self._closed.set()

    def _run_lookup(
        self,
        request_id: int,
        serial: str,
        lookup_root: Path,
    ) -> None:
        try:
            part_number = self._lookup_function(serial, lookup_root)
        except Exception as error:  # Deliberate worker boundary.
            if not self._closed.is_set():
                try:
                    self.failed.emit(
                        request_id,
                        serial,
                        classify_part_lookup_error(error),
                        str(error),
                    )
                except RuntimeError:
                    pass
            return

        if not self._closed.is_set():
            try:
                self.succeeded.emit(request_id, serial, str(part_number))
            except RuntimeError:
                pass


__all__ = ["PartNumberLookupController", "classify_part_lookup_error"]
