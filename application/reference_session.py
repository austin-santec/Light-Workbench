"""Session-scoped references authorized for production acquisition.

References are keyed by the connected measurement context.  This keeps a
reference for one wavelength mode from being confused with a reference for a
different mode, while keeping historical run data completely separate from
the active acquisition session.
"""

from domain.reference import ReferenceSnapshot


class ReferenceSession:
    """Track context-specific references for one application session."""

    def __init__(self):
        self._snapshots = {}
        self._active_key = None
        self._calculation_key = None
        self._calculation_previous_key = None
        self.state = "not_referenced"
        self.reason = "Reference has not been calculated."

    @property
    def snapshot(self) -> ReferenceSnapshot | None:
        """Return the snapshot selected for the current acquisition context."""
        if self._active_key is None:
            return None
        return self._snapshots.get(self._active_key)

    @property
    def snapshots(self) -> tuple[ReferenceSnapshot, ...]:
        """Return all cached snapshots without exposing mutable storage."""
        return tuple(self._snapshots.values())

    @property
    def active_key(self):
        return self._active_key

    @staticmethod
    def key_for_snapshot(snapshot: ReferenceSnapshot):
        """Build the default cache key for a persisted reference snapshot."""
        return (
            snapshot.meter_model,
            snapshot.meter_serial,
            snapshot.meter_resource_address,
            snapshot.laser_model,
            snapshot.laser_serial,
            snapshot.wavelength_mode,
            tuple(snapshot.opm_wavelengths_nm),
            tuple(snapshot.source_wavelengths_nm),
            tuple(snapshot.source_ids),
            snapshot.source_profile_id,
        )

    @property
    def is_valid(self) -> bool:
        return self.snapshot is not None and self.snapshot.is_valid and self.state in {
            "valid_calculated",
            "valid_manual_admin",
        }

    def begin_calculation(self, context_key=None) -> None:
        self._calculation_key = context_key if context_key is not None else self._active_key
        self._calculation_previous_key = self._active_key
        self.state = "calculating"
        self.reason = "Reference calculation is in progress."

    def apply(self, snapshot: ReferenceSnapshot, context_key=None) -> None:
        if not snapshot.is_valid:
            raise ValueError("Cannot apply an invalid reference snapshot.")
        key = context_key if context_key is not None else self.key_for_snapshot(snapshot)
        self._snapshots[key] = snapshot
        self._active_key = key
        self._calculation_key = None
        self._calculation_previous_key = None
        self.state = (
            "valid_manual_admin"
            if snapshot.method == "manual_admin"
            else "valid_calculated"
        )
        self.reason = ""

    def activate(self, context_key, reason: str | None = None):
        """Select a cached context without deleting other session references."""
        self._active_key = context_key
        snapshot = self.snapshot
        if snapshot is not None and snapshot.is_valid:
            self.state = (
                "valid_manual_admin"
                if snapshot.method == "manual_admin"
                else "valid_calculated"
            )
            self.reason = ""
        else:
            # Preserve a more specific terminal reason, such as a confirmed
            # hardware disconnect, while the device is still unavailable.
            preserve_invalidation = (
                context_key is None
                and self.reason.startswith("Reference invalidated")
            )
            self.state = "invalidated" if preserve_invalidation else "not_referenced"
            if not preserve_invalidation:
                self.reason = str(reason or "Reference has not been calculated.")
        return snapshot

    def calculation_failed(self, reason: str) -> None:
        """Restore the prior context after a failed replacement calculation."""
        calculation_key = self._calculation_key
        previous_key = self._calculation_previous_key
        self._calculation_key = None
        self._calculation_previous_key = None
        if calculation_key is not None and previous_key == calculation_key:
            self._active_key = previous_key
            previous = self.snapshot
            if previous is not None and previous.is_valid:
                self.state = (
                    "valid_manual_admin"
                    if previous.method == "manual_admin"
                    else "valid_calculated"
                )
                self.reason = "%s The previous valid reference remains active." % reason
                return
        self._active_key = calculation_key
        self.state = "invalidated"
        self.reason = str(reason or "Reference must be recalculated.")

    def invalidate(self, reason: str, *, clear_all: bool = False) -> None:
        """Invalidate the active context, optionally clearing the session bank."""
        if clear_all:
            self._snapshots.clear()
            self._active_key = None
        elif self._active_key is not None:
            self._snapshots.pop(self._active_key, None)
        self._calculation_key = None
        self._calculation_previous_key = None
        self.state = "invalidated"
        self.reason = str(reason or "Reference must be recalculated.")

    def clear_all(self, reason: str) -> None:
        self.invalidate(reason, clear_all=True)


__all__ = ["ReferenceSession"]
