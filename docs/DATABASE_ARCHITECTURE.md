# Database Architecture

## Status and purpose

Status: approved design proposal; implementation is not yet started.

This document defines how Light Workbench can retain its current CSV/JSON
workflow while optionally submitting accepted switch-test data to a central
database for multi-run and multi-computer analysis.

The design is intentionally incremental. The desktop application must remain
usable with no database, no network connection, and no change to the existing
operator workflow while database capabilities are introduced.

## Design goals

- Preserve the current local CSV and JSON files.
- Store only accepted/written switch-test measurements as analytical data.
- Keep live readings, temporary readings, and overwritten retests out of the
  analytical data set.
- Support engineering and test runs that must remain local only.
- Support invalid or skewed runs without deleting historical evidence.
- Allow multiple computers to contribute data safely.
- Keep local hardware testing independent of temporary database availability.
- Support future OPM, separate laser, and alternate switch implementations.
- Provide a stable foundation for a future reporting GUI.
- Keep file formats and compatibility facades working during migration.

## Non-goals

The first database implementation should not:

- Replace CSV or JSON files.
- Store every transient meter reading.
- Change hardware timing or measurement behavior.
- Make a hardware run wait for a network response.
- Add SQLite as a runtime or synchronization dependency.
- Make replacement recommendations permanent authoritative data.
- Turn the existing COC workbook into a database format.

## Recommended deployment model

```text
Light Workbench
    |
    | Always writes local run files
    v
CSV + JSON files
    |
    | Direct authenticated database repository
    |
    v
Central PostgreSQL or SQL Server database
    |
    v
Reporting and analysis tools
```

The local files remain the durable workstation record and recovery path. The
central database is the shared analytical store. There is no local SQLite
database and no shared SQLite file.

The desktop application should access the central database through an
application-owned database repository. Database connection details and
credentials must be supplied through managed configuration, Windows
authentication, or another approved secret-management mechanism.

The repository boundary keeps SQL and database-specific behavior out of the
UI, hardware controllers, and domain rules. If security or IT requirements
later call for an API, the repository can be replaced with an API client
without changing those layers.

## Why direct central database access?

This design removes a second local persistence system and avoids a shared
SQLite file entirely. All submitted workstations write to the same central
database schema, so reporting does not need to merge multiple local indexes.

Direct access is acceptable only when the database is reachable through an
approved protected network and the database server can safely support the
expected number of connections. The application must still:

- Use connection pooling or bounded connections.
- Use short transactions.
- Use parameterized SQL.
- Validate payloads before writing.
- Use stable IDs and idempotent upserts.
- Handle connection loss without losing local files.

PostgreSQL or SQL Server is appropriate for:

- Concurrent writers from multiple workstations.
- Central reporting.
- Transactions and constraints.
- Backup and restore operations.
- Server-side access control.

If company IT already supports SQL Server, it is a valid equivalent to
PostgreSQL. The application should depend on the repository contract, not on a
specific database vendor.

## Current data ownership

The database must preserve the ownership rules already defined in
`docs/DATA_ARCHITECTURE.md`.

### Unit-level data

Unit data describes the physical device and remains valid across runs:

- Main board serial.
- Part number.
- Completed replacement records.
- Designated spare channels.

The database should use an internal stable `unit_id` rather than using the
main board serial as the primary key. A serial correction must not create an
untraceable new unit.

### Run-level data

Run data describes one switch test:

- Run number.
- Switch serial.
- Operating band.
- Tested-by initials.
- Start, stop, and accumulated switch-test timing.
- Accepted/written channel measurements.
- Run-specific metadata.

The switch serial is run-specific because a switch can be replaced while the
unit remains the same.

### Derived or transient data

These are not authoritative permanent results:

- Live IL readings that were not written.
- Temporary current readings.
- Retest attempts overwritten by a later accepted reading.
- Replacement recommendations.
- Current reference offsets.
- GUI filters and dialog state.
- Clipboard contents.

