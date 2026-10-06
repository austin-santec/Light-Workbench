# Light Workbench requirements checklist

This is a simple working checklist based on the detailed assessment in
[`Requirements.md`](../Requirements.md). It is meant for quick personal use.
Refer to the full document when you need the exact requirement wording,
implementation evidence, or technical details.

Last synchronized with the requirements assessment: **2026-10-05**.

Reference enforcement update: FUN-012 and FUN-013 are complete in version
1.16.1. Production runs require a valid calculated or explicitly
Admin-authorized manual reference. Each accepted reading stores the immutable
reference snapshot used for its calculation, and legacy loaded references are
review-only until a new reference is established.

Validation update: calculated references below -40.0 dBm are rejected, while
negative insertion-loss samples remain visible but cannot be written. Live
negative samples use coalesced support-log episodes rather than repeated modal
warnings.

Implementation note: model-specific controlled criteria and session-only Admin
Mode are now implemented. The detailed requirement counts above should be
re-audited against the full requirements document before a formal release.

Metadata-entry update: connecting a supported OSX now fills Main board serial
from its existing identity response and attempts part-number lookup in the
background. Lookup failure does not change hardware readiness, and loaded or
active run metadata remains protected.

## Quick status

- [x] **7 completed requirements**
- [ ] **30 partially completed requirements**
- [ ] **20 requirements not yet implemented**
- **57 total requirements**

`MVP` means needed for the first requirements-compliant release. `Later` means
the source workbook assigns it to the follow-on R1 release.

## Completed

These already have the required core behavior. Hardware-dependent items may
still need to be repeated during final release testing.

- [x] **FUN-002 — Test channels in sequence.** `[MVP]`
- [x] **FUN-009a — Connect to the ILM-100/OP815 and enter remote mode.** `[MVP]`
- [x] **FUN-009b — Add an operator action to leave ILM remote mode on demand.** `[MVP]`
  - Connect Hardware provides independent and all-hardware disconnect actions;
    disconnecting measurement hardware safely leaves remote mode and releases
    the driver session.
- [x] **FUN-027 — Keep logical channels separate from physical switch ports.** `[MVP]`
- [x] **FUN-047 — Automatically save after every written reading or retest.** `[MVP]`
- [x] **FUN-056 — Keep run data safe if report/COC export fails.** `[MVP]`
- [x] **FUN-060 — Create useful support logs without exposing confidential data.** `[Later]`
  - Always-on local JSONL covers workflows, hardware commands, measurements,
    persistence, exports, and failures using allowlisted/redacted fields.
    `Help > Support Logs` provides status and explicit local bundle export.

## Partially completed

Each item has useful behavior today, but the full requirement is not finished.
Check an item only after the **Still needed** portion is implemented and tested.

- [ ] **FUN-003 — Retest selected channels before the report is final.** `[MVP]`
  - Already works: Completed table rows can be selected and retested.
  - Still needed: Define a clear finalization step and support the complete
    intended retest workflow before finalization.

- [ ] **FUN-006 — Calculate the final channel result using every required wavelength.** `[MVP]`
  - Already works: Both wavelengths are checked against the current warning limit.
  - Still needed: Use controlled, wavelength-specific warning and failure limits
    and calculate the required final status.

- [ ] **FUN-007 — Pause, resume, abort, and safely restart a test.** `[Later]`
  - Already works: A run can be stopped and continued without losing written rows.
  - Still needed: Add a defined pause/resume workflow and safe arbitrary-channel
    restart after an interruption.

- [ ] **FUN-010 — Show ILM identity, status, and useful connection errors.** `[MVP]`
  - Already works: Connected hardware status shows identity and connection state.
  - Still needed: Give consistent, device-specific recovery instructions for
    connection failures.

- [ ] **FUN-012 — Require a reference for every wavelength before testing.** `[MVP]`
  - Already works: References can be calculated or entered manually.
  - Still needed: Prevent DUT testing until a valid reference has been completed.

- [ ] **FUN-014 — Reject invalid or unreliable ILM readings.** `[MVP]`
  - Already works: Communication failures, missing wavelength values, and actual
    wavelength mismatches are handled.
  - Still needed: Detect stale, saturated, under-range, and other invalid readings
    using defined validity rules.

- [ ] **FUN-015 — Find the selected OSX model and show its connection status.** `[MVP]`
  - Already works: Verified OSX-100 and OSX-150 devices are detected using manual,
    last-known, and targeted USB VISA discovery, with LF/CRLF identity probing,
    channel-count validation, and detailed identity/status reporting.
  - Still needed: Add an operator-selected family and family-mismatch workflow.

- [ ] **FUN-017 — Route a channel and confirm the switch finished moving.** `[MVP]`
  - Already works: The application sends the route command and reads back the
    active physical port.
  - Still needed: Verify that the returned route matches the expected authoritative
    logical-to-physical mapping.

