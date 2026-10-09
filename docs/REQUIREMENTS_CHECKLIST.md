# Light Workbench RevB requirements checklist

This is the short working checklist for
[`OSX_IL_Test_Software_Requirements_RevB.xlsx`](../temp%20docs/OSX_IL_Test_Software_Requirements_RevB.xlsx).
See [`Requirements.md`](../Requirements.md) for the full wording, evidence, and roadmap.

**Last reviewed:** 2026-10-08

**Software baseline:** Light Workbench 1.27.0

**RevB total:** 46 requirement rows

## Quick status

- [x] **19 implemented**
- [ ] **24 partially implemented**
- [ ] **3 not implemented**

RevB uses `FUN-009` twice and `FUN-014` twice. This checklist adds `a` and `b`
only to distinguish those duplicate rows. Requirements removed from RevB are no
longer tracked here.

The FUN-004 retest-history row below is retained for traceability to the
original RevB assessment. It is implemented in the 1.22.0 baseline through
append-only accepted-attempt storage and the Run information history viewer.

## Implemented

These capabilities exist in the current production path. Hardware-dependent
items still need representative equipment testing before formal acceptance.

- [x] **FUN-002 — Test channels sequentially.** `[MVP]`
- [x] **FUN-005 — Select 1310/1550 or 850/1300 measurement wavelengths.** `[MVP]`
  - SM and MM are manually selected before referencing/testing. New records use the selected mode and its independent model/mode limits; older compatibility records remain readable.
- [x] **FUN-008 — Block a final report when required channels are untested.** `[MVP]`
- [x] **FUN-009a — Connect the ILM-100 through the OP815 interface and keep it remote.** `[MVP]`
- [x] **FUN-009b — Let the user disconnect the ILM and return it to local operation.** `[MVP]`
- [x] **FUN-012 — Require a two-wavelength reference before production testing.** `[MVP]`
- [x] **FUN-013 — Store reference values, time, method, and meter identity.** `[MVP]`
- [x] **FUN-014b — Let an administrator edit minimum, warning, and failure limits.** `[MVP]`
- [x] **FUN-015 — Connect supported OSX-100/OSX-150 switches and show status.** `[MVP]`
  - Main board serial can be filled from switch identity and part-number lookup starts automatically.
- [x] **FUN-021 — Keep model limits in controlled INI configuration.** `[MVP]`
- [x] **FUN-023 — Save the active criteria profile and revision with the run.** `[MVP]`
- [x] **FUN-025 — Use the OSX-150 optimization band below the failure limit.** `[MVP]`
- [x] **FUN-027 — Keep logical channels separate from physical ports.** `[MVP]`
- [x] **FUN-040 — Fit COC rows to the requested front-panel channel count.** `[MVP]`
- [x] **FUN-047 — Autosave after every accepted reading or retest.** `[MVP]`
- [x] **FUN-055 — Block Start Run until hardware, setup, channels, and reference are valid.** `[MVP]`
  - Normal operators cannot bypass preflight. Admin Mode can bypass only missing descriptive metadata.
- [x] **FUN-056 — Preserve run data when COC export fails.** `[MVP]`
- [x] **FUN-060 — Generate redacted engineering support logs and support bundles.** `[MVP]`
  - Daily logs are compressed after seven days, retained indefinitely, and warn above 500 MB.

## Partially implemented

Each item already has useful behavior, but the noted work remains.

- [ ] **FUN-001 — Require OSX-100 or OSX-150 selection before testing.** `[MVP]`
  - Works now: connected hardware is detected and assigned the matching profile.
  - Next: add the required operator family selection and mismatch handling.

- [ ] **FUN-003 — Retest one or more selected channels before finalization.** `[MVP]`
  - Works now: completed rows can be selected and retested.
  - Next: define and enforce an explicit report-finalized session state.

- [ ] **FUN-006 — Calculate an overall result from both wavelengths.** `[MVP]`
  - Works now: both wavelengths use model-specific too-good, optimization, and failure checks.
  - Next: add wavelength/channel-count criteria and the complete final disposition model.

- [ ] **FUN-007 — Abort, pause, resume, and safely restart at a chosen channel.** `[R1]`
  - Works now: Stop preserves written data and a saved run can be continued.
  - Next: add a formal pause/recovery state and guided arbitrary-channel restart.

- [ ] **FUN-010 — Show ILM status, identity, and actionable errors.** `[MVP]`
  - Works now: connection state, model, and serial are shown when available; optical-switch VISA failures are classified with recovery guidance.
  - Next: standardize recovery guidance for every supported failure and firmware case.

- [ ] **FUN-014a — Reject every stale, saturated, under-range, missing, or invalid reading.** `[MVP]`
  - Works now: missing wavelengths, hardware failures, wavelength mismatches, dark references, and negative loss are rejected.
  - Next: define and implement stale, saturation, and general under-range rules.

- [ ] **FUN-017 — Confirm switch routing before measurement.** `[R2]`
  - Works now: route command, settling delay, and active-port query occur before reading.
  - Next: complete authoritative route verification and hardware/firmware validation.

- [ ] **FUN-019 — Configure and log timeouts, retries, and settling delays.** `[R1]`
  - Works now: timing constants are isolated and hardware traces record timing/commands.
  - Next: move approved values and retry policy into controlled configuration.

- [ ] **FUN-020 — Recover from communication loss without losing completed data.** `[R1]`
  - Works now: written rows survive and the run can be loaded and continued.
  - Next: guide reconnection inside the interrupted workflow and confirm the route before resume.