Replacement analysis should continue to be calculated from current readings.
Manual replacement records and designated spares remain persistent unit data.

## Stable identity and lineage

The database design requires stable identifiers:

- `unit_id`: permanent internal identity for a device.
- `run_id`: permanent internal identity for one run.
- `measurement_id`: identity for an accepted measurement record.
- `replacement_id`: identity for a replacement record.

Human-readable values remain available for searching and display:

- Main board serial.
- Run number.
- Switch serial.
- Folder name.
- Source CSV and JSON paths.

The existing run naming convention, such as `Run-7-switchserial`, remains a
user-facing path convention, not the database identity. A future migration
should add `run_id` to JSON while preserving older files through migration
helpers.

Each synchronized record should retain source lineage where available:

- Original local file path.
- Source file hash.
- Application version.
- Import or synchronization time.
- Submitting workstation identity.

Report metadata such as workstation and synchronization time must remain
separate from COC production metadata. They must not be written into the COC
unless explicitly required by a later approved change.

## Logical data model

### `units`

One record per physical unit.

| Field | Description |
| --- | --- |
| `unit_id` | Internal UUID primary key |
| `main_board_serial` | Current main board serial |
| `part_number` | Current part number |
| `created_at` | Creation timestamp |
| `updated_at` | Last modification timestamp |
| `active` | Whether the unit is active |
| `schema_version` | Record format version |

### `runs`

One record per switch-test run.

| Field | Description |
| --- | --- |
| `run_id` | Internal UUID primary key |
| `unit_id` | Associated unit |
| `run_number` | Operator-facing run number |
| `switch_serial` | Switch used in this run |
| `operating_band` | O band or C band |
| `tested_by` | Operator initials |
| `start_time` | First switch-test start |
| `stop_time` | Final switch-test stop |
| `total_duration_seconds` | Accumulated switch-test duration |
| `completion_status` | Complete, partial, stopped, or failed |
| `run_purpose` | Production, engineering, training, or calibration |
| `submission_policy` | Submit, local-only, or review-before-submit |
| `submission_status` | Not submitted, pending, synced, or failed |
| `analysis_status` | Pending, included, excluded, or superseded |
| `analysis_exclusion_reason` | Required when excluded or superseded |
| `superseded_by_run_id` | Preferred replacement run, if any |
| `source_csv_path` | Original CSV path, when known |
| `source_json_path` | Original JSON path, when known |
| `source_file_hash` | Detects source changes |
| `app_version` | Version that produced the run |
| `created_at` | Database creation time |
| `updated_at` | Last database update time |

### `measurements`

One record per accepted/written channel result.

| Field | Description |
| --- | --- |
| `measurement_id` | Internal UUID primary key |
| `run_id` | Associated run |
| `logical_channel` | Channel shown to the operator |
| `physical_port` | Physical port, when available |
| `loss_1310_db` | Accepted 1310 nm loss |
| `loss_1550_db` | Accepted 1550 nm loss |
| `written_at` | Time accepted into the run |
| `sequence_number` | Order accepted during the run |

The normal current-result view should enforce one active accepted result per
logical channel in a run. If future requirements need full revision history,
old values can be retained in a separate measurement-revisions table without
changing the current-result view.

### `replacement_records`

Unit-level replacement history:

| Field | Description |
| --- | --- |
| `replacement_id` | Internal UUID primary key |
| `unit_id` | Associated unit |
| `current_channel` | Channel being replaced |
| `replacement_channel` | Channel installed in its place |
| `recorded_at` | Time recorded |
| `recorded_by` | Operator, when available |
| `notes` | Optional explanation |

### `designated_spares`

Unit-level spare designations:

| Field | Description |
| --- | --- |
| `unit_id` | Associated unit |
| `channel` | Designated spare channel |
| `designated_at` | Time designated |
| `designated_by` | Operator, when available |

### `database_sync_events`

The central database should retain an audit trail for direct submissions and
status changes. This is not a local SQLite outbox. It records what the central
database accepted after a transaction completes.