- [ ] **FUN-019 — Configure and log hardware timeouts, retries, and delays.** `[Later]`
  - Already works: Important delays are named constants and diagnostics log some
    meter timing.
  - Still needed: Put production timing/retry settings in controlled configuration
    and log switch commands and retry results.

- [ ] **FUN-020 — Recover from a lost hardware connection.** `[Later]`
  - Already works: Previously written readings remain saved and the run can be
    continued later.
  - Still needed: Add guided reconnection during the interrupted session and
    confirm the switch route before resuming.

- [ ] **FUN-025 — Use an optimization warning stricter than the failure limit.** `[MVP]`
  - Already works: The warning threshold drives over-limit and replacement analysis.
  - Still needed: Separate the controlled optimization warning from the published
    absolute failure limit.

- [ ] **FUN-026 — Show Pass, Optimization Review, Fail, Untested, and Invalid.** `[MVP]`
  - Already works: The application shows within-limit, over-limit, and pending states.
  - Still needed: Implement all five required result states consistently.

- [ ] **FUN-030 — Rank spare ports using both wavelengths and explain the ranking.** `[Later]`
  - Already works: Suggestions use the worst of the two losses and expected improvement.
  - Still needed: Show the full calculation and use the final defined ranking policy.

- [ ] **FUN-031 — Change and document a logical-to-physical port mapping.** `[MVP]`
  - Already works: Current Port and Replacement Port can be recorded.
  - Still needed: Apply or verify the actual switch mapping and record logical
    channel, reason, operator, and time.

- [ ] **FUN-033 — Prevent duplicate physical-port assignments.** `[MVP]`
  - Already works: Duplicate replacement-port entries are rejected.
  - Still needed: Validate the entire active channel/spare mapping, not only the
    manually entered replacement list.

- [ ] **FUN-034 — Show available spare ports and their latest test result.** `[MVP]`
  - Already works: Designated spares and replacement suggestions are displayed.
  - Still needed: Maintain an authoritative assigned/unassigned spare list with
    each spare's latest measurement status.

- [ ] **FUN-037 — Fill a selected Excel report automatically.** `[MVP]`
  - Already works: The current fixed COC template can be populated automatically.
  - Still needed: Support the required selected templates, including OSX-100 formats.

- [ ] **FUN-039 — Put all required run information in the report.** `[MVP]`
  - Already works: The report includes part number, serial, date, tester, and both
    wavelength results.
  - Still needed: Add family, channel count, criteria revision, equipment identity,
    final disposition, and any other missing required fields.

- [ ] **FUN-041 — Save complete raw session data separately from the report.** `[MVP]`
  - Already works: CSV/JSON run data is separate from the COC workbook.
  - Still needed: Preserve every attempt, error, validity result, and required
    trace information instead of only the latest written channel value.

- [ ] **FUN-043 — Use configurable report names without overwriting files.** `[MVP]`
  - Already works: Existing COC files receive a numeric suffix instead of being overwritten.
  - Still needed: Make the report naming pattern configurable.

- [ ] **FUN-046 — Make every measurement fully traceable.** `[MVP]`
  - Already works: Saved readings include run identity, logical channel, physical
    port, and both IL values.
  - Still needed: Add stable session/measurement IDs, timestamps, attempt number,
    instrument identity, units, and validity.

- [ ] **FUN-050 — Validate required setup and report information.** `[MVP]`
  - Already works: Missing metadata and zero references produce warnings, and the
    exporter checks some required fields and template details.
  - Still needed: Enforce all required metadata, criteria, completeness, and path
    checks at the correct workflow points.

- [ ] **FUN-051 — Show all important testing status on screen.** `[MVP]`
  - Already works: Unit identity, connected devices, channel, latest readings, and
    progress are visible.
  - Still needed: Show reference status, active wavelength, and the complete required
    result state clearly.

- [ ] **FUN-052 — Provide all normal operator actions in the UI.** `[MVP]`
  - Already works: Normal testing, retesting, diagnostics, and export have UI controls.
  - Still needed: Add the missing family, criteria, mapping, final-result selection,
    and report-preview actions as those features are implemented.

- [ ] **FUN-053 — Give clear hardware/channel errors and recovery guidance.** `[MVP]`
  - Already works: Many errors identify the immediate problem.
  - Still needed: Standardize device- and channel-specific messages and explain what
    the operator should do next.

- [ ] **FUN-054 — Confirm actions that could replace or clear important data.** `[MVP]`
  - Already works: Some new-run, continuation, and changed-identity actions are confirmed.
  - Still needed: Cover session clearing, family changes, and replacing the selected
    final result with a consistent confirmation policy.

- [ ] **FUN-055 — Do not move or read hardware until setup is confirmed.** `[MVP]`
  - Already works: Hardware is connected before routing and setup warnings are shown.
  - Still needed: Enforce the final required configuration/reference gate instead of
    allowing required setup to be bypassed.

