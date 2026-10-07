# OSX insertion-loss software requirements: RevB implementation assessment

**Source:** [OSX_IL_Test_Software_Requirements_RevB.xlsx](temp%20docs/OSX_IL_Test_Software_Requirements_RevB.xlsx), `Requirements` worksheet, rows 5–50. The workbook's Document Control sheet identifies the document as **version 0.1 Draft**, dated **2026-09-30**, and prepared for Santec California engineering, production, software, and quality stakeholders.

**Assessment date:** 2026-10-07. **Software baseline:** Light Workbench 1.21.3 (`config/app_info.py`).

**Assessment method:** Source-code, automated-test, and project-documentation review. This is an engineering gap assessment, not formal approval, hardware qualification, or user acceptance.

## Revision B reconciliation

RevB contains **46 requirement rows: 39 Must and 7 Should; 37 MVP, 7 R1, and 2 R2**. Compared with RevA, it removes 12 rows, adds a second `FUN-014`, and changes several requirements or release targets.

- Removed from the RevB register: `FUN-016`, `FUN-018`, `FUN-024`, `FUN-033`, `FUN-038`, `FUN-039`, `FUN-042`, `FUN-044`, `FUN-045`, `FUN-048`, `FUN-052`, and `FUN-054`.
- Added: editable minimum, maximum, and warning criteria as a second `FUN-014` row.
- Changed: `FUN-008` now blocks incomplete reports without an override clause.
- Changed: `FUN-017` and `FUN-053` move to R2.
- Changed: `FUN-035` requires the final mapping in a debug file rather than the final customer report.
- Changed: `FUN-057` and `FUN-060` move into MVP; `FUN-060` is now a Must.

The workbook uses `FUN-009` twice and `FUN-014` twice. This assessment labels them `FUN-009a`/`FUN-009b` and `FUN-014a`/`FUN-014b` for traceability without changing the workbook.

## Executive summary

Light Workbench implements the central production path for an ILM-100/OP815 and supported Santec OSX-100/OSX-150 switches. Current strengths include persistent hardware connections and status, dual-wavelength reference enforcement, role-dependent Start Run preflight, model-specific controlled limits, sequential and selective testing, autosave, logical/physical channel tracking, multi-run COC preparation, strict report completeness/failure checks, and always-on engineering support logs.

The largest remaining RevB gaps are selectable product family and wavelength pairs, complete measurement/retest history, channel-count- and wavelength-specific criteria, comprehensive invalid-reading detection, authoritative replacement mapping and retest enforcement, complete raw traceability, guided communication recovery, and formal crash recovery.

This assessment rates **17 requirements implemented, 24 partially implemented, and 5 not implemented**. Hardware-dependent items still require representative OSX-100/OSX-150 and ILM-100 validation.

## Status definitions

- **Implemented:** The reviewed production path provides the required core behavior for its currently supported scope.
- **Partial:** Related behavior exists, but an explicit part of the RevB requirement remains missing or unverified.
- **Not implemented:** The required behavior or data model is absent from the production path.

## Requirement-by-requirement assessment

### Functional workflow

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-001 | Must / MVP | Require selection of OSX-100 or OSX-150 before testing. | Partial | The connected switch is identified and assigned an OSX-100 or OSX-150 limit profile, but there is no required operator family selector before connection/start. |
| FUN-002 | Must / MVP | Allow sequential channel testing. | Implemented | Full configured pass tests logical channels sequentially. Single-channel, range, and manual-order workflows are also available. |
| FUN-003 | Must / MVP | Allow one or more channels to be selected and retested before report finalization. | Partial | Completed table rows can be selected and retested. The application does not yet have an explicit report-finalized session state. |
| FUN-004 | Must / MVP | Preserve full retest history and identify the active/final result. | Implemented | Run JSON stores an append-only accepted-attempt history with stable IDs, replacement links, timestamps, operator, reference snapshots, and the latest effective projection. The Run information box provides a read-only history viewer. |
| FUN-005 | Must / MVP | Let the user specify measurement wavelengths. | Not implemented | Production acquisition is fixed at 1310/1550 nm; there is no 1310/1550 versus 850/1300 selector or compatible multimode hardware path. |
| FUN-006 | Must / MVP | Calculate overall channel disposition using applicable limits at both wavelengths. | Partial | Both 1310 and 1550 values are assessed with the active model profile, including optimization/too-good/failure classifications. Criteria are not yet wavelength- or channel-count-specific, and the complete required disposition model is unfinished. |
| FUN-007 | Should / R1 | Support abort, pause, resume, and safe restart, including an arbitrary channel. | Partial | Stop and later continuation preserve written rows, and continuation/manual modes can choose a channel. There is no formal pause state or guided interrupted-session recovery protocol. |
| FUN-008 | Must / MVP | Prevent final report generation while required channels are untested. | Implemented | COC preparation requires a complete reading for every requested front-panel channel and provides no incomplete-report bypass. |