- [ ] **FUN-026 — Show Pass, Optimization Review, Fail, Untested, and Invalid.** `[MVP]`
  - Works now: pending, too-good, optimization, and failure conditions are shown.
  - Next: use one consistent five-state model and persist Invalid Measurement evidence.

- [ ] **FUN-030 — Rank spare channels using both wavelengths and show the basis.** `[R1]`
  - Works now: analysis uses both wavelengths and separates recommended/optional replacements.
  - Next: approve and display the complete ranking calculation.

- [ ] **FUN-031 — Document a manually performed replacement and record the complete change.** `[MVP]`
  - Works now: Current Port → Replacement Port, reason, operator, timestamp, and append-only replacement history are stored per unit. Repeated changes can be tracked as chains such as 14 → 41 → 43.
  - Important boundary: Light Workbench intentionally does not execute, identify, or verify the hardware mapping. The requirement wording should be clarified to reflect this manual process.

- [ ] **FUN-034 — Show unassigned spares and their latest result.** `[MVP]`
  - Works now: designated spares and replacement suggestions are visible.
  - Next: maintain an authoritative assigned/unassigned list with latest status.

- [ ] **FUN-035 — Put the final map and replacements in the debug file.** `[MVP]`
  - Works now: run JSON/support logs contain logical/physical routes and unit data contains replacements.
  - Next: export one complete final-map debug view that clearly marks replacements.

- [ ] **FUN-037 — Populate a selected XLSX report automatically.** `[MVP]`
  - Works now: approved OSX-150 templates are populated without manual data copying.
  - Next: support the required OSX-100 report template/workflow.

- [ ] **FUN-041 — Save complete raw session data separately from the report.** `[MVP]`
  - Works now: run CSV/JSON and support logs are separate from the COC.
  - Next: preserve all attempts, invalid readings, errors, and final-result links authoritatively.

- [ ] **FUN-043 — Use configurable timestamped report names without overwriting.** `[MVP]`
  - Works now: filenames contain model, serial, and timestamp; collisions receive a suffix.
  - Next: make the naming pattern controlled/configurable.

- [ ] **FUN-046 — Make every measurement fully traceable.** `[MVP]`
  - Works now: accepted results include run/product identity, logical/physical channel, both values, and reference/meter evidence.
  - Next: add authoritative timestamps, attempt numbers, units, validity, and rejected samples.

- [ ] **FUN-050 — Validate required metadata and paths before start and report finalization.** `[MVP]`
  - Works now: Start Run preflight blocks incomplete setup before side effects, and COC preparation validates source data and template capacity.
  - Next: complete controlled output-path and finalization validation.

- [ ] **FUN-051 — Show all required run status on one screen.** `[MVP]`
  - Works now: unit/run, hardware, reference, channel, dual-wavelength reading, progress, and limits are visible.
  - Next: show active wavelength and a unified final disposition state.

- [ ] **FUN-053 — Give device/channel-specific errors and corrective actions.** `[R2]`
  - Works now: switch VISA failures identify the operation, preserve the status code, and suggest recovery.
  - Next: create a reviewed error/recovery catalog and fault-test matrix.

- [ ] **FUN-057 — Recover automatically after an unexpected application exit.** `[MVP]`
  - Works now: accepted rows are atomically saved and can be continued manually.
  - Next: add automatic recovery/reconciliation and forced-termination tests.

- [ ] **FUN-058 — Capture operator identity and authorize restricted actions by role.** `[R1]`
  - Works now: Tested by is required for normal runs; Admin Mode protects restricted changes.
  - Next: replace shared initials/password with attributable authenticated roles.

- [ ] **FUN-059 — Isolate commands and rules in version-controlled configuration.** `[R1]`
  - Works now: hardware, timing, profiles, export, and naming logic are separated by module.
  - Next: move remaining hard-coded/per-user rules into controlled versioned configuration.

## Not implemented

- [ ] **FUN-004 — Preserve every retest attempt and choose the active/final result.** `[MVP]`
- [ ] **FUN-022 — Define criteria by family, channel-count range, and wavelength.** `[MVP]`
- [ ] **FUN-032 — Force a new two-wavelength test after a mapping change.** `[MVP]`
- [ ] **FUN-036 — Link and retain pre- and post-optimization measurements.** `[R1]`

## Decisions still needed

- [ ] Approve OSX-100 and OSX-150 limits by wavelength and channel-count range.
- [ ] Confirm the OSX-150 optimization band and who may approve exceptions.
- [ ] Approve the spare-ranking formula.
- [ ] Decide how the final result is selected when multiple attempts exist.
- [ ] Define reference age and mandatory re-reference triggers.
- [ ] Confirm supported OSX transports and command documentation.
- [ ] Choose the report-template mapping method.
- [ ] Choose the authoritative complete raw-session format.
- [ ] Define attributable operator/engineer/admin roles.
- [ ] Confirm deployment constraints and representative UAT hardware/data.

## Suggested implementation order

1. [ ] Resolve the open acceptance decisions.
2. [ ] Add family, wavelength, channel-count criteria, and final dispositions.
3. [ ] Add full attempt history, final-result selection, traceability, and crash recovery.
4. [ ] Complete reading validity, route verification, timing/retries, and reconnect behavior.
5. [ ] Add authoritative mapping/spare status, forced retest, and the final-map debug export.
6. [ ] Complete OSX-100 reporting, raw-session output, naming, and finalization validation.
7. [ ] Add attributable roles, finish controlled configuration, and execute RevB UAT.

Update this checklist and [`Requirements.md`](../Requirements.md) together whenever implementation status changes.
