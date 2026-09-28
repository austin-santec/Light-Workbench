"""Shared application-level pacing defaults for automatic live readings."""

# This delay starts only after a complete 1310 nm and 1550 nm measurement.
# It paces repeated software requests and is separate from instrument settling.
LIVE_UPDATE_PAUSE_MS = 250
LIVE_WRITE_INTERVAL_SECONDS = LIVE_UPDATE_PAUSE_MS / 1000.0