| Field | Description |
| --- | --- |
| `event_id` | Central event identifier |
| `entity_type` | Unit, run, measurement, replacement, or spare |
| `entity_id` | Entity written |
| `operation` | Insert, update, submit, exclude, or restore |
| `source_file_hash` | Local source version, when available |
| `submitted_by` | User or workstation identity |
| `submitted_at` | Central acceptance time |

### `database_conflicts`

Conflicts must be recorded rather than silently overwritten. Examples include
two workstations submitting different values for the same run/channel or
simultaneously changing unit-level replacements.

The conflict record should retain both versions, the submitting identities,
timestamps, and the resolution decision.

### Schema migrations

The central database needs explicit schema migration versions. A migration
must:

- Be forward-only and repeatable.
- Validate the starting schema version.
- Preserve existing data.
- Have a rollback or recovery plan where practical.
- Be covered by hardware-free tests.

The application must reject an unsupported future database schema rather than
silently dropping fields.

## Run classification and analysis eligibility

This is a central part of the design.

### Run purpose

Every run should eventually have one of these purposes:

- `Production` - intended for normal quality and performance analysis.
- `Engineering/Test` - exploratory or troubleshooting work.
- `Training/Demo` - operator training or demonstrations.
- `Calibration/Equipment Check` - validation of hardware or fixtures.

### Submission policy

- `Submit when complete` - eligible for explicit submission after testing.
- `Local only` - never uploads measurement data automatically.
- `Review before submitting` - waits for explicit approval.

### Analysis status

- `Pending review` - not included until approved.
- `Included` - eligible for normal reports.
- `Excluded` - retained but omitted from normal reports.
- `Superseded` - replaced by a preferred later run.

The status must not be inferred from a note, filename, or operator initials.

### Test-only run

For a switch used only for testing, the operator selects `Engineering/Test` and
`Local only`. The application still saves CSV and JSON normally, but does not
submit measurement data to the central database.

The run remains available locally for troubleshooting and may later be
submitted explicitly if it is determined to be useful.

### Skewed or invalid run

If a run has bad readings, incorrect channel selection, a connection problem,
or another known issue, it should be marked `Excluded` with a required reason.
The data is retained, but normal reports ignore it.

### Multiple attempts

If five attempts are made, all five runs remain identifiable. The valid final
run can be marked `Included`; earlier attempts can be marked `Excluded` or
`Superseded`.

This prevents invalid runs from affecting averages without destroying the
history needed to investigate what happened.

### Partial runs

A stopped or incomplete run should be `Pending review` or `Excluded` by
default. It should not be included in completion-time or quality statistics
unless a report explicitly requests partial runs.

### Restoring a run

An excluded or local-only run may be submitted later through an explicit
operator action. The system should record who changed the status and when.

## Local persistence and direct database-write behavior

The normal local workflow remains:

1. The operator writes an accepted measurement.
2. Existing CSV/JSON persistence saves it locally.
3. A database repository writes the accepted data to the central database in a
   short transaction.
4. The test continues without waiting for a second local database.
5. A background database worker may retry a failed write from the local run
   files.

No database call should be required for hardware communication, measurement,
or local persistence. Database submission must happen after local persistence,
so a database failure cannot remove the local record.

If the network is unavailable:

- CSV and JSON continue to work.
- The run is marked pending database submission.
- The application can retry by scanning local run files using stable IDs and
  source hashes.
- The user can request a manual retry or submit a selected run later.
- Errors remain visible for diagnosis.

Direct database writes must be idempotent. Retrying the same run or
measurement must not create duplicate records. The central database should use
unique constraints and transactionally safe upserts.

### Recovery without a local database

The local JSON file and its source hash act as the recovery record. The run
should retain a small database-submission state such as `not_submitted`,
`pending`, `submitted`, or `failed`, along with the last error when applicable.

If a direct write fails, a later retry should:

