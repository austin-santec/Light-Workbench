# Database Implementation Roadmap

## Purpose

This roadmap implements the approved SQL Server schema in
`docs/DATABASE_ARCHITECTURE.md`. It applies to the database-focused development
branch and intentionally starts with future data. Existing local runs are not
scheduled for bulk import.

The current file-backed application remains usable while development proceeds.
The database branch does not become SQL Server-primary until its write, query,
failure, and recovery behavior has been verified against the existing domain
rules.

## Milestone 0 - Freeze the database contract

### Implement

- Approve the ten tables and four read-only views.
- Approve SQL Server types, nullable fields, status vocabularies, and JSON
  shapes.
- Approve identity, foreign-key, unique, check, and append-only rules.
- Define database-unavailable and stale-`in_progress` behavior.
- Confirm that historical bulk import, SQLite, and local synchronization are
  out of scope.

### Deliverables

- Reviewed data dictionary.
- Entity relationship diagram.
- Status transition table.
- JSON examples for channel maps, hardware, limits, and references.
- Permission matrix for application read/write and reporting read-only roles.

### Exit criteria

- No unresolved naming or ownership questions remain in the initial schema.
- Completion status is separate from derived pass/fail quality.
- Unit/switch assignments and replacement ownership are unambiguous.

## Milestone 1 - SQL Server foundation

Status: complete. Forward-only migrations through
`0006_authoritative_channel_roles.sql`, checksum/history validation, the
ten tables, four views, least-privilege database roles,
guarded reset tooling, and isolated SQL integration tests are implemented. The
local `LWBTestDB_Integration` database has been reset, migrated, backed up,
restored to a temporary database, checked with `DBCC CHECKDB`, and cleaned up
using 32-bit Python, `pyodbc`, Windows Authentication, and ODBC Driver 18.

### Implement

- Create forward-only migration scripts for `LWBTestDB`.
- Create `UNITS`, `SWITCHES`, `UNIT_SWITCH_ASSIGNMENTS`, `IL_RUNS`,
  `IL_MEASUREMENTS`, `CHANNEL_REPLACEMENTS`, `DESIGNATED_SPARES`,
  `REPLACEMENT_ANALYSES`, `REPLACEMENT_ANALYSIS_RECOMMENDATIONS`, and
  `SCHEMA_MIGRATIONS`.
- Create `vw_CurrentILMeasurements`, `vw_CurrentChannelMap`, and
  `vw_ReplacementRecommendationUsage`.
- Add foreign keys, checks, unique constraints, filtered active-assignment
  indexes, and reporting indexes.
- Configure Windows Authentication roles.
- Create a separate integration-test database, such as
  `LWBTestDB_Integration`.
- Verify that the selected ODBC driver works with supported 32-bit Python.

### Tests

- Apply all migrations to an empty database.
- Re-running the migration command makes no duplicate changes.
- A modified migration checksum is detected.
- Unsupported future schema versions are rejected.
- Constraints reject invalid JSON, duplicate UUIDs, invalid status values,
  duplicate active assignments, and incomplete measurement pairs.
- Back up and restore the disposable integration database before applying the
  same operational process to development or production data.

### Exit criteria

- A clean SQL Server Express instance can be prepared repeatably.
- The schema is inspectable in SQL Server Management Studio.
- The integration database can be reset without touching development data.

## Milestone 2 - Connection and configuration boundary

Status: complete. Non-secret per-user SQL Server settings, automatic create-only
initialization of the per-user `database.ini`, preservation of existing files,
invalid-file validation, a credential-free example configuration, a bounded
Windows-authenticated connection factory, short transaction contexts,
read-only migration compatibility preflight, classified operator diagnostics,
and credential-free support events are implemented. Database use is enabled by
default on the database branch and production persistence is connected by
Milestone 9.

### Implement

