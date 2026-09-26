"""Compatibility facade for the Live IL presentation module."""

from ui.live_il_reading import (
    LIVE_UPDATE_PAUSE_MS,
    LiveILReadingDialog,
    LiveILReadingWorker,
)

__all__ = [
    "LIVE_UPDATE_PAUSE_MS",
    "LiveILReadingDialog",
    "LiveILReadingWorker",
]