### Instrument and switch interfaces

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-009a | Must / MVP | Discover/connect the ILM-100 through the approved legacy OP815 interface and keep it in remote mode. | Implemented | The persistent hardware manager uses the OP815 DLL adapter, enters remote mode at connection, and keeps the session available until explicit disconnect or application shutdown. |
| FUN-009b | Must / MVP | Let the user take the ILM-100 out of remote mode. | Implemented | The Connect Hardware menu can disconnect measurement hardware independently; cleanup disables sources, exits remote mode, and closes the driver session. |
| FUN-010 | Must / MVP | Display ILM-100 connection status, identity, and actionable errors. | Partial | Connected hardware status shows state, model, and serial when available. Optical-switch VISA failures now classify the status and provide operation-specific recovery guidance; a complete device/firmware recovery catalog remains. |
| FUN-012 | Must / MVP | Support a required reference/zero operation for each wavelength before DUT testing. | Implemented | Start Run requires an authorized two-wavelength reference. Normal operators must calculate it; Admin Mode may explicitly apply a manual reference but cannot bypass a missing or invalid reference. |
| FUN-013 | Must / MVP | Record reference date/time and values or instrument acknowledgement in the session. | Implemented | Immutable reference snapshots include timestamp, both values, method, and meter identity, and are attached to accepted readings and run JSON. |
| FUN-014a | Must / MVP | Reject invalid, stale, saturated, under-range, or missing ILM readings. | Partial | Missing wavelengths, DLL failures, actual-wavelength mismatches, dark references below -40 dBm, and negative insertion loss are rejected from accepted production data. General stale, saturation, and under-range detection remains undefined/incomplete. |
| FUN-014b | Must / MVP | Make loss minimum/maximum and warning criteria editable. | Implemented | Admin Config edits model-specific too-good minimum, optimization-warning applicability/value, absolute failure maximum, profile name, and revision; values are validated and stored in a per-user INI file. |
| FUN-015 | Must / MVP | Discover/connect the selected OSX and display status, with automatic field population. | Implemented | Supported OSX-100/OSX-150 identities are detected and shown. Connection can populate Main board serial and trigger automatic part-number lookup when run state permits. |
| FUN-017 | Must / R2 | Route a logical channel and confirm command completion before measurement. | Partial | The adapter sends the route command, waits, and queries the active physical port before measurement. Production hardware/firmware coverage and authoritative route verification still need completion. |
| FUN-019 | Should / R1 | Make communication timeouts, retries, and settling delays configurable and logged. | Partial | Timing constants are isolated and hardware/support traces record commands and timing. They are not managed through controlled configuration, and retry policy is incomplete. |
| FUN-020 | Should / R1 | Reconnect after communication loss without losing completed results and confirm the channel before resume. | Partial | Accepted data remains saved and a run can be reloaded/continued. Guided in-session reconnect and mandatory post-reconnect channel confirmation are absent. |

### Controlled criteria and configuration

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-021 | Must / MVP | Store product acceptance limits in controlled configuration. | Implemented | OSX-100/OSX-150 profiles are stored in `limit_profiles.ini` and edited through session-only Admin Mode rather than the test workflow. |
| FUN-022 | Must / MVP | Include family, channel-count range, wavelengths, warning band, and absolute failure limit in the selected criteria set. | Not implemented | Current profiles include family, too-good/warning/failure values, name, and revision, but not channel-count applicability or wavelength definitions/per-wavelength limits. |
| FUN-023 | Must / MVP | Capture criteria-set name and revision in the run record. | Implemented | New run JSON snapshots the active switch model, profile name, revision, thresholds, and warning applicability. |
| FUN-025 | Must / MVP | Support an internal optimization band stricter than the published maximum loss. | Implemented | OSX-150 uses a controlled optimization warning above 2.25 dB and formal failure above 2.5 dB; OSX-100 intentionally has no optimization-warning band. |
| FUN-026 | Must / MVP | Visually distinguish Pass, Optimization Review, Fail, Untested, and Invalid Measurement. | Partial | Pending, too-good, optimization, and formal-failure conditions are distinguished in current workflows. A consistent five-state model, particularly persisted Invalid Measurement, remains incomplete. |

