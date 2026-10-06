# OSX insertion-loss software requirements: implementation assessment

**Source:** [OSX_IL_Test_Software_Requirements_RevA.xlsx](temp%20docs/OSX_IL_Test_Software_Requirements_RevA.xlsx), `Requirements` worksheet, rows 5–61. The workbook's Document Control sheet identifies it as **version 0.1 Draft**, dated **2026-09-30**, prepared for Santec California engineering, production, software, and quality stakeholders.  
**Assessment date:** 2026-10-06. **Software baseline:** Light Workbench 1.19.0 (`config/app_info.py`).
**Assessment method:** Review of source code, existing automated tests, and project documentation. This is a gap analysis, not hardware qualification or formal user acceptance. The workbook's own `Status` column says *Draft* for every item; the implementation status below is a separate assessment.

**Validation implementation note (1.16.1):** Measurement-based references
below -40.0 dBm are rejected before production authorization, while negative
insertion-loss samples are retained only as visible/support evidence and cannot
be written to production run data. This safety behavior does not change the
requirements status classifications below.

## Executive summary

Light Workbench already supports the core OSX-100/OSX-150/ILM-100 workflow: selecting channels, routing a supported Santec switch, acquiring 1310/1550 nm readings, accepting readings with **Write IL**, saving CSV/JSON after each accepted result, analyzing over-limit readings, recording basic physical-port swaps, and exporting an OSX-150 COC workbook. These functions provide a useful starting point, but **the application does not yet meet the full draft production requirements**. Final COC preparation now blocks incomplete or formally failing channel sets and can combine a complete base run with one validated replacement/retest run. Accepted retests still replace earlier values in normal run persistence, and the current output format cannot serve as a complete measurement audit record.

The highest-impact gaps are product-family and wavelength support; revisioned acceptance criteria; mandatory reference evidence; complete retest and mapping history; measurement validity; report completeness and variable-length templates; and authorization/audit controls. An OSX-100 or multimode release also depends on verified production hardware interfaces and defined limits. No row has been judged intrinsically impossible, but several cannot be demonstrated until those technical details and hardware tests are available.

Of the 57 rows, this review rates **15 implemented**, **28 partial**, and **14 not implemented**. These are engineering assessments of the current source, not approved closure counts.

## How to read this register

- **Implemented:** The reviewed code provides the stated behavior for its current supported scope. Hardware-dependent behavior still needs testing on representative equipment.
- **Partial:** A related capability exists, but one or more explicit parts of the requirement are missing.
- **Not implemented:** The required behavior is absent from the reviewed production path. A nearby feature or future design document does not count as implementation.
- **Priority / release** reproduces the workbook's `Must` or `Should` and `MVP` or `R1` values. *R1* means the workbook's planned follow-on release; it does not make a `Must` item optional.

The workbook has **57 requirement rows: 46 Must and 11 Should; 41 MVP and 16 R1**. It uses `FUN-009` twice. This document labels them **FUN-009a** (ILM connection/remote entry, worksheet row 13) and **FUN-009b** (operator exit from remote mode, row 14) without changing the source workbook. The workbook also skips several ID numbers; no missing requirements are inferred from those gaps.

## Requirement-by-requirement assessment

### Functional workflow

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-001 | Must / MVP | Select OSX-100 or OSX-150 family before testing. | Partial | The adapter supports verified OSX-100 and OSX-150 profiles and resolves the legacy generic OSX identity as OSX-100. There is not yet a required operator family selector or family-specific workflow. |
| FUN-002 | Must / MVP | Test channels sequentially. | Implemented | Full configured pass routes successive logical channels; single, range, and manual-order modes also exist. |
| FUN-003 | Must / MVP | Select and retest one or more channels before report finalization. | Partial | **Retest selected** accepts multiple completed table rows after an active run stops. In-run selective retest and a distinct finalization boundary are not established. |
| FUN-004 | Must / MVP | Preserve every retest attempt and identify the active/final result. | Not implemented | Committing a retest replaces the prior channel row. `RunRecorder.record_attempt()` exists, but the save payload does not write `attempts`, and the normal commit path does not call that method. |
| FUN-005 | Must / MVP | Let the user choose measurement wavelengths. | Not implemented | Production measurement and IL calculation are fixed at 1310/1550 nm. The worksheet notes that OSX-100 multimode may need 850/1300 nm. |
| FUN-006 | Must / MVP | Determine overall channel disposition using limits at every required wavelength. | Partial | Both values are compared against one editable `warning_limit_db`; there are no wavelength-specific absolute fail limits, approved criteria, or separate review/fail disposition. |
| FUN-007 | Should / R1 | Abort, pause, resume, and safely restart, including an arbitrary restart channel. | Partial | Stop and later continuation preserve accepted rows, and continuation can choose a channel. A defined pause state and interrupted-communication recovery protocol are absent. |
| FUN-008 | Must / MVP | Block final report for missing required channels unless an authorized override reason is recorded. | Implemented | Final COC preparation requires every front-panel logical channel and provides no incomplete-report override. Missing channels are listed in one blocking validation message. |