- Add configurable SQL Server instance and database settings.
- Use Windows Authentication without embedded credentials.
- Add a database connection factory under `infrastructure/`.
- Add bounded connections, parameterized commands, and short transactions.
- Add startup/explicit connection diagnostics and schema compatibility checks.
- Classify authentication, server unavailable, timeout, permission, and schema
  errors for operator feedback and local support logs.
- Create `%LOCALAPPDATA%\LightWorkbench\config\database.ini` on first database
  initialization when missing, without replacing existing configuration.
- Reject malformed or invalid existing configuration with actionable feedback;
  do not silently fall back to hidden defaults.
- Keep the example file `config/database.ini.example` free of credentials and
  outside the runtime configuration path.

### Tests

- Valid Windows-authenticated connection.
- Unavailable server and invalid instance.
- Missing database.
- Insufficient permissions.
- Unsupported schema version.
- Connection cleanup after success and failure.

### Exit criteria

- UI and hardware modules do not know connection-string or SQL details.
- Connection failures are actionable and do not expose credentials.

### Operator/developer diagnostic

Database settings are stored in
`%LOCALAPPDATA%\LightWorkbench\config\database.ini`. The file contains only
the endpoint, database, driver, encryption policy, and bounded timeouts. It
never stores a username or password because the process uses Windows
Authentication.

Run the read-only readiness check with:

```powershell
python -m tools.check_database_connection
```

The diagnostic validates connectivity and migration history but never applies
migrations automatically. If the configured file is missing, the supported
database bootstrap creates it first using the documented defaults. An explicit
`--config` path is also handled through the same repository and validation
rules.

## Milestone 3 - Repository contracts

Status: complete. Database-neutral typed records and protocols now define the
unit, switch, assignment, run, measurement, replacement, and spare boundaries.
Matching in-memory and parameterized SQL Server implementations pass the same
contract, including retry-safe UUID behavior, current-versus-history reading
queries, lifecycle transitions, and transaction rollback/cleanup. These
repositories remain disconnected from the production UI and file workflow
until the following integration milestones.

### Implement

- Define repository protocols for units, switches, assignments, runs,
  measurements, replacements, and spares.
- Implement fake/in-memory repositories for hardware-free workflow tests.
- Implement SQL Server repositories in `infrastructure/`.
- Keep entity validation and status transitions in `domain/` or
  `application/`, not in Qt widgets.
- Keep SQL statements private to infrastructure modules.

### Required operations

```text
UnitRepository.get_or_create(...)
SwitchRepository.get_or_create(...)
AssignmentRepository.get_active(...)
AssignmentRepository.install(...)
AssignmentRepository.remove(...)
RunRepository.create(...)
RunRepository.finish(...)
RunRepository.find_stale_in_progress(...)
MeasurementRepository.append_attempt(...)
MeasurementRepository.current_for_run(...)
MeasurementRepository.history_for_run(...)
ReplacementRepository.append(...)
SpareRepository.append_event(...)
```

### Tests

- Repository contract tests run against fakes and the integration database.
- SQL injection-like input remains data rather than executable SQL.
- Duplicate UUID retries resolve existing records safely.
- Failed operations roll back their transactions.

### Exit criteria

- Application workflows can depend on repository interfaces without importing
  database-specific packages.

## Milestone 4 - Unit, switch, and assignment workflow

Status: complete at the application/repository boundary. The workflow now
resolves or creates units and switches, reuses matching active assignments,
uses one confirmation for a genuinely new pairing, automatically closes all
affected active assignments, stops unfinished runs, validates a fresh identity
baseline, and atomically creates the new assignment and first run. It assumes
the external module-map reset and does not command or verify hardware mapping.

### Implement

1. Resolve or create a unit by main-board serial.
2. Resolve or create a switch by switch serial.
3. Find the active unit/switch assignment.
4. Create the baseline logical-to-physical map for a new assignment.
5. Close every conflicting active assignment when a new pairing is confirmed.
6. Stop unfinished runs on those assignments in the same transaction.
7. Create a new assignment and first run with a fresh identity map.
8. Prevent one unit or switch from participating in conflicting active
   assignments.

