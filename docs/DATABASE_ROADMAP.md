# Database Implementation Roadmap

## Purpose

This roadmap turns `docs/DATABASE_ARCHITECTURE.md` into small, testable
milestones. Each milestone should leave the current application usable and
should be completed with tests and documentation before the next begins.

The current CSV/JSON workflow is the compatibility baseline. No milestone may
remove or weaken that workflow without a separate approved change.

## Milestone 0 - Confirm requirements and ownership

### Implement

- Confirm PostgreSQL or company-supported SQL Server.
- Identify the network host and IT owner.
- Decide how users are authenticated.
- Confirm who can submit, include, exclude, restore, and supersede runs.
- Confirm historical import scope.
- Confirm backup, retention, and restore expectations.
- Approve the run classification vocabulary.

### Deliverables

- Approved data dictionary.
- Approved user/permission matrix.
- Approved run-status workflow.
- Test data set containing production, test, partial, and invalid examples.

### Exit criteria

- Stakeholders agree what is included in normal analysis.
- Stakeholders agree what local-only guarantees.
- No code or database deployment is required yet.

## Milestone 1 - Stable IDs and schema metadata

### Implement

- Add stable unit and run identifiers to the domain model.
- Add migration support for older JSON records.
- Preserve existing folder and filename loading.
- Record explicit schema versions.
- Ensure run identity survives continuation and filename changes.
- Record source-file lineage where appropriate.

### Do not change

- CSV column layout.
- COC output.
- Hardware behavior.
- Current operator workflow.

### Tests

- Legacy JSON migration.
- New JSON round-trip.
- Stable run identity after continuation.
- Filename changes without changing run identity.
- Unsupported future schema rejection.

### Exit criteria

- Existing runs load unchanged.
- New runs have stable identities.
- All file-backed tests pass.

## Milestone 2 - Direct central database repository

### Implement

- Add a database repository behind the existing infrastructure boundary.
- Add central schema migrations and foreign-key constraints.
- Add direct queries for units, runs, measurements, replacements, and spares.
- Use parameterized SQL, bounded connections, and short transactions.
- Add stable IDs and idempotent insert/update behavior.
- Keep SQL and connection handling out of the UI and hardware controllers.

### Initial behavior

- CSV/JSON remain the operational source.
- The central database is an optional destination for accepted data.
- Hardware operations do not require a successful database connection.
- File-backed reports remain available while database reporting is introduced.
- The repository can be replaced by an API client later if required.

### Tests

- Submit a complete run.
- Submit a partial run without treating it as complete.
- Ignore transient and overwritten readings.
- Retry an accepted run without creating duplicates.
- Query one unit and all units through the repository.
- Confirm database report totals match file-backed reports.

### Exit criteria

- Multiple workstations can use the same central schema safely.
- Repeating a submission is safe and idempotent.
- Removing database access does not remove local production run files.

## Milestone 3 - Run classification and local submission controls

### Implement

- Add run purpose: Production, Engineering/Test, Training/Demo, or
  Calibration/Equipment Check.
- Add submission policy: Submit when complete, Local only, or Review before
  submitting.
- Add analysis status: Pending review, Included, Excluded, or Superseded.
- Add exclusion reason and notes.
- Add completion status for complete, partial, stopped, and failed runs.
- Add an explicit Submit Run workflow.

### Recommended behavior

- Local-only runs never upload automatically.
- Invalid runs require an exclusion reason.
- Reports exclude pending, excluded, and superseded runs by default.
- A run can later be restored or explicitly submitted.

### Tests

- Test-only run remains local.
- Production run can be submitted explicitly.
- Invalid run is excluded from normal report totals.
- Superseded run is retained but excluded from current-result reports.
- Partial run does not affect complete-run timing metrics.

### Exit criteria

- Operators can perform exploratory work without contaminating production
  analysis.
- No run is silently deleted.
- Status changes are auditable locally.

## Milestone 4 - Direct-write reliability and offline recovery

### Implement

- Save CSV/JSON before attempting database submission.
- Add an asynchronous database worker with bounded connections.
- Add submission status and error details to the run state.
- Retry failed submissions using stable run IDs and source-file hashes.
- Add a manual retry or submit-selected-run operation.
- Add central audit events after successful transactions.
- Keep database writes non-blocking for hardware operations.

### Tests

- Network failure leaves local data intact.
- Retry eventually succeeds.
- Duplicate retry does not duplicate data.
- Local-only runs are never submitted.
- A run remains usable while database submission is pending.
- A successful database write followed by a local status failure is safe to
  retry.

### Exit criteria

- A disconnected workstation can complete a full test.
- Pending submissions are visible and recoverable from local files.
- No hardware operation waits on the database.

## Milestone 5 - Central database pilot

### Implement

- Implement central schema migrations.
- Configure approved direct database authentication.
- Restrict database network access to approved workstations or segments.
- Implement direct run and measurement transactions.
- Validate payload schema and application compatibility.
- Add central duplicate and conflict detection.
- Add audit records for submission and status changes.