### Instrument and switch interfaces

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-009a | Must / MVP | Discover/connect the ILM-100 through its approved legacy OP815 interface and enter remote mode. | Implemented | The persistent hardware manager opens the OP815 through the approved DLL adapter, which calls `RemoteMode(1)`. The connection remains available between workflows until explicitly disconnected or the application closes. |
| FUN-009b | Must / MVP | Give the operator a way to leave ILM remote mode on demand. | Implemented | The header `Connect Hardware...` menu provides measurement-only and all-hardware disconnect actions. The manager safely turns sources off, calls the adapter cleanup that performs `RemoteMode(0)`, and releases the driver session. |
| FUN-010 | Must / MVP | Show ILM status/identity and actionable connection errors. | Partial | The header shows connection state, model, and serial when available; errors are surfaced. Corrective guidance is not consistently device-specific. |
| FUN-012 | Must / MVP | Reference/zero every required wavelength before DUT testing. | Implemented | Production acquisition requires a valid calculated reference or an explicitly authorized Admin Mode manual reference. |
| FUN-013 | Must / MVP | Record reference time, values, or instrument acknowledgement in the session. | Implemented | Immutable reference snapshots are stored per accepted reading and in the run-level JSON reference history, with CSV audit columns. |
| FUN-014 | Must / MVP | Reject invalid, stale, saturated, under-range, or missing ILM readings. | Partial | DLL failures and wrong/unsupported actual wavelength raise errors; both wavelengths must be present for the current calculation. There is no complete stale/saturation/under-range validation policy or persisted invalid-sample state. |
| FUN-015 | Must / MVP | Discover/connect the selected OSX family and show status. | Implemented | USB VISA discovery and connected-switch status work for verified OSX-100 and OSX-150 profiles. Explicit unsupported/malformed identities are rejected, while the complete legacy generic OSX identity is resolved as OSX-100 with a warning. |
| FUN-016 | Must / R1 | Check connected switch family against operator selection, or authorize an override. | Not implemented | There is no operator family selection or mismatch/override workflow. Current unsupported models are rejected. |
| FUN-017 | Must / MVP | Route a logical channel and confirm completion before measurement. | Partial | The driver sends `CLOSe <channel>`, waits 0.25 s, then queries `CLOSe?` for a physical port before measuring. It parses a response but does not verify the reported route against an authoritative expected mapping. |
| FUN-018 | Should / R1 | Support configurable USB/serial and Ethernet methods where hardware supports them. | Not implemented | The production switch adapter searches a fixed Santec USB VISA resource type. No transport selector or Ethernet/serial adapter is available. |
| FUN-019 | Should / R1 | Make timeouts, retry counts, and settling delays configurable and logged. | Partial | Constants exist in adapters, and always-on OP815/switch support events record command and measurement timing. Production settings are not operator/engineer configurable and there is no configurable retry policy. |
| FUN-020 | Should / R1 | Reconnect after communication loss without losing completed data; confirm channel before resume. | Partial | Accepted rows survive an interruption and a later run can be continued. Automatic or guided reconnect within the interrupted session, with required route confirmation, is absent. |