- [ ] **FUN-057 — Recover after a crash without losing or duplicating results.** `[Later]`
  - Already works: Run writes are atomic and saved runs can be continued manually.
  - Still needed: Add formal crash recovery/reconciliation and forced-termination tests.

- [ ] **FUN-058 — Identify operators and control restricted actions by role.** `[Later]`
  - Already works: Tester initials are recorded.
  - Still needed: Add authenticated identity, roles, and attributable restricted actions.

- [ ] **FUN-059 — Keep commands and rules in version-controlled configuration.** `[Later]`
  - Already works: Hardware adapters, profiles, timing constants, and exporters are
    separated into appropriate modules.
  - Still needed: Add versioned configuration for criteria, report mappings, naming
    rules, and remaining hardware behavior.

## Not yet implemented

These requirements need a new complete capability or data model. Some have
technical questions that must be answered before implementation.

- [ ] **FUN-001 — Add an OSX-100/OSX-150 family selector and family-specific workflow.** `[MVP]`
- [ ] **FUN-004 — Keep every retest attempt and explicitly identify the final result.** `[MVP]`
- [ ] **FUN-005 — Let the user select supported wavelengths and use compatible equipment.** `[MVP]`
- [ ] **FUN-008 — Block incomplete final reports unless a defined exception and reason are recorded.** `[MVP]`
- [ ] **FUN-013 — Store the reference values, time, instrument, and validity with the run.** `[MVP]`
- [ ] **FUN-016 — Detect a switch-family mismatch and handle the defined exception workflow.** `[Later]`
- [ ] **FUN-018 — Support configurable USB/serial/Ethernet transports where the hardware allows it.** `[Later]`
- [ ] **FUN-021 — Store product acceptance limits in controlled configuration.** `[MVP]`
- [ ] **FUN-022 — Define criteria by family, channel count, wavelength, warning, and failure limit.** `[MVP]`
- [ ] **FUN-023 — Save the criteria-set name and revision with every run.** `[MVP]`
- [ ] **FUN-024 — Restrict criteria changes to the defined authorized roles.** `[Later]`
- [ ] **FUN-032 — Force a new two-wavelength test after a port mapping changes.** `[MVP]`
- [ ] **FUN-035 — Include the final port mapping and replacements in the final report.** `[MVP]`
- [ ] **FUN-036 — Keep both pre-optimization and post-optimization measurements.** `[Later]`
- [ ] **FUN-038 — Configure report field/column mappings separately for each template.** `[Later]`
- [ ] **FUN-040 — Resize report rows for different channel counts without breaking the workbook.** `[MVP]`
- [ ] **FUN-042 — Preview the final report before saving it.** `[Later]`
- [ ] **FUN-044 — Optionally export the final report as a PDF.** `[Later]`
- [ ] **FUN-045 — Mark retested channels, report only the chosen final values, and preserve history.** `[MVP]`
- [ ] **FUN-048 — Keep an append-only event history for connections, references, readings, errors, mappings, overrides, and reports.** `[Later]`

## Technical answers still needed

These are not separate software features, but several checklist items depend
on them. Check each one after the rule or equipment choice is clearly defined.

- [ ] Define required OSX-100 single-mode and multimode wavelengths and channel counts.
- [ ] Identify the equipment and control method for any required 850/1300 nm testing.
- [ ] Define warning and failure limits for every product/wavelength/channel range.
- [ ] Decide whether a value exactly equal to a limit passes or exceeds the limit.
- [ ] Define the reference procedure, maximum reference age, and re-reference rules.
- [ ] Decide how the final retest result is selected, including an invalid latest retest.
- [ ] Decide whether Light Workbench changes switch mappings or verifies changes made elsewhere.
- [ ] Define required spare counts, when a spare counts as tested, and how spares are ranked.
- [ ] Define whether incomplete reports are always blocked or can use a recorded exception.
- [ ] Identify every required Excel template, supported channel-count range, and PDF rule.
- [ ] Define supported Windows, VISA, driver, switch firmware, timeout, and reconnect cases.

## Suggested implementation order

This order avoids building reports and UI around data that will later need to change.

1. [ ] Define the unanswered technical rules above.
2. [ ] Add product family, wavelengths, and controlled criteria.
3. [ ] Add the complete session, reference, measurement-attempt, and final-result model.
4. [ ] Finish measurement validity, result states, preflight checks, and recovery.
5. [ ] Add authoritative switch mapping and spare handling.
6. [ ] Finish variable-length reports, final mapping, history, preview, and PDF options.
7. [ ] Add roles, complete audit events, support logs, and final hardware/UAT coverage.

When an item is completed, update both this checklist and the detailed status in
[`Requirements.md`](../Requirements.md) so they stay consistent.
