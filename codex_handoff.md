# Light Workbench - Project Status and Handoff

Timing implementation reviewed: 2026-11-10 on `cleanup`, against source revision
`2aa4967` plus uncommitted timing changes. The broader governance review was
2026-11-03 against `11a0068`. Start with [AGENTS.md](AGENTS.md)
and the [documentation authority guide](docs/README.md).
Source inspection confirms implementation; it does not establish runtime acceptance.

## Current Baseline

- **Application:** Light Workbench **1.36.0**, from
  [config/app_info.py](config/app_info.py). Record the Git revision as well as
  the version when reporting results.
- **Architecture:** PyQt desktop composition remains in [ilm_app.py](ilm_app.py),
  with application controllers/workers, domain rules, hardware adapters, and
  infrastructure repositories. Root facades and the console entry point remain
  compatibility surfaces. See [PROGRAM_DESIGN](docs/PROGRAM_DESIGN.md) and
  [PROJECT_LAYOUT](docs/PROJECT_LAYOUT.md); do not duplicate their module inventory here.
- **Persistence:** SQL Server is authoritative for new recorded runs of every
  purpose. Run creation precedes acquisition; accepted two-wavelength attempts
  commit atomically and remain append-only. The worker advances after a matching
  persistence acknowledgement, and completion reconciles saved coverage.
  See [database workflow](application/database_primary_workflow.py),
  [measurement workflow](application/measurement_persistence_workflow.py), and
  [DATA_ARCHITECTURE](docs/DATA_ARCHITECTURE.md).
- **Schema in source:** seven forward-only migrations, `0001` through
  [0007_run_test_sessions.sql](infrastructure/database/sql_migrations/0007_run_test_sessions.sql),
  define **eleven tables (including tracking) and five views**, including persisted analyses,
  recommendations, confirmed extras, and active test sessions. Migration 0007
  was applied to `localhost\SQLEXPRESS / LWBTestDB` on 2026-11-10 at the user's
  request; read-only preflight and schema checks passed (see deployment record below).
  SQL version 7 is distinct
  from legacy run JSON version 6/unit JSON version 3.
  [DATABASE_ARCHITECTURE](docs/DATABASE_ARCHITECTURE.md) owns the schema;
  [migration scripts](infrastructure/database/sql_migrations/) and the
  [preflight](infrastructure/database/preflight.py) establish the source contract.
  Hardware timing workflows and isolated SQL integration tests remain unverified.