### Controlled criteria and configuration

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-021 | Must / MVP | Keep product acceptance limits in controlled configuration. | Implemented | Model-specific OSX-100/OSX-150 criteria are stored in the per-user limit-profile INI and editable only through session-only Admin Mode. |
| FUN-022 | Must / MVP | Criteria include family, channel-count applicability, wavelengths, warning band, and absolute fail limit. | Not implemented | No such criteria-set schema or selection/validation logic exists. |
| FUN-023 | Must / MVP | Store criteria-set name and revision with each run. | Implemented | New run JSON stores the resolved model, profile name/revision, and threshold snapshot; legacy JSON remains loadable. |
| FUN-024 | Should / R1 | Restrict criteria edits/approval to authorized users. | Not implemented | There are no roles, approval workflow, or protected criteria edits. |
| FUN-025 | Must / MVP | Support an internal optimization band stricter than the published maximum IL. | Implemented | OSX-150 uses a controlled 2.25 dB optimization warning and 2.5 dB formal-failure limit; OSX-100 has no optimization-warning band. |
| FUN-026 | Must / MVP | Distinguish Pass, Optimization Review, Fail, Untested, and Invalid Measurement. | Partial | Formal failure, optimization warning, too-good warning, and pending states are now model-aware; the separate invalid-measurement state remains to be completed. |

### OSX-150 spare optimization and mapping

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-027 | Must / MVP | Distinguish logical routed channels from physical ports. | Implemented | Routing accepts a logical channel and queries the active physical port; accepted run JSON stores both. The operator view also reports the physical port. |
| FUN-030 | Should / R1 | Rank spare candidates using both wavelength results and show the calculation basis. | Partial | The analyzer ranks by worst-of-two loss and improvement, and the UI shows a proposed swap and improvement. The full per-wavelength score and approved ranking policy are not presented as a controlled decision basis. |
| FUN-031 | Must / MVP | Change a logical-to-physical mapping and record old/new mapping, reason, operator, and time. | Partial | An operator can record **Current Port → Replacement Port** and designated spares for the unit. This is a manual note, not a switch mapping command; logical identity, reason, operator, and timestamp are not recorded with the change. |
| FUN-032 | Must / MVP | Require both-wavelength retest after a mapping change. | Not implemented | Recording a replacement does not invalidate or block acceptance of the affected channel until a new routed result is taken. |
| FUN-033 | Must / MVP | Prevent one physical port from serving multiple logical channels. | Partial | Replacement records reject duplicate replacement-port numbers, but the application does not validate the entire live logical-to-physical map against active channels/spares. |
| FUN-034 | Must / MVP | Show unassigned spare ports and latest test status. | Partial | The UI lists designated spares and analyzer suggestions. It does not maintain an authoritative assigned/unassigned map with current measured disposition for each spare. |
| FUN-035 | Must / MVP | Show final logical-to-physical map and replacements in the final report. | Not implemented | The COC writes IL values to fixed wavelength columns; it does not write a final mapping/replacement table. |
| FUN-036 | Should / R1 | Retain pre- and post-optimization measurements. | Not implemented | Final accepted rows overwrite earlier values for the same logical channel; separate numbered runs may exist but do not establish a linked before/after optimization history. |

### Reports and output

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-037 | Must / MVP | Populate a selected XLSX report template without manually copying measurements. | Partial | **Write COC** selects the approved 45- or 48-channel OSX-150 template, validates a custom template's capacity, and fills the expected cells. The workbook's OSX-100 report format is not supported. |
| FUN-038 | Must / R1 | Configure metadata and measurement-column mappings per report template. | Not implemented | COC cell addresses, sheet name, and measurement rows are hard-coded in `infrastructure/coc_export.py`. |
| FUN-039 | Must / MVP | Include part/serial, test date/time, tester, family, channel count, criteria revision, equipment ID, both IL values, and final disposition. | Partial | The COC writes part number, main-board serial, date, tester initials, and 1310/1550 values. It omits several specified fields and does not use a criteria revision or final disposition. |
| FUN-040 | Must / MVP | Fit report rows to channel count while preserving formatting/formulas/merged cells/print area. | Implemented | COC export chooses the 45- or 48-channel template, removes rows below the requested front-panel count, repairs affected merged ranges, and updates the print area while preserving the source template. |
| FUN-041 | Must / MVP | Save complete raw session data separately from the formatted report. | Partial | CSV/JSON run files are separate from COC output, but they retain only final accepted per-channel values and limited metadata, not the required retest/error history. |
| FUN-042 | Should / R1 | Preview report before final save. | Not implemented | The export writes the workbook immediately and then reports the output path. |
| FUN-043 | Must / MVP | Use configurable report naming and prevent silent overwrite. | Partial | COC files use `COC OSX-150 <serial>_YYMMDD-HHMMSS.xlsx`; existing names receive a numeric suffix instead of being overwritten. The naming pattern is not yet configurable. |
| FUN-044 | Should / R1 | Optionally export the finalized report to PDF. | Not implemented | There is no PDF export path. |
| FUN-045 | Must / MVP | Mark retested channels, show only approved final values in the main table, and preserve history separately. | Not implemented | The COC shows the latest written value, but no final-approval concept, retest marker, or complete history sheet/file exists. |