### Tests

- Reconnecting the same unit/switch reuses the active assignment.
- Replacing a switch preserves the old assignment and its runs.
- A switch can be paired with a different main board after one confirmation.
- Both destination and source conflicts are resolved together.
- Unfinished conflicting runs are stopped without deleting measurements.
- A new pairing does not inherit mapping, replacement, spare, or analysis data.
- Invalid or missing baseline channel maps are rejected.
- Front-panel count is authoritative; the last SCPI-reported count remains
  diagnostic and does not impose replacement capacity.

### Exit criteria

- Every future run can reference one unambiguous installed unit/switch pair.

## Milestone 5 - Run lifecycle persistence

Status: complete at the application/repository boundary. New database-backed
runs now require a successful readiness result, receive a caller-generated
retry UUID, and obtain a per-unit run number while the SQL repository holds a
unit-scoped transaction lock. Runs preserve their setup, hardware, and limit
snapshots and support explicit complete, stopped, and failed endings.
Purpose and analysis eligibility are separate, no purpose is implicitly voided,
and stale runs remain in progress until an explicit resume,
close-stopped, or close-failed decision. Production Start Run is wired to this
workflow; the UI defaults new runs to Production and records the selected
purpose.

### Implement

- Require a successful database/schema preflight before a production run.
- Generate `client_run_uuid` before the first insertion attempt.
- Allocate the unit's operator-facing run number transactionally.
- Insert an `in_progress` run with part-number, channel-count, hardware, and
  limit snapshots.
- Transition the run to `complete`, `stopped`, or `failed` with
  `run_ended_at_utc`.
- Add production, engineering, training, and calibration purpose choices.
- Add pending, included, excluded, and superseded analysis status.
- Require an exclusion reason when appropriate.
- Detect stale `in_progress` runs and present an explicit resume/close
  workflow.

### Tests

- Duplicate create retry does not create a second run.
- Completion status never doubles as measurement pass/fail.
- A complete run may contain formally failing measurements.
- A stopped run retains accepted measurements.
- A failed run records the technical end state.
- Engineering/training data remains distinguishable in production-only reports
  without being implicitly voided from technical analysis.
- A stale run is not silently marked complete.
- Purpose is preserved through loaded-run continuation and retest workflows.

### Exit criteria

- Every database-backed run has stable identity, assignment, context, and a
  valid lifecycle state.

## Milestone 6 - Atomic measurement persistence

Status: complete at the application/repository boundary. Write IL data is
prepared as an immutable pending two-wavelength value with a stable UUID before
the first database attempt. The repository locks the run, verifies that it is
still in progress and that the wavelength pair matches its SM/MM mode,
allocates the next run/channel attempt number, and inserts the complete sample
in one transaction. Finite non-negative losses are normalized to four decimal
places, and a reference snapshot is mandatory. Commit notification occurs only
after repository success, so a failed write remains retryable with the same
UUID and cannot alter the accepted projection. Production Write IL remains on
the file workflow until the database-primary cutover milestone.

The database-backed hardware worker now participates in the same acceptance
boundary. It receives a token for each displayed provisional sample and does
not advance to the next channel until the UI reports a matching successful
commit (run, operation, measurement UUID, logical channel, physical port, and
attempt number). A failed commit leaves the exact pending sample retryable;
reading/repeat requests cannot silently advance it. Run completion performs a
fresh persisted-coverage reconciliation and leaves the database run open when
any planned channel is missing.

### Implement

- Generate `measurement_uuid` before insertion.
- Validate a complete two-wavelength sample before writing.
- Store both wavelength/IL pairs and the reference snapshot in one row and one
  transaction.
