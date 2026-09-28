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

## Milestone 2 - Local SQLite index and query repository

### Implement

- Add a local SQLite database under application data, not the source tree.
- Add schema migrations and foreign-key constraints.
- Import existing unit/run JSON and accepted measurements.
- Index unit, run, measurement, replacement, and spare data.
- Add a rebuild/reindex operation.
- Add repository interfaces so reporting does not depend on SQLite details.

### Initial behavior

- CSV/JSON remain the operational source.
- SQLite is a local read index and may be rebuilt.
- Hardware operations do not require SQLite.
- Reports can fall back to file-backed queries if SQLite is unavailable.

### Tests

- Import a complete run.
- Import a partial run.
- Ignore transient and overwritten readings.
- Rebuild the index without duplicates.
- Query one unit and all units.
- Confirm report totals match existing file-backed reports.

### Exit criteria

- Hundreds of runs can be queried without scanning every CSV for each query.
- Reindexing is repeatable and safe.
- Removing the local database does not remove production run files.

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

## Milestone 4 - Local synchronization outbox

### Implement

- Add an outbox transaction after local run persistence.
- Queue only records eligible for synchronization.
- Add retry count, error details, and synchronization status.
- Add idempotency keys.
- Add manual retry and diagnostic status.
- Keep synchronization asynchronous and non-blocking.

### Tests

- Network failure leaves local data intact.
- Retry eventually succeeds.
- Duplicate retry does not duplicate data.
- Local-only runs do not enter the upload queue.
- A run remains usable while synchronization is pending.

### Exit criteria

- A disconnected workstation can complete a full test.
- Pending data is visible and recoverable.
- No hardware operation waits on the database.

## Milestone 5 - Central API and database pilot

### Implement

- Create the internal API service.
- Implement central schema migrations.
- Add authentication and authorization.
- Implement batch synchronization.
- Validate payload schema and application compatibility.
- Add central duplicate and conflict detection.
- Add audit records for submission and status changes.

### Pilot scope

- One or two test workstations.
- Non-critical test data first.
- Central backup and restore verification before production use.

### Tests

- Authenticated submission.
- Invalid payload rejection.
- Duplicate upload handling.
- Concurrent update conflict detection.
- Server unavailable behavior.
- Backup restore into a test database.

### Exit criteria

- Pilot workstations synchronize without changing their local workflow.
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
infrastructure/            SQLite, file import, API client, repositories
config/                    Database and service configuration defaults
ui/                        Status, submission, review, and reporting screens
tests/                     Hardware-free repository and workflow tests
docs/                      Architecture, operations, and migration guidance
```

The central API should be a separately deployable service rather than a
hardware or UI module inside the desktop executable.

## Testing strategy

Every milestone should include:

- Unit tests for domain rules.
- Repository tests with temporary directories or temporary SQLite databases.
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
2. Pilot SQLite indexing without central submission.
3. Pilot synchronization with non-critical data.
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