### Data integrity, usability, reliability, and security

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-046 | Must / MVP | Trace every measurement with session/product identity, logical/physical channel, wavelength, value/units, time, attempt, instrument, and validity. | Partial | Always-on support logs correlate workflows/operations and record complete temporary measurements, raw power, references, IL, channels, hardware identity, and timing. The authoritative run schema still lacks complete attempt history, explicit validity, and final-result linkage. |
| FUN-047 | Must / MVP | Autosave after each completed channel or retest. | Implemented | **Write IL** commits the accepted row and atomically updates run CSV/JSON. A newly started run is not materialized until its first accepted row. |
| FUN-048 | Must / R1 | Keep append-only events for connections, references, readings, retests, mappings, overrides, errors, and reports. | Not implemented | Local JSONL support logs now record these operational events, but they are editable diagnostic evidence rather than an immutable, controlled, authoritative audit history. Normal run persistence still rewrites a current-state snapshot. |
| FUN-050 | Must / MVP | Validate required metadata and paths at start and report finalization. | Partial | Role-aware Start Run preflight validates setup metadata, channel selection, connection readiness, and reference authorization before side effects. COC finalization validates persisted source compatibility, complete channel coverage, finite nonnegative values, physical-port replacements, the strict 2.5000 dB limit, and template capacity; broader report-finalization metadata rules remain. |
| FUN-051 | Must / MVP | Show unit, devices, reference status, active channel/wavelength, latest reading, progress, and pass/review/fail. | Partial | Identity, device, active-channel, latest 1310/1550, and progress fields appear in the run window. An explicit active-wavelength indicator, persisted reference status, and the required disposition states do not. |
| FUN-052 | Must / MVP | Make normal operator actions available through the UI. | Partial | Current testing, retest, diagnostic, and export actions have UI controls. Several required actions (family choice, criteria selection, mapping execution, approval, preview) do not yet exist. |
| FUN-053 | Must / MVP | Give device/channel-specific errors and corrective guidance where known. | Partial | Many exceptions and validation dialogs identify the problem. Consistent recovery instructions, particularly for transport/firmware failures, need a reviewed error catalog and fault tests. |
| FUN-054 | Must / MVP | Confirm clearing a session, changing family mid-test, or overwriting a selected final result. | Partial | The UI confirms new-run versus continue and asks about changed identity. There is no family selection, final-result approval, or comprehensive confirmation policy for those cases. |
| FUN-055 | Must / MVP | Start safely, with no switch move/read until connection and configuration are confirmed. | Implemented | Role-aware preflight blocks incomplete setup, invalid channel selection, unavailable hardware, and missing/invalid references before run creation, switch routing, source activation, or measurement. Admin Mode can bypass only descriptive metadata through an explicit choice. |
| FUN-056 | Must / MVP | Preserve the session if report export fails, allowing later retry. | Implemented | Measurements are saved independently of COC export; COC exceptions show an error and leave the run data intact. This still needs locked-file/path-failure UAT. |
| FUN-057 | Must / R1 | Recover after unexpected termination without losing or duplicating accepted rows. | Partial | Atomic CSV/JSON writes and manual continuation provide a recovery basis. There is no formal crash-recovery/reconciliation flow or forced-termination validation. |
| FUN-058 | Must / R1 | Capture operator identity and authorize overrides/criteria edits by role. | Partial | The **Tested by** initials field is captured; authentication, role enforcement, and attributable approvals do not exist. |
| FUN-059 | Should / R1 | Isolate commands, timing, criteria, template mappings, and naming rules in version-controlled configuration. | Partial | The hardware adapter, switch profile, timing constants, and export code are separate modules. Controlled criteria/template/naming configuration and revision governance are missing. |
| FUN-060 | Should / R1 | Produce support logs without disclosing confidential credentials. | Implemented | Always-on local JSONL covers production/tool workflows, complete measurements, OP815 and switch commands, connection leases, persistence, exports, and errors. It uses an allowlist, path redaction, prohibited-field removal, bounded responses, rotation/retention, degraded fallback, status UI, and explicit local support bundles. `docs/SUPPORT_LOGGING.md` documents the policy and limitations. |

