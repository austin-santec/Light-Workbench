"""Application state for references authorized for production acquisition."""

from domain.reference import ReferenceSnapshot


class ReferenceSession:
    """Track reference lifecycle separately from editable display widgets."""

    def __init__(self):
        self.snapshot: ReferenceSnapshot | None = None
        self.state = "not_referenced"
        self.reason = "Reference has not been calculated."

    @property
    def is_valid(self) -> bool:
        return self.snapshot is not None and self.snapshot.is_valid and self.state in {
            "valid_calculated",
            "valid_manual_admin",
        }

    def begin_calculation(self) -> None:
        self.state = "calculating"
        self.reason = "Reference calculation is in progress."

    def apply(self, snapshot: ReferenceSnapshot) -> None:
        if not snapshot.is_valid:
            raise ValueError("Cannot apply an invalid reference snapshot.")
        self.snapshot = snapshot
        self.state = (
            "valid_manual_admin"
            if snapshot.method == "manual_admin"
            else "valid_calculated"
        )
        self.reason = ""

    def invalidate(self, reason: str) -> None:
        self.snapshot = None
        self.state = "invalidated"
        self.reason = str(reason or "Reference must be recalculated.")


__all__ = ["ReferenceSession"]
