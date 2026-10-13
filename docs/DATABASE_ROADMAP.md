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

- Approve the eight tables and two read-only views.
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

Status: complete. Migration `0001_initial_schema.sql`, checksum/history
validation, the eight tables, two views, least-privilege database roles,
guarded reset tooling, and isolated SQL integration tests are implemented. The
local `LWBTestDB_Integration` database has been reset, migrated, backed up,
restored to a temporary database, checked with `DBCC CHECKDB`, and cleaned up
using 32-bit Python, `pyodbc`, Windows Authentication, and ODBC Driver 18.

### Implement

- Create forward-only migration scripts for `LWBTestDB`.
- Create `UNITS`, `SWITCHES`, `UNIT_SWITCH_ASSIGNMENTS`, `IL_RUNS`,
  `IL_MEASUREMENTS`, `CHANNEL_REPLACEMENTS`, `DESIGNATED_SPARES`, and
  `SCHEMA_MIGRATIONS`.
- Create `vw_CurrentILMeasurements` and `vw_CurrentChannelMap`.
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

Status: complete. Non-secret per-user SQL Server settings, a bounded
Windows-authenticated connection factory, short transaction contexts,
read-only migration compatibility preflight, classified operator diagnostics,
and credential-free support events are implemented. Database use remains
disabled by default and is not yet connected to run persistence; that begins
with repository work in Milestone 3.

### Implement

- Add configurable SQL Server instance and database settings.
- Use Windows Authentication without embedded credentials.
- Add a database connection factory under `infrastructure/`.
- Add bounded connections, parameterized commands, and short transactions.
- Add startup/explicit connection diagnostics and schema compatibility checks.
- Classify authentication, server unavailable, timeout, permission, and schema
  errors for operator feedback and local support logs.

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
migrations automatically.

## Milestone 3 - Repository contracts

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

### Implement

1. Resolve or create a unit by main-board serial.
2. Resolve or create a switch by switch serial.
3. Find the active unit/switch assignment.
4. Create the baseline logical-to-physical map for a new assignment.
5. Close an old assignment when a physical switch is removed.
6. Create a new assignment for the replacement switch.
7. Prevent one unit or switch from participating in conflicting active
   assignments.

### Tests

- Reconnecting the same unit/switch reuses the active assignment.
- Replacing a switch preserves the old assignment and its runs.
- A switch cannot be active in two units simultaneously.
- Invalid or missing baseline channel maps are rejected.
- Physical channel count and front-panel channel count remain distinct.

### Exit criteria

- Every future run can reference one unambiguous installed unit/switch pair.

## Milestone 5 - Run lifecycle persistence

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
- Engineering/training data is excluded from normal production analysis.
- A stale run is not silently marked complete.

### Exit criteria

- Every database-backed run has stable identity, assignment, context, and a
  valid lifecycle state.

## Milestone 6 - Atomic measurement persistence

### Implement

- Generate `measurement_uuid` before insertion.
- Validate a complete two-wavelength sample before writing.
- Store both wavelength/IL pairs and the reference snapshot in one row and one
  transaction.
- Allocate `attempt_number` safely for each run/logical channel.
- Mark a reading accepted in the UI only after commit succeeds.
- Leave failed writes temporary and retryable without advancing the channel.
- Keep raw power, temporary readings, live samples, and rejected samples out of
  `IL_MEASUREMENTS`.

### Tests

- SM 1310/1550 and MM 850/1300 rows round-trip at four-decimal precision.
- A transaction cannot produce a one-wavelength measurement.
- Retrying the same UUID is idempotent.
- Parallel or repeated attempts cannot claim the same attempt number.
- Database failure does not alter the current accepted projection.
- Invalid/negative/unwritten readings are absent from the database.

### Exit criteria

- Write IL is atomic, retry-safe, and preserves the existing acceptance rules.

## Milestone 7 - Retest and current-value queries

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

### Implement

- Store replacements against `assignment_id` rather than permanently against a
  unit.
- Append reason, operator, timestamp, previous port, replacement port, and
  optional related run.
- Append spare designation and undesignation events.
- Use `vw_CurrentChannelMap` to combine the baseline assignment map with the
  latest replacement per logical channel.
- Keep replacement recommendations derived and temporary.
- Do not command or verify external switch mapping changes.

### Tests

- Multiple replacements of one channel retain complete history.
- Replacements from a removed switch do not affect a new assignment.
- Current-map queries return the latest effective port.
- Spare designation history produces the correct active set.
- Replacement records survive run changes and remain attributable.

### Exit criteria

- Database queries can reconstruct the effective map and full documentation
  history for each assignment.

## Milestone 9 - Database-primary cutover

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
9. Pilot future data on the network server.
10. Enable reporting after backup and restore procedures are proven.

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
- Non-production and excluded runs do not contaminate normal analysis.
- Local support logs remain independent from analytical storage.
- Database failures are visible and cannot silently lose or falsely accept a
  reading.
- SQL Server can be backed up, restored, and queried by approved workstations.