## Milestone 0: testable software behavior baseline

This is a **working implementation baseline**, not a claim that the behaviors below already exist. Keep the workbook unchanged; use `FUN-009a` and `FUN-009b` here to distinguish its two `FUN-009` rows. Each requirement retains its original priority, release target, and current status in the register above. Where a technical choice is still open, do not silently substitute the current UI default or infer an answer from an existing feature.

| Area | Target behavior and testable acceptance condition | Requirements |
| --- | --- | --- |
| Product and criteria | A session identifies OSX family, optical type, selected wavelengths, configured channel count, and criteria name/revision. The application rejects an unsupported family/wavelength/equipment combination before routing or reading. Criteria supply applicable warning and fail limits per wavelength and channel range. The editable 2.0 dB warning default is **not** a production limit. | FUN-001, FUN-005, FUN-006, FUN-021–026, FUN-055 |
| Reference and measurement | A successful reference event records the required wavelength values, time, instrument identity, and validity in the session. Every accepted attempt contains both required wavelengths and their raw power, calculated IL, timestamp, logical channel, physical route, instrument identity, and validity. Missing/invalid/stale readings cannot become final values. The exact re-reference and validity thresholds remain open. | FUN-012–014, FUN-017, FUN-046–047 |
| Attempts and final result | Each **Write IL** or retest commit adds an immutable attempt. One explicitly selected valid attempt is final for each logical channel; the main result table and final report show only that attempt, while the full attempt history remains available separately. The selection policy (latest valid automatically or operator-selected) is open. Existing saved runs must remain readable after a schema change. | FUN-003–004, FUN-041, FUN-045–048, FUN-057 |
| Disposition and completeness | Evaluate every required wavelength against the criteria applicable to that channel. Target states are Untested (no final attempt), Invalid Measurement (an attempted reading is invalid), Fail (any required wavelength exceeds its fail limit), Optimization Review (no fail, at least one exceeds warning), and Pass (all required values meet limits). COC export blocks missing channels and has no operator override; values are compared after four-decimal formatting and exactly 2.5000 dB fails. | FUN-006, FUN-008, FUN-025–026, FUN-039, FUN-050–051, FUN-058 |
| Switch mapping and spares | Persist one authoritative logical-to-physical mapping with unique active physical assignments. Show tested unassigned spares separately. A replacement records old/new mapping, actor, reason, and time, and the affected logical channel cannot retain its old final result without a new valid two-wavelength measurement. A typed replacement note alone is **not** evidence that the hardware route changed. | FUN-017, FUN-027, FUN-030–036, FUN-048 |
| Reports | Generate a family-appropriate template with rows for the configured channel count and the required identity, criteria, final mapping, final values, and disposition fields. Keep raw session/attempt history separate from the formatted result. Template/path failures leave committed measurements intact and allow retry without duplicate results. Actual template mappings and PDF mechanism remain open. | FUN-037–045, FUN-050, FUN-056 |
| Recovery | Autosave each accepted attempt; a communication error must not create a partial final result. After restart/reconnect, restore committed attempts exactly once and confirm the current route before another measurement. Test both wavelength failure points, disconnects, forced termination, and report-write failure using fakes, then representative hardware. | FUN-014, FUN-020, FUN-047–048, FUN-053, FUN-057 |

These contracts describe observable outcomes, not a mandated UI or database design. The existing CSV/JSON files remain a compatibility input; any future stored-attempt schema needs explicit versioning/migration. Local testing and reporting must work without a network database.

### Working UAT-to-requirement crosswalk

The workbook's `UAT Acceptance` sheet references groups such as `INT-*`, `DAT*`, and `REL` that are **not requirement IDs in its `Requirements` sheet**. The table below is a working crosswalk to existing `FUN-*` rows for implementation and automated-test planning; it does not alter the workbook's scenario wording or claim those scenarios have passed.

