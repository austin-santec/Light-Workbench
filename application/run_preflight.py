"""Pure validation for the production hardware-run start workflow.

The preflight layer only inspects values supplied by the UI and the existing
connection/reference state.  It does not touch hardware, persistence, or Qt,
so a rejected start cannot create a partial run or activate an instrument.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from application.hardware_planning import HardwareRunPlan, build_hardware_run_plan
from domain.models import ChannelMode


class RunPreflightIssueCategory(str, Enum):
    """Technician-facing groups used to explain a blocked start."""

    METADATA = "metadata"
    CHANNELS = "channels"
    HARDWARE = "hardware"
    REFERENCE = "reference"


@dataclass(frozen=True)
class RunPreflightIssue:
    """One unresolved item found before a production run can start."""

    code: str
    category: RunPreflightIssueCategory
    label: str
    message: str
    field_id: str = ""
    admin_metadata_bypassable: bool = False


@dataclass(frozen=True)
class RunPreflightResult:
    """All normalized start decisions and issues returned by preflight."""

    issues: tuple[RunPreflightIssue, ...] = ()
    plan: HardwareRunPlan | None = None

    @property
    def metadata_issues(self) -> tuple[RunPreflightIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.category is RunPreflightIssueCategory.METADATA
        )

    @property
    def non_metadata_issues(self) -> tuple[RunPreflightIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.category is not RunPreflightIssueCategory.METADATA
        )

    @property
    def blocking_issues(self) -> tuple[RunPreflightIssue, ...]:
        """Return issues that cannot be bypassed by Admin Mode."""
        return tuple(
            issue for issue in self.issues if not issue.admin_metadata_bypassable
        )

    @property
    def is_valid_for_normal_operator(self) -> bool:
        return not self.issues

    @property
    def is_valid_for_admin(self) -> bool:
        return not self.blocking_issues


def _metadata_issue(code, label, field_id):
    return RunPreflightIssue(
        code=code,
        category=RunPreflightIssueCategory.METADATA,
        label=label,
        message="Enter %s." % label.lower(),
        field_id=field_id,
        admin_metadata_bypassable=True,
    )


def _reference_issues(
    *,
    admin_mode: bool,
    reference_valid: bool,
    reference_state: str,
    reference_method: str,
    reference_hardware_matches: bool,
    wavelengths: tuple[int, int] = (1310, 1550),
):
    wavelength_text = "%d nm and %d nm" % tuple(wavelengths)
    if not reference_valid:
        if reference_state == "invalidated":
            return [
                RunPreflightIssue(
                    "reference_invalidated",
                    RunPreflightIssueCategory.REFERENCE,
                    "Reference",
                    "Recalculate the %s reference; the current reference was invalidated."
                    % wavelength_text,
                    "reference_1310",
                )
            ]
        return [
            RunPreflightIssue(
                "reference_not_calculated",
                RunPreflightIssueCategory.REFERENCE,
                "Reference",
                "Calculate the %s reference before starting the run."
                % wavelength_text,
                "reference_1310",
            )
        ]

    if reference_method == "manual_admin" and not admin_mode:
        # Manual references are deliberately restricted to an authenticated
        # administrator by the caller; the normal operator path requires a
        # calculated reference.
        return [
            RunPreflightIssue(
                "reference_not_authorized",
                RunPreflightIssueCategory.REFERENCE,
                "Reference",
                "Use a calculated reference before starting a production run.",
                "reference_1310",
            )
        ]

    if not reference_hardware_matches:
        return [
            RunPreflightIssue(
                "reference_hardware_mismatch",
                RunPreflightIssueCategory.REFERENCE,
                "Reference",
                "Recalculate the reference for the currently connected measurement hardware.",
                "reference_1310",
            )
        ]
    return []


def validate_run_preflight(
    *,
    admin_mode: bool,
    metadata: dict[str, Any],
    run_number: Any,
    channel_mode: ChannelMode | str | int,
    single_channel: Any = 1,
    channel_ranges: str = "",
    manual_channel_order: bool = False,
    hardware_ready: bool,
    reference_valid: bool,
    reference_state: str = "",
    reference_method: str = "",
    reference_hardware_matches: bool = True,
    wavelengths: tuple[int, int] = (1310, 1550),
) -> RunPreflightResult:
    """Validate every non-side-effecting condition for a production start."""
    issues = []
    plan = None

    specific_mode = (
        channel_mode == ChannelMode.SPECIFIC_CHANNELS
        or str(channel_mode).strip() == ChannelMode.SPECIFIC_CHANNELS.value
        or channel_mode == 2
    )
    if specific_mode and not str(channel_ranges or "").strip():
        issues.append(
            RunPreflightIssue(
                "missing_channel_selection",
                RunPreflightIssueCategory.CHANNELS,
                "Channels/ranges",
                "Enter at least one channel or range.",
                "channel_ranges",
            )
        )

    if not any(issue.code == "missing_channel_selection" for issue in issues):
        try:
            plan = build_hardware_run_plan(
                channel_mode,
                single_channel=single_channel,
                channel_ranges=channel_ranges,
                manual_channel_order=manual_channel_order,
            )
        except (TypeError, ValueError) as error:
            issues.append(
                RunPreflightIssue(
                    "invalid_channel_selection",
                    RunPreflightIssueCategory.CHANNELS,
                    "Channel selection",
                    str(error),
                    "channel_mode",
                )
            )

    field_values = (
        ("missing_main_board_serial", "Main board serial", "main_board_serial"),
        ("missing_switch_serial", "Switch serial", "switch_serial"),
        ("missing_part_number", "Part number", "part_number"),
        ("missing_operating_band", "Operating band", "operating_band"),
        ("missing_tested_by", "Tested by", "tested_by"),
    )
    for code, label, field_id in field_values:
        if not str(metadata.get(label) or "").strip():
            issues.append(_metadata_issue(code, label, field_id))

    if str(metadata.get("Operating band") or "").strip() not in {
        "O band",
        "C band",
    }:
        issues.append(
            RunPreflightIssue(
                "invalid_operating_band",
                RunPreflightIssueCategory.METADATA,
                "Operating band",
                "Select O band or C band.",
                "operating_band",
                admin_metadata_bypassable=True,
            )
        )

    try:
        normalized_run_number = int(run_number)
    except (TypeError, ValueError):
        normalized_run_number = 0
    if normalized_run_number < 1:
        issues.append(
            _metadata_issue("invalid_run_number", "Run number", "run_number")
        )

    if not hardware_ready:
        issues.append(
            RunPreflightIssue(
                "hardware_not_ready",
                RunPreflightIssueCategory.HARDWARE,
                "Connected hardware",
                "Connect the measurement hardware and optical switch before starting the run.",
                "hardware",
            )
        )

    issues.extend(
        _reference_issues(
            admin_mode=admin_mode,
            reference_valid=reference_valid,
            reference_state=reference_state,
            reference_method=reference_method,
            reference_hardware_matches=reference_hardware_matches,
            wavelengths=wavelengths,
        )
    )

    # Admin Mode changes only the policy for descriptive metadata. It never
    # removes channel, hardware, or reference safeguards.
    if admin_mode:
        issues = list(issues)
    return RunPreflightResult(tuple(issues), plan)


__all__ = [
    "RunPreflightIssue",
    "RunPreflightIssueCategory",
    "RunPreflightResult",
    "validate_run_preflight",
]