- Allocate `attempt_number` safely for each run/logical channel.
- Mark a reading accepted in the UI only after commit succeeds.
- Leave failed writes temporary and retryable without advancing the channel.
- Acknowledge persistence only with the exact displayed sample token.
- Reconcile persisted coverage before marking a hardware run `complete`.
- Keep raw power, temporary readings, live samples, and rejected samples out of
  `IL_MEASUREMENTS`.

### Tests

- SM 1310/1550 and MM 850/1300 rows round-trip at four-decimal precision.
- A transaction cannot produce a one-wavelength measurement.
- Retrying the same UUID is idempotent.
- Parallel or repeated attempts cannot claim the same attempt number.
- Database failure does not alter the current accepted projection.
- A mismatched or missing persistence acknowledgement does not advance the
  worker or mark a channel complete.
- Completion is blocked and missing channels are reported when the persisted
  run projection is incomplete.
- Invalid/negative/unwritten readings are absent from the database.

### Exit criteria

- Write IL is atomic, retry-safe, and preserves the existing acceptance rules.

## Milestone 7 - Retest and current-value queries

Status: complete at the database application/repository boundary. Accepted
retests remain append-only, while a stable repository snapshot returns the
`vw_CurrentILMeasurements` projection and every accepted attempt from one
transaction. A shared database run snapshot now supplies the readings table,
run status, comparison, Copy Raw Data, analysis, COC preparation, and
replacement analysis so those consumers cannot select different attempts.
Current rows retain logical-channel order, history retains database commit
order, table filtering remains presentation-only, and temporary readings are
absent. The production UI continues using local runs until the database-primary
cutover in Milestone 9.

### Implement

- Use append-only rows for accepted retests.
- Use `vw_CurrentILMeasurements` for the current result per channel.
- Back Reading History with all attempt rows.
- Move readings-table, run-status, comparison, Copy Raw Data, analysis, COC,
  and replacement inputs to repository queries over the current view.
- Preserve existing logical channel ordering and table-filter independence.

### Tests

- Retesting appends an attempt and preserves the original.
- The current view selects the highest attempt only.
- History returns every accepted attempt in order.
- COC, analysis, clipboard, and visible readings agree on the current values.
- Temporary readings never appear in history or current views.

### Exit criteria

- Current behavior remains latest-only where expected while complete accepted
  history is queryable.

## Milestone 8 - Replacement and spare persistence

Status: complete at the database application/repository boundary. Replacement
records and spare designation changes are append-only and owned by the exact
unit/switch assignment. The workflow records operator, reason, timestamp,
previous/effective port, optional related run, and notes without issuing switch
commands or using switch route queries. Repository validation prevents stale
replacement chains, duplicate effective routes, unconfirmed candidate ports,
cross-assignment related runs, and changes to removed assignments.
`vw_CurrentChannelMap` supplies the effective logical-to-physical map, while a
stable routing snapshot exposes complete replacement/spare history and the
current designated-spare set. Normal replacements and spare designations use
assignment-scoped confirmed extra measurements rather than a stored capacity
ceiling. Replacement analysis is now persisted as an
append-only run snapshot, while recommendations remain advisory and do not
change the external mapping.

### Implement

- Store replacements against `assignment_id` rather than permanently against a
  unit.
- Append reason, operator, timestamp, previous port, replacement port, and
  optional related run.
- Append spare designation and undesignation events.
- Use `vw_CurrentChannelMap` to combine the baseline assignment map with the
  latest replacement per logical channel.
- Persist each completed replacement-analysis snapshot and its normalized
  recommendations.
- Store a compact assignment-wide source snapshot and deterministic fingerprint
  so measurement, mapping, replacement, spare, or criteria changes make an
  older result visibly stale.
- Link an approved replacement to its source recommendation when selected.
- Do not command or verify external switch mapping changes.
- Derive post-replacement verification from accepted measurements on the
  recorded effective physical port.
- Support iterative selected-channel verification runs and subsequent analysis
  using unchanged channels and unused extras from compatible earlier runs.