1. Load the run through the existing file repository.
2. Use the stable `run_id` and measurement identities.
3. Compare the source hash or submitted version with the central record.
4. Insert or update only the missing/current records.
5. Mark the local run submitted after the central transaction succeeds.

If the application closes after the central transaction succeeds but before the
local status is updated, repeating the same operation must be safe because the
central unique keys and idempotent upserts identify the existing data.

An accepted two-wavelength measurement must be submitted as one database
transaction. A database failure must not create a 1310 nm-only analytical
measurement.

## Central database repository boundary

The desktop application should use a repository such as:

```text
CentralDatabaseRepository.submit_run(run)
CentralDatabaseRepository.submit_measurement(measurement)
CentralDatabaseRepository.update_run_status(run_id, status)
CentralDatabaseRepository.get_unit(unit_id)
CentralDatabaseRepository.query_runs(filters)
CentralDatabaseRepository.query_reports(filters)
```

The repository owns:

- Connection setup and approved authentication.
- Payload validation.
- Duplicate detection.
- Conflict detection.
- Schema compatibility.
- Transaction boundaries and audit records.
- Reporting queries.

The repository must not expose SQL or database credentials to the UI, hardware
controllers, or domain services.

An API remains a possible future security boundary, but it is not required for
the initial direct-database proposal.

## Reporting requirements

Normal reports should include only runs that are:

- Submitted to the central system.
- Marked `Included`.
- Production runs, unless a different filter is selected.
- Complete when the report requires complete runs.
- Based on accepted/written measurements.

Separate advanced views may include test, excluded, partial, and superseded
runs for troubleshooting.

Future reporting screens should support:

- Date range.
- Main board serial.
- Part number.
- Run number.
- Switch serial.
- Operating band.
- Tested by.
- Completion status.
- Submission and analysis status.

Useful reports include:

- Average, median, fastest, and slowest test duration.
- Duration normalized by tested-channel count.
- Timing by operator.
- Average channels over 2.0 dB or 2.5 dB.
- Channel-specific failure frequency.
- Unit history across runs.
- Switch-to-switch comparison.
- Before-and-after replacement comparison.
- Runs pending review or database submission.

Reports should distinguish active switch-test time from elapsed calendar time.
Incomplete and invalid runs should not silently enter production averages.

## Security, backup, and operations

Production deployment should provide:

- Encrypted database connections where supported.
- Windows/domain authentication where available.
- Role-based permissions.
- No database secrets embedded in the executable.
- Credentials stored in managed Windows credential storage or configuration.
- Server-side validation and audit logging.
- Scheduled database backups.
- Periodic restore testing.
- A documented retention policy.
- Health checks for the database connection and server.
- An administrator workflow for conflict resolution.

Database reports should be read-only initially. Editing production measurements
should require a separate correction workflow with an audit trail.

## Compatibility rules

- Existing CSV and JSON files remain loadable.
- Existing folder and filename conventions remain supported.
- Existing root-level compatibility facades remain available.
- COC output remains independent of database reporting metadata.
- Clipboard output remains transient.
- Database synchronization never changes the measurement calculation.
- Database failure never prevents a local hardware run from completing.

## Open decisions before implementation

1. PostgreSQL or an existing SQL Server installation.
2. Server host and IT ownership.
3. Windows/domain authentication versus application accounts.
4. Whether local-only runs may later be manually submitted.
5. Who may include, exclude, restore, or supersede a run.
6. Historical import scope and handling of incomplete legacy metadata.
7. Data-retention and backup requirements.
8. Whether the first reporting screen belongs in Light Workbench or in a
   separate Light Workbench Reports application.

## Related documents

- `docs/DATA_ARCHITECTURE.md` - current unit/run ownership and file formats.
- `docs/DATABASE_ROADMAP.md` - implementation milestones and exit criteria.
- `docs/REFACTOR_ROADMAP.md` - broader application refactor history.
- `docs/PROJECT_LAYOUT.md` - placement of future repository and service code.