| UAT scenario | Existing requirement IDs to exercise | Evidence to capture |
| --- | --- | --- |
| UAT-001 — Create OSX-100 session with arbitrary channel count | FUN-001, FUN-002, FUN-005, FUN-009a, FUN-012, FUN-015, FUN-021–023, FUN-050, FUN-055 | Valid and invalid family/channel-count/wavelength combinations; stored criteria identity. |
| UAT-002 — Complete two-wavelength test | FUN-002, FUN-006, FUN-014, FUN-017, FUN-026, FUN-046–047, FUN-051 | Route confirmation, complete attempt, final values, and disposition at both wavelengths. |
| UAT-003 — Retest selected channel | FUN-003–004, FUN-045–047 | Original and retest attempts preserved; one final result selected and reported. |
| UAT-004 — OSX-150 spare optimization | FUN-027, FUN-030–036 | Candidate analysis, unique final mapping, and new valid measurement after replacement. |
| UAT-005 — Instrument disconnect recovery | FUN-014, FUN-020, FUN-047, FUN-053, FUN-057 | No partial/duplicate result; committed attempts survive; route reconfirmed. |
| UAT-006 — Variable-length Excel report | FUN-037, FUN-039–041, FUN-043, FUN-056 | Short/long channel-count workbooks with correct rows, metadata, and preserved formatting. |
| UAT-007 — Incomplete-test finalization | FUN-008, FUN-050, FUN-058 | Export blocked or a precisely defined exception with reason and actor. |
| UAT-008 — Criteria revision traceability | FUN-021–023, FUN-039, FUN-046 | Run and report agree on criteria identity/revision and applied limits. |
| UAT-009 — Crash recovery | FUN-047, FUN-057 | Restart/reload reproduces committed attempts without loss or duplicates. |
| UAT-010 — Template/path failure | FUN-037, FUN-043, FUN-050, FUN-056 | Failure does not damage saved session; corrected path/template can be retried. |

### Open technical questions

Answers to these change implementation or acceptance tests. Until resolved, keep them visible as questions rather than inventing rules.

1. What OSX-100 SM/MM wavelength sets and channel-count ranges are required? Is 850/1300 nm mandatory for the MVP, and which meter/source and control interface can actually measure them? (**OD-007**, FUN-001, FUN-005, FUN-015)
2. What warning/optimization and absolute fail values apply by family, optical type, wavelength, and channel range? Does equality to a limit count as pass or over-limit? (**OD-001–OD-003**, FUN-006, FUN-021–026)
3. What exact reference procedure, maximum reference age, re-reference trigger, and instrument error/range checks determine a valid sample? (**OD-006**, FUN-012–014)
4. Is the final result automatically the latest valid retest, or must an operator choose it? What happens if the newest retest is invalid? (**OD-005**, FUN-003–004, FUN-045)
5. Does the application command physical switch remapping, or verify a mapping made outside it? What command or query proves the new route, and when must the affected channel be retested? (**OD-007**, FUN-031–033)
6. How many designated spares are required per configuration, when is a spare considered tested, and what calculation ranks candidates? (**OD-004**, FUN-030, FUN-034)
7. COC output now always blocks missing required channels and provides no operator override. Confirm whether any future report type needs a separately controlled exception workflow. (**OD-010**, FUN-008, FUN-050, FUN-058)
8. Which OSX-100/150 XLSX templates, channel-count extremes, field locations, and PDF output rules must be supported? What is the full raw-session export contract? (**OD-008–OD-009**, FUN-037–044)
9. Which Windows/VISA/driver and firmware combinations and disconnect/timeout cases must be supported and exercised on hardware? (**OD-011–OD-012**, FUN-018–020, FUN-053, FUN-057)

**Feasibility constraint:** No listed requirement is known to be fundamentally impossible. Hardware-dependent requirements cannot be demonstrated without compatible equipment/interfaces and representative fault tests. If a required wavelength or route cannot be controlled with the available instruments, the implementation needs a compatible hardware path or an explicitly documented scope limitation; a UI selector alone is insufficient.

## Implementation roadmap

The sequence below follows software dependencies and the workbook's MVP/R1 priorities. Each milestone should have automated tests and, where hardware behavior matters, representative instrument checks traceable to the requirement IDs above. Existing CSV/JSON files should remain readable; schema changes require migration/versioning. Local test and report generation must continue to work without a future network database.