### OSX-150 spare optimization and mapping

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-027 | Must / MVP | Distinguish logical routed channels from physical switch channels. | Implemented | Routing uses a logical channel, queries the active physical port, shows it to the operator, and stores both values in run JSON. |
| FUN-030 | Should / R1 | Rank spare channels using both wavelengths and show the calculation basis. | Partial | Replacement analysis uses both wavelengths and separates recommended from optional candidates. The complete controlled ranking basis is not fully presented or approved. |
| FUN-031 | Must / MVP | Replace a routed channel with a selected spare and record old/new mapping, reason, operator, and timestamp. | Partial | Light Workbench now records the manually performed Current Port → Replacement Port change with reason, operator, timestamp, and append-only history, including repeated replacement chains. It intentionally does not execute, identify, or verify the hardware remap; the requirement wording should be clarified to match that operating model. |
| FUN-032 | Must / MVP | Require two-wavelength retest after a mapping change. | Not implemented | Recording a replacement does not invalidate the affected final result or force a new accepted two-wavelength measurement. |
| FUN-034 | Must / MVP | Show remaining unassigned spares and their latest test status. | Partial | Designated spares and replacement suggestions are visible. There is no authoritative assigned/unassigned spare inventory linked to each spare's latest disposition. |
| FUN-035 | Must / MVP | Put the final logical-to-physical map and replacement identification in the debug file. | Partial | Support logs and run JSON record routed logical/physical pairs, and unit data records replacements. No single exported debug view currently assembles the complete final map and identifies every optimization replacement. |
| FUN-036 | Should / R1 | Retain pre- and post-optimization measurements in the session record. | Not implemented | Separate numbered runs and multi-run COC combination can preserve useful data, but the authoritative session does not link complete before/after attempts as optimization history. |

### Reporting and output

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-037 | Must / MVP | Populate a user-selected XLSX report template without manual measurement copy/paste. | Partial | The COC workflow populates approved OSX-150 templates and supports template selection. Required OSX-100 report output is not implemented. |
| FUN-040 | Must / MVP | Fit report rows to channel count while preserving formatting, formulas, merged cells, and print area where practical. | Implemented | The exporter selects the 45- or 48-channel OSX-150 template, removes unused rows, repairs affected merged ranges, and updates the print area without modifying the source template. |
| FUN-041 | Must / MVP | Save raw session data separately from the formatted report. | Partial | CSV/JSON run data and support logs are separate from the COC. The authoritative raw session still lacks full attempts, invalid samples, errors, and final-result linkage. |
| FUN-043 | Must / MVP | Use a configurable report name and prevent silent overwrite, including date/time. | Partial | COC names include model, main-board serial, and `YYMMDD-HHMMSS`; collisions receive a numeric suffix. The naming pattern is not yet administrator/configuration controlled. |

### Data integrity, usability, reliability, security, and maintainability

| ID | Priority / release | Requirement | Status | Current behavior and remaining work |
| --- | --- | --- | --- | --- |
| FUN-046 | Must / MVP | Record session/product identity, logical/physical channel, wavelength, value, units, timestamp, attempt, instrument, and validity for every measurement. | Partial | Accepted rows contain product/run identity, channels, two IL values, and reference snapshots with meter identity. Support logs add timestamps and temporary measurements, but the authoritative schema lacks complete attempt numbering, explicit units/validity, and every rejected sample. |
| FUN-047 | Must / MVP | Autosave after every completed channel or retest. | Implemented | Write IL atomically updates run CSV/JSON after each accepted reading or retest. New run folders remain deferred until the first accepted measurement. |
| FUN-050 | Must / MVP | Validate required metadata and file paths before start and report finalization. | Partial | Role-aware Start Run preflight enforces metadata, channels, connected hardware, and authorized reference before side effects. COC preparation validates source compatibility, completeness, limits, replacements, and template capacity; a complete controlled output-path/finalization policy remains. |
| FUN-051 | Must / MVP | Show unit, connected instruments, reference status, active channel/wavelength, latest measurement, progress, and pass/review/fail. | Partial | The main screen shows unit/run information, connected hardware, reference status, active channel, completed dual-wavelength readings, progress, and limit status. It does not show an explicit active wavelength during acquisition or a fully unified disposition state. |
| FUN-053 | Should / R2 | Identify the affected device/channel and corrective action for errors when known. | Partial | Optical-switch VISA failures now identify the switch operation, command, status, and recovery guidance, while preserving technical details in support logs. A reviewed, comprehensive error/recovery catalog and fault-test matrix are still needed. |
| FUN-055 | Must / MVP | Start safely with no routing or measurement until connections and test configuration are confirmed. | Implemented | Persistent connection is an explicit operator action. Central preflight blocks incomplete setup, invalid channel input, unavailable hardware, and missing/invalid/mismatched references before run creation, routing, source activation, or reading. |
| FUN-056 | Must / MVP | Preserve the completed session when report export fails so export can be retried. | Implemented | Run persistence is independent of COC export. Export exceptions leave the session intact and report a recoverable error. |
| FUN-057 | Must / MVP | Recover after unexpected termination from the last autosaved state without duplicating measurements. | Partial | Atomic per-reading saves and manual run loading/continuation provide a recovery base. Automatic crash-session detection, reconciliation, and forced-termination evidence are absent. |
| FUN-058 | Must / R1 | Capture operator identity and require an authorized role for overrides and criteria edits. | Partial | Tested by initials are required for normal starts, and session-only Admin Mode protects criteria edits/manual-reference and metadata bypass actions. Authentication is a shared local password rather than attributable user identity/roles. |
| FUN-059 | Should / R1 | Isolate commands, timing, criteria, template mappings, and naming rules in version-controlled configuration modules. | Partial | Hardware commands, timing, limit profiles, exporters, and naming helpers are separated by module. Some values remain hard-coded or per-user rather than controlled/versioned configuration. |
| FUN-060 | Must / MVP | Generate engineering support logs without exposing confidential credentials. | Implemented | Always-on daily JSONL logs use allowlisted fields and redaction, include hardware/workflow/persistence/export evidence, compress older logs, retain them indefinitely, warn above 500 MB, and support explicit support-bundle export. |