An API is not required for this milestone. If direct database access is later
rejected by IT or security, the repository contract should be retained and an
API-backed repository can replace the direct implementation.

### Pilot scope

- One or two test workstations.
- Non-critical test data first.
- Central backup and restore verification before production use.

### Tests

- Authenticated direct submission.
- Invalid payload rejection.
- Duplicate upload handling.
- Concurrent update conflict detection.
- Server unavailable behavior.
- Backup restore into a test database.

### Exit criteria

- Pilot workstations submit data without changing their local workflow.
- Central records match local accepted measurements.
- Conflicts are visible and resolvable.

## Milestone 6 - Historical data import

### Implement

- Scan existing `Unit-*` folders through the repository boundary.
- Import legacy layouts supported by current loaders.
- Preserve source paths and hashes.
- Mark uncertain or incomplete records for review.
- Produce an import report with counts and errors.

### Import rules

- Import accepted/written measurements only.
- Do not infer missing metadata silently.
- Do not treat replacement recommendations as permanent replacement records.
- Do not mark uncertain historical runs as production-included automatically.

### Exit criteria

- Import can be repeated without duplicates.
- Every imported run is traceable to its source file.
- Uncertain records are separated from normal production reports.

## Milestone 7 - Database reporting service

### Implement

- Add report query interfaces independent of the database vendor.
- Add filters for unit, run, switch, band, operator, date, and status.
- Add timing, limit, completion, replacement, and trend summaries.
- Keep normal reports limited to eligible production data.
- Add advanced views for excluded, test, partial, and superseded data.
- Support CSV export of report results.

### Exit criteria

- Reports can compare hundreds or thousands of runs efficiently.
- Complete and incomplete runs are clearly distinguished.
- Excluded data cannot enter normal metrics accidentally.

## Milestone 8 - Reporting GUI

### Implement

Choose either a read-only area under `Tools` or a separate Light Workbench
Reports application. The first version should provide:

- Search and filtering.
- Unit history.
- Run detail.
- Production-only summary dashboard.
- Operator timing summary.
- Over-limit channel summary.
- Synchronization and pending-review status.
- Export.

Editing production measurements should not be part of the first GUI. Status
correction should require explicit permissions and an audit trail.

### Exit criteria

- Users can answer the initial analysis questions without opening individual
  run folders.
- The GUI remains usable when the central service is temporarily unavailable,
  where local cached data is available.

## Milestone 9 - Production hardening

### Implement

- Scheduled backup verification.
- Restore drills.
- API and database health checks.
- Permission review.
- Conflict-resolution procedures.
- Retention and archival procedures.
- Deployment and upgrade documentation.
- User training for run classification and submission.
- Monitoring for synchronization failures.

### Exit criteria

- The organization can recover from workstation, API, and database failure.
- A new workstation can be configured from documented instructions.
- Users understand local-only, pending, included, excluded, and superseded
  runs.

## Proposed source placement

When implementation begins, use the existing project boundaries:

```text
domain/                    Run classification and reporting rules
application/               Submission and synchronization orchestration
infrastructure/            Database repository, file import, SQL, repositories
config/                    Database and service configuration defaults
ui/                        Status, submission, review, and reporting screens
tests/                     Hardware-free repository and workflow tests
docs/                      Architecture, operations, and migration guidance
```

The central database remains outside the desktop executable. Direct database
access belongs in an infrastructure repository with configuration and secret
handling kept separate from hardware and UI code. An API can be added later
behind the same repository contract if required.

## Testing strategy

Every milestone should include:

- Unit tests for domain rules.
- Repository tests with temporary directories and a disposable test database
  or database test container.
- Migration tests using representative old records.
- Synchronization tests using a fake API.
- Failure and retry tests.
- Qt tests only for visible workflow behavior.
- No connected hardware requirement.

Before implementation is considered complete, run the project checks from
`docs/TESTING_AND_RELEASE.md`, including the hardware-free unittest suite,
Python compilation, and `git diff --check`.

## Release and rollout strategy

1. Release local classification fields first.
2. Pilot direct database submission with non-critical data.
3. Verify direct-write retry and offline recovery.
4. Verify backup and restore.
5. Import historical data in a separate controlled operation.
6. Enable reporting for a small user group.
7. Expand to all workstations after reconciliation checks pass.

The existing executable should continue to function at every step. Database
features should be optional until the central service and operating procedures
are proven.

## Success criteria

The architecture is successful when:

- Operators can test hardware while offline.
- Existing CSV/JSON data remains intact and usable.
- Test-only work does not contaminate production reports.
- Invalid and superseded runs remain traceable but excluded by default.
- Multiple computers can synchronize without duplicate or silent data loss.
- Reports use accepted/written readings only.
- The central system can be backed up and restored.
- Future hardware configurations can reuse the same run and measurement model.