| Milestone | Delivery and acceptance gate | Primary requirements |
| --- | --- | --- |
| **0. Define testable software behavior** | Keep source IDs intact, use working `FUN-009a/b` aliases, map UAT scenarios to real IDs, specify target observable behavior, and list only unresolved technical questions that affect implementation. Exit when each of the 57 rows has a current status and a target behavior or explicit open question; the crosswalk above provides the scenario-level starting point. No code or approval workflow changes in this milestone. | All; especially FUN-001, FUN-005, FUN-021–023, FUN-039–040 |
| **1. Canonical session and attempt record** | Add versioned session ID, immutable measurement attempts (both wavelengths, raw/IL values as approved, validity, timestamps, channel/port, instrument identity), explicit final-result selection, and migration from current files. Autosave each accepted attempt and test forced interruption/reload. Establish a reference event with timestamp and active baseline. | FUN-004, 012–014, 041, 045–048, 057 |
| **2. Controlled criteria and safe preflight** | Add family and criteria selection, channel-count applicability, per-wavelength warning/fail thresholds, revision capture, five-state disposition, and required reference/metadata gates. Preserve the current no-override incomplete-COC rule unless a separately controlled exception is defined later. Validate against approved fixtures for SM/MM and low/high channel counts. | FUN-001, 006, 008, 012–016, 021–026, 050–055 |
| **3. Qualify hardware and transport** | Implement verified OSX-100 profile/transport and the approved 850/1300-capable meter/source where needed. Extend wavelength-agnostic models and measurement worker. Add expected-route checks, bounded retries/reconnect, configurable timing, command diagnostics, and real hardware fault tests; retain OSX-150 behavior. | FUN-005, 009a–010, 014–020, 053, 055, 059–060 |
| **4. Govern spare remapping** | Model authoritative logical-to-physical assignments and unassigned tested spares. Apply or explicitly verify actual switch remap, record old/new mapping plus actor/reason/time, enforce one-to-one mapping, invalidate affected final results, require two-wavelength retest, and retain before/after attempts. Confirm ranking policy and display its calculation. | FUN-027, 030–036, 048 |
| **5. Final report and release gate** | Support approved OSX-100/150 XLSX mappings and variable channel counts; populate all required metadata, final mapping/disposition, and retest indicators while preserving workbook formatting. Add preview, configurable no-overwrite naming, optional PDF, and completeness/authorization checks. Exercise locked-template/path failures. | FUN-008, 035, 037–045, 050, 056 |
| **6. R1 governance and recovery** | Add operator/engineer/admin permissions, approved criteria changes, append-only audit events, explicit pause/reconnect/recovery flow, support-safe logs, and production deployment procedures. Run the complete workbook UAT set, including forced termination, disconnect, and template failure. | FUN-007, 016, 018–020, 024, 036, 038, 042, 044, 048, 057–060 |

**Delivery sequence:** Treat milestones 0–5 as the MVP implementation path even where a supporting workbook row is marked R1; otherwise some MVP items cannot be demonstrated (for example, a final report cannot safely enforce a mapping it does not know). Milestone 6 finishes the explicit R1 controls. Source-code review alone is not evidence that hardware-dependent behavior works: exercise the applicable UAT scenario and record the hardware/firmware, criteria, and template revisions used.

## Reviewed implementation evidence

The status calls above are anchored in these current modules. Paths point to source code; the workbook remains the authority for requirement wording and business intent.

- [Main window and operator workflow](ilm_app.py): setup, reference warning, run/retest, status, saved-result selection, and COC controls.
- [Run planning](application/hardware_planning.py), [measurement worker](application/measurement_worker.py), and [hardware session](hardware/session.py): channel order, routing, measurement, lifecycle, and continuation.
- [OP815 driver](op815_driver.py), [switch adapter](hardware/optical_switch.py), and [measurement formula](domain/measurement.py): current hardware protocol and wavelength behavior.
- [Run persistence](infrastructure/run_persistence.py), [unit persistence](infrastructure/unit_persistence.py), and [run model](domain/run_data.py): accepted-result schema, autosave, and unit/run identity.
- [Replacement analysis](domain/replacements.py) and [COC exporter](infrastructure/coc_export.py): recommendation/mapping records and fixed-template output.
- [Hardware architecture](docs/HARDWARE_ARCHITECTURE.md), [data architecture](docs/DATA_ARCHITECTURE.md), and [testing/release guidance](docs/TESTING_AND_RELEASE.md): intended boundaries and validation gates.