## Open acceptance inputs carried by RevB

The workbook's `Open Decisions` sheet still identifies these unresolved inputs:

1. Approve OSX-100 and OSX-150 limits, including wavelength/channel-count applicability.
2. Confirm the OSX-150 optimization band and approval policy.
3. Approve the spare-ranking method.
4. Define how a final result is chosen when retests exist.
5. Define reference age and mandatory re-reference triggers.
6. Confirm supported OSX transports and command documentation.
7. Define the report-template mapping approach.
8. Choose the authoritative complete raw-session format.
9. Define attributable authorization roles.
10. Confirm deployment/update constraints and the representative UAT dataset.

## Implementation roadmap

| Milestone | Outcome | Primary RevB requirements |
| --- | --- | --- |
| **0. Resolve acceptance inputs** | Record approved wavelengths, limits, reference lifetime, final-result selection, spare ranking, transport, raw-data, deployment, and UAT decisions. | FUN-001, 005–006, 014, 019, 022, 030, 043, 058–059 |
| **1. Family, wavelength, and criteria model** | Add required family selection, 1310/1550 versus 850/1300 capability, channel-count/wavelength-aware criteria, and the complete five-state disposition model. | FUN-001, 005–006, 022, 026 |
| **2. Authoritative session and measurement history** | Preserve every attempt and invalid sample with stable IDs, timestamps, units, instrument identity, validity, active/final selection, and crash-recovery state. | FUN-003–004, 014a, 041, 046–047, 057 |
| **3. Hardware robustness** | Complete reading-validity rules, controlled timing/retries, guided reconnect, route verification, and consistent corrective errors across supported firmware. | FUN-010, 014a, 017, 019–020, 053, 055 |
| **4. Spare mapping and optimization audit** | Model authoritative logical/physical assignments and spare status, record attributed changes, force retest, retain before/after measurements, and export the final map in the debug package. | FUN-027, 030–036 |
| **5. RevB-complete reporting** | Add OSX-100 output, complete raw-session export, configurable naming, finalization/path validation, and release tests for variable templates and export failures. | FUN-008, 037, 040–043, 050, 056 |
| **6. Governance and UAT** | Replace shared admin authorization with attributable roles where required, finish version-controlled configuration, and execute the RevB UAT matrix on representative hardware. | FUN-058–060 plus all hardware-dependent requirements |

## Reviewed implementation evidence

- `ilm_app.py`: production UI, role-dependent preflight, hardware status, reference workflow, run/retest controls, analysis, and COC entry points.
- `application/run_preflight.py`, `application/hardware_connection.py`, and `application/measurement_worker.py`: start authorization, persistent hardware ownership, routing, and acquisition lifecycle.
- `domain/reference.py`, `domain/measurement.py`, and `domain/limit_profiles.py`: reference evidence, reading safety, and model-specific controlled criteria.
- `hardware/power_meter.py`, `op815_driver.py`, and `hardware/optical_switch.py`: current ILM/OSX communication and identity handling.
- `infrastructure/run_persistence.py` and `infrastructure/unit_persistence.py`: current authoritative run/unit storage.
- `domain/replacements.py`, `application/coc_workflow.py`, and `infrastructure/coc_export.py`: optimization analysis, multi-run preparation, and COC export.
- `application/support_logging.py` and `infrastructure/support_log_writer.py`: engineering support logging, retention, redaction, and support bundles.

When behavior changes, update this assessment and [the simplified checklist](docs/REQUIREMENTS_CHECKLIST.md) together. The RevB workbook remains the authority for requirement wording and business intent.