- **Configuration and compatibility:** default development target is
  `localhost\SQLExpress / LWBTestDB`. Windows Authentication is the default;
  explicit SQL-password authentication uses the per-user `database.ini`.
  These defaults are not evidence of any station's actual endpoint or credentials.
  Historical CSV/JSON runs remain review inputs, not automatic imports or a second
  write path. Logs, explicit diagnostic/report exports, COC workbooks, and
  per-user configuration remain local. See
  [database configuration](docs/DATABASE_ARCHITECTURE.md#approved-deployment-direction)
  and [data formats](docs/DATA_ARCHITECTURE.md#format-responsibilities).
- **Measurements and routing:** SM/MM is operator-selected, with independent
  model/mode criteria and session-scoped references. Loading runs preserves
  session references; a confirmed meter disconnect clears them. Part number
  determines front-panel count; SCPI-configured count is not physical capacity.
  `CLOSe?` confirms the logical channel only; assignment records supply the
  documented physical map. OSX-150 extras default to CLI for new settings,
  with explicit SCPI selection retained and the method fixed per run.
  Extra-only runs, CLI IP-readiness checking, and configurable timing/scheduled
  averaging are implemented. See [HARDWARE_ARCHITECTURE](docs/HARDWARE_ARCHITECTURE.md)
  and [timing profiles](domain/measurement_timing.py).
- **Analysis and COC:** replacement analysis uses assignment-wide effective
  evidence, persists immutable snapshots/recommendations, and detects staleness.
  Replacements document external reroutes; post-replacement readings verify
  their measured result. New hardware pairings start fresh assignment history.
  Compatible runs can contribute to COC without a two-run limit; the latest
  eligible whole wavelength pair wins, including newer failures. Purpose alone
  does not block technical analysis/COC. COC supports OSX-100 SM/MM and OSX-150
  SM, with all front-panel channels required; OSX-150 MM COC remains unsupported.
  See [effective analysis](domain/effective_replacement_analysis.py),
  [COC preparation](domain/coc_preparation.py), and DATA_ARCHITECTURE.
- **Other implemented surfaces:** database reports, purpose/station capture,
  accepted-reading history, managed persistent hardware leases, Live IL/Red Light/
  diagnostics, database health monitoring, and Clear Workspace. Clear Workspace
  unloads UI data while retaining connections and session references.
  [PROGRAM_DESIGN](docs/PROGRAM_DESIGN.md) owns workflow boundaries;
  [SUPPORT_LOGGING](docs/SUPPORT_LOGGING.md) owns local diagnostic evidence.
- **Milestones:** [DATABASE_ROADMAP](docs/DATABASE_ROADMAP.md) records 0-10A
  implemented and managed network Milestone 11 deferred.
  [REFACTOR_ROADMAP](docs/REFACTOR_ROADMAP.md) records the current refactor through
  Phase 6 complete. Those are implementation/history claims, not blanket manual
  acceptance. Separate real OPM/laser support remains future expansion.

Evidence labels used below:

- **Implemented:** located in current source/migrations; execution not implied.
- **Automated Verified:** an identified automated check passed at its stated
  revision/environment; test code alone does not earn this label.
- **Manual Verification Pending:** required physical, operator, SQL, or target
  environment checks have no sufficient completion record for this baseline.
- **Manually Verified:** a scoped, dated observation is recorded; it does not
  qualify other devices, firmware, stations, or later revisions.
- **Blocked:** a stated dependency prevents progress; include the dependency.
- **Superseded:** an older claim/workflow has been replaced, with its successor
  identified. Unknown issues remain open rather than being silently closed.

## Active Work

- Documentation governance Phases 1 and 2 are implemented (records below).
  No additional feature implementation or priority order is established by this
  review; Phase 3 needs a separate task.
- Supported pending work consists of the unresolved items and required manual
  verification below. The old generic contribution order is superseded by the
  completed refactor and SQL-primary cutover; it is not an approved backlog.
- Managed network rollout remains deferred under DATABASE_ROADMAP Milestone 11.
  Implemented temporary workgroup authentication does not establish production
  readiness or authorize that rollout.

## Open Bugs and Decisions

### LWB-DOC-001 - Conflicting requirements and workflow descriptions

- **Status/evidence:** Open documentation discrepancy; confirmed by text/source inspection.
- **Observed/expected:** [Requirements.md](Requirements.md) and the
  [checklist](docs/REQUIREMENTS_CHECKLIST.md) contain mixed-age statuses;
  [README.md](README.md) still describes desktop CSV storage. HARDWARE_ARCHITECTURE
  still calls live pacing a fixed 250 ms and mentions external-completion
  confirmation, while [timing profiles](domain/measurement_timing.py),
  [Live IL dialog](ui/live_il_reading.py), and the
  [replacement dialog](ui/database_replacements.py) implement configurable pacing
  and no bottom confirmation gate. Documents should describe their actual scope.
- **Next:** reconcile owning documents in separately approved work; preserve RevB
  as original intent, not current acceptance. No requirement statuses changed here.

### LWB-UI-001 - Unreachable legacy simulation UI

- **Status/evidence:** Needs decision; static issue remains present, not UI-reproduced.
- **Observed/expected:** `start_demo()`, `measure_demo()`, and `accept_demo()` in
  [ilm_app.py](ilm_app.py) reference demo widgets absent from `_build_ui()`;
  no current action wiring for `start_demo()` was found. A supported entry point
  should be usable or explicitly retired; this does not show a production-run failure.
- **Next:** decide whether to restore or remove the stale UI path, then verify
  that choice. Retain simulated adapters needed by tests.

### LWB-RET-001 - Historical opened-run retest concern

- **Status/evidence:** Needs investigation; inherited recommendation lacks a
  reproducible failure or a documented closure.
- **Observed/expected:** the old handoff recommended fixing persistence when
  retesting an opened run. Current [SQL workflow](application/database_primary_workflow.py)
  and [lifecycle](application/run_lifecycle_workflow.py) reopen retained runs;
  [lifecycle tests](tests/test_run_lifecycle_workflow.py) and
  [UI tests](tests/test_database_primary_ui.py) cover related behavior.
  Their existence does not resolve the unidentified historical case.
- **Next:** determine whether the report concerned legacy-file or SQL continuation,
  reproduce that case, and record persistence/attempt identity before closing.

### LWB-ENV-001 - Historical launcher and packaging warnings

- **Status/evidence:** Needs investigation; historical environment observations only.
- **Observed/expected:** the old handoff reports `py -3.11-32` could not find
  Python, a direct 32-bit interpreter worked, and a non-fatal `sip` hidden-import
  warning accompanied a successful build. Those observations do not describe
  today's interpreter registration or package readiness.
  [ilm_app.spec](ilm_app.spec) now names `PyQt5.sip`; the inspected local
  `build/ilm_app/warn-ilm_app.txt` did not contain that old warning.
- **Next:** when a build is requested, check interpreter bitness/registration and
  perform the documented clean-target smoke test. No build was run here.

### LWB-OPS-001 - Production operations and stale-run policy

- **Status/evidence:** Open decision; deployment acceptance remains pending.
- **Observed/expected:** DATABASE_ARCHITECTURE's remaining decisions include host/
  ownership, authentication/groups, backup/retention, and stale `in_progress`
  policy. [Run lifecycle](application/run_lifecycle_workflow.py) implements stale
  lookup/resume/close decisions, but no automatic startup stale-run prompt was
  located in [ilm_app.py](ilm_app.py). Service support is not proof of that UI.
- **Next:** agree production operations and recovery behavior; verify UI wiring
  and outage recovery before accepting Milestone 11. Do not assume the temporary
  workgroup setup resolves every production decision.

### LWB-HW-001 - Firmware coverage and diagnostic identity ambiguity

- **Status/evidence:** Open vendor/validation question; no new hardware testing.
- **Observed/expected:** [DLL reference](docs/ILM_DLL_FUNCTION_REFERENCE.md)
  records USB description OP815 but module ID 14 mapped to OP930 by vendor HTML.
  HARDWARE_ARCHITECTURE also leaves CLI response/readback qualification firmware-
  dependent; no default physical-port readback is approved.
- **Next:** retain the diagnostic evidence, seek vendor clarification, and test
  supported firmware before expanding capability claims. Do not infer model,
  mode, physical mapping, or command success from ambiguous fields.

## Pending Manual Verification

All rows are **Manual Verification Pending for this reviewed baseline** unless
a later scoped record supplies results. This does not erase earlier limited
observations. [TESTING_AND_RELEASE](docs/TESTING_AND_RELEASE.md) owns procedures.

| Area | Required evidence still to record |
| --- | --- |
| ILM/switch/firmware | Representative OSX-100/150 discovery, logical routing/mismatch handling, SCPI versus CLI extras, binary/unknown/error responses, unverified-route confirmation, IP recheck, return to normal routing, source-off cleanup, and stop/close/reconnect behavior. |
| Timing and references | One-, two-, and three-sample schedules, actual offsets/raw samples/mean, shared reference and Live IL behavior, saved-profile continuation/retest, manual SM/MM selection, dark/negative-reading gates, local/remote transitions, and disconnect invalidation. |
| Writes and iterative replacement | Rapid Live Write acceptance and channel advancement, retry after a failed commit, saved coverage, assignment isolation, replacement retest state, analysis reload/staleness/adoption history, and multi-run COC consistency using an actual run. |
| SQL network/deployment | Correct live schema, both approved authentication modes on target stations, permissions, concurrent creation/writes, cold-start/outage recovery, and measured remote load timings. DATABASE_ROADMAP records historical local integration backup/restore/`DBCC CHECKDB` success; it is not a current deployment result. Production backup/restore, retention, and stale-run recovery remain to qualify. |
| Packaging/target environment | Supported Windows/32-bit runtime, installed x86 VISA/ODBC/Visual C++ dependencies, packaged migration integrity, no private stale runtime DLLs, responsive startup/health indicator, and clean close. Follow the release verifier and packaged smoke test; no rebuild was requested here. |
| COC workbook and print | OSX-100 SM/MM and OSX-150 SM, 1-45 base and 46+ expandable 48-row base, replacement/composite provenance, graphics, merges, print area, and actual target-printer appearance. Check the environment-dependent part lookup/manual fallback. Workbook round-trip coverage is not printer qualification. |
| Operator presentation | Clear Workspace retaining hardware/reference, light/dark dialogs, and layouts on target monitors/DPI. Follow the applicable workflow checks rather than treating source/UI test inspection as operator acceptance. |

## Recent Implementation Records

Entries identify implementation and coverage, not fresh test runs.
Unless explicitly stated, verification here was source/test inspection only;
application tests, SQL connections, builds, hardware, and printer checks were
not performed during Phase 2.

| Date / revision | Change and verification boundary |
| --- | --- |
| 2026-11-11 / uncommitted against `5d49728` | **Implemented; manual UI check pending:** Copy Raw Data now prompts for 0-4 decimal places (default 2), rounds the clipboard-only TSV with decimal half-up semantics, preserves fixed trailing zeros, and leaves the clipboard unchanged on Cancel. The pure formatter retains its existing 4-place default for other callers and rejects unsupported precision. The copy still uses all accepted rows regardless of table filter. Updated IL Instructions, PROGRAM_DESIGN, and DATA_ARCHITECTURE. **Automated verified:** Python 3.11 x86 `-B -m unittest discover -s tests`: 805 tests OK, 12 SQL integration cases skipped; targeted raw-export/UI suite: 128 tests OK. No SQL schema/data, hardware, build, or packaged files changed. **Pending:** manually inspect the prompt and clipboard contents in the rebuilt app on a target workstation; build/deploy only when requested. |
| 2026-11-10 / uncommitted against `2aa4967` | **Implemented; physical/print checks pending:** Removed the 48-channel front-panel parser and COC preparation/export ceilings. The positive part-number count now drives a 49-channel database run, full-pass plan, status, and matching COC output. The 48-row model/mode template is expanded only in the output workbook: new rows copy the prior section's styles/height, extend merged return-loss specifications, preserve template drawings, and update print area/pagination. Single-channel selection now follows the part-number/configured count. Updated the operator guide and owning design/data docs. **Automated verified:** Python 3.11 x86 `-B -m unittest discover -s tests`: 801 tests OK, 12 isolated SQL cases skipped. Real-template 49-channel OSX-100 SM and 52-channel OSX-100 MM exports were reopened and checked for channels, IL data, formatting, merges, pagination metadata, and unchanged source templates/drawings. No 250-channel test was added. `git diff --check` passed. **Pending:** physically test the 49-channel OSX-100 run, inspect the generated 49-channel COC in Excel and on the target printer, and rebuild/deploy when requested; no live SQL write, hardware command, printer test, or build was performed here. |
| 2026-11-10 / `2aa4967` plus uncommitted timing implementation | **Migration deployed; read-only SQL verification passed:** user requested applying the new migration to the configured `localhost\SQLEXPRESS / LWBTestDB` using Windows Authentication. `python -B -m tools.migrate_database --server 'localhost\SQLEXPRESS' --database 'LWBTestDB' --trust-server-certificate --check` validated existing checksums and identified only 0007 pending; the same command without `--check` applied 0007 and reported schema 0007. Initial sandbox connection failed with Windows security/SSL error 08001; the approved unrestricted retry succeeded without changing configuration or weakening encryption. Runtime `check_database_preflight` then returned ready/current=7/expected=7. Read-only queries verified migration IDs 1..7, all nine session-table columns, the unique filtered open-session index, the five intended role grants, and a readable summary view. The new table contained zero sessions; all 20 existing runs correctly reported unavailable historical timing. No existing run data was rewritten, synthetic sessions inserted, hardware contacted, integration tests run, build performed, or commit created. Existing user build/dist/cache changes were preserved. **Next:** restart the updated application and manually verify start/stop/continue timing; isolated SQL integration, interruption/retry, and target-workstation verification remain pending. |
| 2026-11-10 / uncommitted against `2aa4967` | **Implemented; SQL/deployment verification pending:** approved durable active-test timing. Migration [0007](infrastructure/database/sql_migrations/0007_run_test_sessions.sql) adds IL_RUN_SESSIONS and vw_RunTimingSummary with application-role permissions. Domain records/summaries, monotonic clocks, coalesced 30-second/post-commit checkpoints, atomic normal final close/status, stale recovery at the last durable checkpoint, partial/legacy quality, frozen final retries, uncertain-start UUID recovery, pairing cleanup, Run information/session history, and numeric run/filtered-assignment report metrics are connected. Summed effort and interval union remain separate; no historical timing is fabricated. See [timing tests](tests/test_run_sessions.py), [fake SQL rollback tests](tests/test_run_session_sql.py), DATABASE_ARCHITECTURE, DATA_ARCHITECTURE, and TESTING_AND_RELEASE. **Automated Verified:** final `python -B -m unittest discover -s tests`: 798 tests, OK, 12 SQL-dependent cases skipped, 15.192 s (Python 3.11 x86). An initial suite found the two old schema-version assertions; these now expect 0007, and integration schema/view counts were updated. Sixteen changed/new Python modules passed syntax compilation with temporary caches outside the repository; HTML structure, migration discovery/batch parsing, and diff checks passed. Prior migration content and canonical checksums match HEAD; an initial raw-byte comparison encountered checkout CRLF versus Git LF, so the audit used the migration runner's normalized text/checksums. Optional Black was unavailable; no dependency was installed. **Not performed:** live SQL migration/integration, hardware or mapped-drive access, physical/target UI walkthrough, build, commit. **Next:** apply 0007 to the intended database with administrator tooling, run isolated integration checks, then manually exercise stop/continue/restart, outage/retry and controlled interruption, session history/report exports, station ownership, and light/dark layouts before deployment. |
| 2026-11-10 / uncommitted against `02ec8f8` | **Implemented; mapped-drive verification pending:** approved model-aware, strictly read-only part lookup. Shared parent configuration and exporter root resolution now cover automatic/manual lookup, opening the model directory (shared parent when unknown), and COC missing-part fallback. Loaded-run/COC identity is independent of unrelated connected hardware; unknown models require one match across both accessible directories. Duplicate, unavailable, and model-inconsistent results are rejected; background results are guarded by request, serial, and model. Legacy explicit-root calls remain supported. See [PROGRAM_DESIGN](docs/PROGRAM_DESIGN.md), [DATA_ARCHITECTURE](docs/DATA_ARCHITECTURE.md#read-only-product-log-lookup), and [lookup regression tests](tests/test_model_part_number_lookup.py). **Automated Verified:** `python -B -m unittest discover -s tests`: 769 tests, OK, 10 SQL-dependent cases skipped (Python 3.11 x86; no SQL integration configured). Targeted lookup/controller/COC/UI suite passed 150 tests before the final COC fallback test; the full suite includes that additional test. Its initial fixture referenced nonexistent `ready_for_export`; corrected to `eligible`, then the isolated test and full suite passed. Eight changed Python files passed `py_compile` with temporary caches outside the repository; guide HTML structure, lookup mutation-call audit, and `git diff --check` passed. Filesystem-mutation/file-open guards and unchanged temporary-folder contents verify the read-only lookup boundary. No U: access, hardware/SQL connections, build, or commit performed. Existing guide/handoff edits preserved. **Next:** verify OSX-100 SM/MM and OSX-150 lookups on the actual mapped share; rebuild only when requested. |
| 2026-11-04 / uncommitted against `02ec8f8` | **Implemented (documentation only):** updated [IL Instructions](ILM_READING_GUIDE.html) against current source: database health/purpose, timing and scheduled dBm averaging, persistence acknowledgement, independent extra-only and SCPI/CLI/IP workflows, assignment-scoped analysis history, replacement recording/verification, voiding/new pairings, and automatic unlimited multi-run COC/latest-whole-pair selection. Clarified the existing stricter COC boundary without changing policy or code. **Document checks passed:** balanced HTML, 14 numbered sections plus quick checklist, seven rectangular tables, 12 UI labels checked against source, obsolete procedure removal, unchanged CSS, and `git diff --check`. No application tests, hardware/SQL operations, acceptance tests, browser-rendering review, or build performed. **Manual Verification Pending:** operator walkthrough in the installed build; packaged guide refresh requires the normal requested rebuild. Only the root guide and this handoff changed. |
| 2026-11-03 / `11a0068` | **Implemented:** governance Phase 1 added AGENTS.md and updated docs/README.md. Guidance and links inspected during this review; application behavior was outside its scope. |
| 2026-11-02 / `de87dda` | **Implemented; Manual Verification Pending:** scheduled 1-3 power samples and arithmetic mean, timing configuration, raw trace evidence, and saved-profile use. Coverage exists in [timing tests](tests/test_measurement_timing.py), [OP815 tests](tests/test_op815_driver.py), and [UI tests](tests/test_ilm_app.py); not rerun here. |
| 2026-11-02 / `4c80fac` | **Implemented; Manual Verification Pending:** CLI unassigned-IP warning/recheck and OSX-150 CLI default. [Worker tests](tests/test_measurement_worker.py) and [settings tests](tests/test_limit_profile_repository.py) cover seams; actual firmware/network behavior still needs qualification. |
| 2026-10-30 / `509b811`, `983481f` | **Implemented; Manual Verification Pending:** background database health/Clear Workspace and ILM remote/local control, respectively. See [health tests](tests/test_database_health_monitor.py) and [hardware-manager tests](tests/test_hardware_connection.py); target startup and device transitions not retested here. |
| 2026-10-30 / `9d7f527` | **Implemented:** load-stage instrumentation, bounded read sessions/bulk retrieval, immutable loaded context, and query-free automatic UI publication. [Load tests](tests/test_database_primary_workflow.py) and [UI load tests](tests/test_database_primary_ui.py) exist; historical benchmark evidence is scoped below. No universal speedup or cold-start reliability claim is inferred. |
| 2026-10-29/30 / `34ed981`, `87b6b41` | **Implemented; Manual Verification Pending:** explicit SQL-password runtime authentication, then packaging exclusion/rejection of private Visual C++ runtimes. See [connection tests](tests/test_database_connection.py), [build script](build_windows.ps1), [release verifier](verify_release.ps1), and TESTING_AND_RELEASE. |
| 2026-10-28/29 / `18737d1`, `616e84c`, `e0fe5f6` | **Implemented; Manual Verification Pending:** assignment-wide iterative analysis/voiding, authoritative channel roles, and logical-only `CLOSe?` contract. Migrations 0005/0006, [analysis tests](tests/test_effective_replacement_analysis.py), and [switch tests](tests/test_optical_switch.py) support source inspection; representative hardware acceptance remains pending. |

Historical evidence retained with its limits:

- **Reported Automated Verified, historical:** `c985f34` (2026-10-06) introduced
  the old handoff's `python -m unittest discover -s tests`: **342 tests passed**
  statement. That handoff also reported `python -m compileall -q -f .` passed
  and a successful PyInstaller build. These are inherited reports, not raw
  execution logs or current-baseline results; the old header's 2026-10-13 review
  date does not make the count current.
  The old handoff also reports a real-template COC round-trip smoke check;
  target-printer review remained pending, and no execution artifact is linked.
- **Unverified historical audit report:** **748 passing tests and 10 skips**
  was supplied as previous-audit context. No supporting result or introducing
  change was found in the searched repository Markdown/text/log records or their
  Git history. Do not cite it as current verification or infer why tests skipped;
  rerun the appropriate suite when verification is requested.
- **Historical benchmark observation:** the artifacts committed in `9d7f527`,
  [baseline](build/database-run-load-baseline-99190-run1.json) and
  [Phase 2](build/database-run-load-phase2-99190-run1.json), report 20 connections/
  19 transactions versus 1/1 per load for unit 99190, run 1. Their workflow
  durations are source-tree samples, not packaged remote-station UI latency.
  Preserve these as historical evidence; use the documented benchmark and
  station logs for new comparisons.
- **Reported Manually Verified, limited historical scope:** the DLL reference
  records one OP815-described device (USB serial 00016582, firmware 202) returning
  diagnostics and closing cleanly, with the module-ID ambiguity in LWB-HW-001.
  No date/revision-bound qualification of the present feature set follows.
- **Superseded:** desktop CSV/JSON as the new-run write path, session-only database
  analysis, the eight-table/two-view schema summary, SCPI as the new-settings
  default, a configurable 64-port probe ceiling, and the unfinished-refactor
  narrative. Current source uses SQL-primary persistence, eleven tables/five views,
  persisted analyses, a CLI default, and a fixed internal 512 guard. The guard
  is not installed capacity. Legacy format details remain in DATA_ARCHITECTURE.

Phase 2 implementation record (2026-11-03, uncommitted against `11a0068`):

- **Implemented:** replaced the mixed-age handoff with these six sections,
  source-backed baseline, stable unresolved-item IDs, verification boundaries,
  compact implementation history, and the reusable template below.
- **Verification:** all 55 local Markdown links resolve, including the two
  section anchors; the six required sections and template fences were checked.
  Claims were reviewed against source/migrations/Git; `git diff --check` passed
  and Git status confirmed only this file changed. Application tests were not
  run for this documentation-only task; no runtime acceptance is claimed.
- **Remaining:** unresolved items/manual checks above. Phase 3 was not started.

## Handoff Record Template

Use this compact format for meaningful future tasks; link to owning documents
instead of repeating architecture. Update existing issue IDs when applicable.

```text
Date / task / approval basis:
Source revision / branch / application version:
Status: Implemented | Automated Verified | Manual Verification Pending |
        Manually Verified | Blocked | Superseded (combine when appropriate)
Change and affected files:
Evidence: exact commands/results, failures/skips, environment, artifact links;
          distinguish source inspection, execution, and inference.
Manual checks: performed (scope/result) / pending / not applicable, with reason.
Issues/decisions: stable IDs, observed versus expected, unresolved assumptions.
Remaining work / dependency / next authorized action:
Commit: hash if committed; otherwise uncommitted.
```