- Validate replacement batches against one freshly loaded authoritative routing
  snapshot before opening the write transaction. The editor permits one
  pending replacement per logical channel, captures the expected current port,
  reports stale/no-op/duplicate requests precisely, and preserves queued work
  after a failed save for correction and retry.

### Tests

- Multiple replacements of one channel retain complete history.
- Replacements from a removed switch do not affect a new assignment.
- Current-map queries return the latest effective port.
- Spare designation history produces the correct active set.
- Replacement records survive run changes and remain attributable.
- A multi-channel replacement batch is order-independent, and invalid batches
  commit neither replacement nor spare events.
- Confirmed candidates above the SCPI count remain valid for the same
  assignment; unmeasured candidates and candidates from another assignment are
  rejected.

### Exit criteria

- Database queries can reconstruct the effective map and full documentation
  history for each assignment.

## Milestone 9 - Database-primary cutover

Status: complete. Production application startup now composes the SQL Server
workflow. Start Run performs database/schema preflight, resolves unit/switch
assignment identity, and creates an authoritative `in_progress` run with a
database-allocated unit run number. Write IL commits one complete,
retry-identified two-wavelength attempt before the UI advances. Completion,
manual stop, and hardware failure close the database lifecycle explicitly.
Explicit continuation/retest reopens the retained run before appending a new
attempt, then closes it again without deleting earlier accepted attempts.
Numbered run loading, comparison, reading history, analysis, Copy Raw Data,
COC preparation, and replacement/spare records use database projections.
Legacy CSV files remain viewable without upload, automatic local run files are
not created, and support/diagnostic/COC outputs retain their intended local
file behavior.

### Development transition

During development, compare database repository results with the existing file
repository using controlled test runs and synthetic data. This is verification,
not a permanent dual-write architecture.

### Final behavior

- SQL Server becomes authoritative for new run data on this branch.
- New runs no longer require automatic CSV/JSON persistence.
- Existing files may remain viewable, but opening one does not upload it.
- Explicit CSV/JSON exports remain available if retained as an operator feature.
- COC and diagnostic exports remain generated files.
- Support logs remain local.
- Red Light Test and Power Measurement Diagnostics may operate without the
  run database because they do not write production runs.

### Database outage behavior

- Start Run is blocked if database/schema preflight fails.
- A mid-run failed Write IL stays temporary in memory and offers retry.
- The application does not advance in a way that loses the pending reading.
- Support logs record the database failure but never act as a measurement
  outbox.

### Tests

- Database-backed results match established domain behavior.
- No automatic local run file is required after cutover.
- Explicit exports do not become authoritative storage.
- Startup and mid-run database failures provide clear operator guidance.
- Existing non-recording tools remain available as designed.

### Exit criteria

- New production data can be created, resumed, queried, analyzed, and exported
  using SQL Server as the source of truth.

## Milestone 10 - Reporting

Status: complete. `Tools > Database Reports...` provides read-only joined
assignment/run history, selected-run channel and retest history, replacement
outcomes, saved-limit result derivation, production-safe filtering, explicit
troubleshooting scope, and per-tab CSV export. The application layer owns
filtering and derivation, Qt owns presentation and file selection, and report
queries do not mutate authoritative records.

### Implement

- Add read-only queries for unit, switch, assignment, run, and channel history.
- Filter by model, mode, operator, date, completion, purpose, and analysis
  status.
- Add retest-frequency and replacement-outcome reporting.
- Derive pass/fail and optimization from current measurements and the saved
  limit snapshot.
- Exclude pending, excluded, superseded, and non-production data from normal
  production metrics unless explicitly requested.
- Add CSV export of report results.

### Exit criteria

- Users can answer normal production and troubleshooting questions without
  scanning local run folders.
- Derived results can be reproduced from stored measurements and snapshots.

## Milestone 10A - Persistent replacement-analysis history

