"""Classification and operator messages for VISA switch communication errors."""

from dataclasses import dataclass
from enum import Enum

from pyvisa.constants import StatusCode


class SwitchVisaErrorCategory(str, Enum):
    """Stable categories used for switch communication diagnostics."""

    CONNECTION_LOST = "connection_lost"
    RESOURCE_NOT_FOUND = "resource_not_found"
    TIMEOUT = "timeout"
    INVALID_SESSION = "invalid_session"
    RESOURCE_BUSY = "resource_busy"
    INVALID_RESOURCE = "invalid_resource"
    SYSTEM_ERROR = "system_error"
    IO_ERROR = "io_error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SwitchVisaErrorClassification:
    """A transport error translated for both the UI and support logging."""

    category: SwitchVisaErrorCategory
    status_name: str
    status_code: int | None
    operation: str
    command: str
    model: str
    resource_address: str
    disconnection_certainty: str
    reason: str
    recovery_action: str
    technical_error: str

    @property
    def operator_message(self) -> str:
        """Return a concise but actionable message for the operator."""
        subject = self.model or "Optical switch"
        operation = self.operation or "a hardware command"
        technical = "VISA status: %s" % self.status_name
        if self.status_code is not None:
            technical += " (%d)" % self.status_code
        if self.command:
            technical += "\nCommand: %s" % self.command
        if self.technical_error:
            technical += "\nTechnical error: %s" % self.technical_error
        return (
            "%s communication failed during %s.\n\n%s\n\n%s\n\n%s"
            % (subject, operation, self.reason, self.recovery_action, technical)
        )


class SwitchCommunicationError(RuntimeError):
    """A translated VISA failure from an already identified optical switch."""

    communication_failure = True

    def __init__(self, classification: SwitchVisaErrorClassification):
        self.classification = classification
        super().__init__(classification.operator_message)


_STATUS_CATEGORY = {
    StatusCode.error_connection_lost.value: (
        SwitchVisaErrorCategory.CONNECTION_LOST
    ),
    StatusCode.error_resource_not_found.value: (
        SwitchVisaErrorCategory.RESOURCE_NOT_FOUND
    ),
    StatusCode.error_timeout.value: SwitchVisaErrorCategory.TIMEOUT,
    StatusCode.error_invalid_object.value: SwitchVisaErrorCategory.INVALID_SESSION,
    StatusCode.error_resource_busy.value: SwitchVisaErrorCategory.RESOURCE_BUSY,
    StatusCode.error_resource_locked.value: SwitchVisaErrorCategory.RESOURCE_BUSY,
    StatusCode.error_invalid_resource_name.value: (
        SwitchVisaErrorCategory.INVALID_RESOURCE
    ),
    StatusCode.error_system_error.value: SwitchVisaErrorCategory.SYSTEM_ERROR,
    StatusCode.error_io.value: SwitchVisaErrorCategory.IO_ERROR,
}


def _status_name(error, status_code: int | None) -> str:
    abbreviation = str(getattr(error, "abbreviation", "") or "")
    if abbreviation.startswith("VI_"):
        return abbreviation
    if status_code is not None:
        try:
            return "VI_%s" % StatusCode(status_code).name.upper()
        except ValueError:
            pass
    return "VI_ERROR_UNKNOWN"


def _category_reason(category: SwitchVisaErrorCategory) -> tuple[str, str, str]:
    if category == SwitchVisaErrorCategory.CONNECTION_LOST:
        return (
            "The VISA session reported that the connection was lost.",
            "Check switch power and the USB connection, then reconnect the "
            "optical switch.",
            "confirmed",
        )
    if category == SwitchVisaErrorCategory.RESOURCE_NOT_FOUND:
        return (
            "The configured VISA resource is no longer available.",
            "Check switch power, USB connectivity, and the configured VISA "
            "address, then reconnect.",
            "suspected",
        )
    if category == SwitchVisaErrorCategory.TIMEOUT:
        return (
            "The optical switch did not respond before the communication timeout.",
            "Check that no other program is using the switch, then verify power, "
            "USB, and the VISA address before reconnecting.",
            "unknown",
        )
    if category == SwitchVisaErrorCategory.INVALID_SESSION:
        return (
            "The optical switch communication session is no longer valid.",
            "Reconnect the optical switch before starting another hardware operation.",
            "unknown",
        )
    if category == SwitchVisaErrorCategory.RESOURCE_BUSY:
        return (
            "The VISA resource is busy or locked by another application.",
            "Close Santec Terminal and any other program using the switch, then "
            "reconnect it.",
            "unknown",
        )
    if category == SwitchVisaErrorCategory.INVALID_RESOURCE:
        return (
            "The configured VISA resource address is invalid.",
            "Verify the VISA address and installed VISA driver before reconnecting.",
            "unknown",
        )
    if category == SwitchVisaErrorCategory.SYSTEM_ERROR:
        return (
            "A system-level VISA communication error occurred. The switch may "
            "have been disconnected, or its USB/VISA session may have failed.",
            "Check switch power and the USB connection, close other VISA "
            "software, and reconnect the optical switch.",
            "suspected",
        )
    if category == SwitchVisaErrorCategory.IO_ERROR:
        return (
            "VISA reported a low-level input/output communication error.",
            "Check switch power, USB connectivity, and whether another "
            "application has the VISA resource open, then reconnect.",
            "unknown",
        )
    return (
        "Communication with the optical switch failed for an unclassified VISA "
        "reason.",
        "Check switch power and USB connectivity, close other VISA software, "
        "and reconnect the optical switch.",
        "unknown",
    )


def classify_switch_visa_error(
    error,
    *,
    operation: str = "",
    command: str = "",
    model: str = "",
    resource_address: str = "",
) -> SwitchVisaErrorClassification:
    """Classify a PyVISA error without making hardware calls."""
    raw_code = getattr(error, "error_code", None)
    try:
        status_code = int(raw_code) if raw_code is not None else None
    except (TypeError, ValueError):
        status_code = None
    category = _STATUS_CATEGORY.get(status_code, SwitchVisaErrorCategory.UNKNOWN)
    reason, recovery_action, certainty = _category_reason(category)
    return SwitchVisaErrorClassification(
        category=category,
        status_name=_status_name(error, status_code),
        status_code=status_code,
        operation=str(operation or ""),
        command=str(command or ""),
        model=str(model or ""),
        resource_address=str(resource_address or ""),
        disconnection_certainty=certainty,
        reason=reason,
        recovery_action=recovery_action,
        technical_error=str(error or ""),
    )


__all__ = [
    "SwitchCommunicationError",
    "SwitchVisaErrorCategory",
    "SwitchVisaErrorClassification",
    "classify_switch_visa_error",
]