Status: complete, including migration 0005. Analyses now use an immutable,
assignment-scoped effective projection and classify optimized,
recommendations-available, verification-required, pass-without-viable-
optimization, fail-without-viable-recovery, incomplete, and review-required
states. Administrators can permanently void an invalid entire run without
deleting its readings or saved analyses. Switch-assignment boundaries prevent
old switch data from contributing to a new installation period.

Status: complete. Every database-backed Analyze Replacements action saves an
immutable analysis header and normalized recommendation rows. Loading a run
restores the latest snapshot and its full history; a newer accepted measurement
marks the latest snapshot stale instead of silently displaying old advice.
Selecting a saved recommendation in the replacement editor carries its ID
into the append-only replacement record, allowing adoption reporting through
`vw_ReplacementRecommendationUsage`.

### Scope safeguards

- Analysis persistence never changes a switch route or verifies an external
  reroute.
- A failed database save does not publish the calculated result as authoritative
  and reports the failure to the operator.
- File-backed legacy runs keep their existing session-local analysis behavior;
  no historical file import is introduced.

## Milestone 11 - Network pilot and production hardening

### Implement

- Deploy the migrations to the approved network SQL Server.
- Configure Windows/domain groups and least-privilege roles.
- Enable encrypted database connections.
- Pilot with one or two workstations and non-critical future data.
- Test concurrent run creation and measurement writes.
- Measure database growth and query performance.
- Configure backup, retention, restore drills, and database health monitoring.
- Document workstation configuration, database outage procedures, and stale-run
  recovery.

### Exit criteria

- Multiple workstations create future data without duplicate identities or
  conflicting assignments.
- Backup restoration is demonstrated.
- Expected capacity is confirmed with measured pilot data.
- Operators and support staff have documented recovery procedures.

## Source placement

```text
domain/          Database-independent entities, validation, status, and rules
application/     Run/measurement/assignment orchestration and recovery flows
infrastructure/  SQL Server connection factory, migrations, and repositories
config/          Non-secret database endpoint and application settings
ui/              Connection status, recovery prompts, and reporting screens
tests/           Fake repository tests and isolated SQL integration tests
docs/            Architecture, operations, and schema guidance
```

Root-level compatibility facades should not become SQL ownership boundaries.
No hardware adapter or Qt widget should execute database commands directly.

## Testing strategy

Every milestone includes:

- Hardware-free unit tests for domain and application rules.
- Shared repository contract tests.
- SQL integration tests against `LWBTestDB_Integration`, never development or
  production data.
- Transaction rollback and idempotency tests.
- Failure classification and recovery tests.
- Qt tests only for visible workflow behavior.
- No connected hardware requirement for automated tests.

Run the project checks from `docs/TESTING_AND_RELEASE.md`, including the full
unittest suite, compilation of changed Python modules, and `git diff --check`.

## Release strategy

1. Freeze and document the schema.
2. Validate migrations and Windows Authentication locally.
3. Implement repository contracts and fakes.
4. Persist unit/switch assignments and run lifecycle.
5. Persist accepted measurements and retests atomically.
6. Move replacement/spare history and current-value queries to SQL Server.
7. Complete controlled database/file parity testing.
8. Cut the database branch over to SQL Server-primary behavior.
9. Enable read-only database reporting with production-safe defaults.
10. Pilot future data on the network server and prove operational recovery.

The executable must not be rebuilt merely because documentation or database
scripts changed. Follow the normal version and build policy once runtime code
is introduced.

## Success criteria

The implementation is successful when:

- Every future production run has stable unit, switch, assignment, and UUID
  identity.
- Every accepted reading is a complete, atomic two-wavelength record.
- Retests remain append-only and the current projection is deterministic.
- Replacement and spare history cannot leak across switch assignments.
- Production-only reports remain purpose-filtered, while explicitly voided and
  superseded runs cannot contaminate technical analysis or COC preparation.
- Local support logs remain independent from analytical storage.
- Database failures are visible and cannot silently lose or falsely accept a
  reading.
- SQL Server can be backed up, restored, and queried by approved workstations.
