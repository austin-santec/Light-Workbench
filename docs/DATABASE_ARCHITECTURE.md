# Database Architecture

## Status and purpose

Status: approved design with the Milestone 1 schema implemented as forward-only
migration `0001_initial_schema.sql`. Application repositories and runtime
cutover are not yet implemented.

This document defines the SQL Server schema and persistence boundaries for the
future database-backed version of Light Workbench. The database will start
clean and will store future runs only. Existing CSV and JSON runs are mostly
development/test data and are not scheduled for bulk import.

The current file-backed release remains the compatibility baseline until the
database milestones in `docs/DATABASE_ROADMAP.md` are complete. On the
database branch, SQL Server will eventually become authoritative for new run
data. Always-on engineering support logs remain local.

## Approved deployment direction

- Database engine: Microsoft SQL Server.
- Development instance: `localhost\SQLExpress`.
- Development database: `LWBTestDB`.
- Authentication: Windows Authentication.
- Production direction: the same versioned schema on a managed network SQL
  Server using Windows/domain groups and encrypted connections.
- No SQLite database, shared database file, local synchronization database, or
  historical bulk-import milestone is planned.

Database connection details belong in configuration and must not be embedded
in source code or the executable. Because the supported Light Workbench
runtime is 32-bit Python, the selected SQL Server ODBC driver and Python
database adapter must support that runtime.

Runtime endpoint settings are kept in the per-user non-secret file
`%LOCALAPPDATA%\LightWorkbench\config\database.ini`. Light Workbench uses the
signed-in Windows identity and does not store SQL usernames or passwords. The
configuration includes bounded connection and command timeouts. Connections
and cursors are short-lived and closed deterministically; write operations use
explicit commit/rollback transaction scopes.

The application performs a read-only schema preflight before database-backed
workflows. It reports unavailable servers, authentication failures, missing
databases, timeouts, insufficient permissions, and incompatible migration
history as distinct categories. The preflight never applies migrations.
Technical details recorded in local support logs exclude credentials and full
connection strings.

The migration tool uses `pyodbc`, Windows Authentication, and an explicitly
provided server/database target. Local integration testing uses
`LWBTestDB_Integration`; migrations must never be tested against development or
production data.

The guarded reset and backup/restore verification tools accept only
`LWBTestDB_Integration`. Backup verification restores to
`LWBTestDB_RestoreVerification`, runs `DBCC CHECKDB`, validates migration and
schema counts, and removes the temporary database and backup unless retention
is explicitly requested.

## Design goals

- Store future accepted switch-test data in one authoritative SQL Server
  schema.
- Preserve the unit, installed switch, run, accepted measurement, retest,
  replacement, and designated-spare relationships.
- Keep the two insertion-loss values in ordinary relational columns for
  efficient reporting.
- Use JSON only for bounded historical context that is not queried heavily:
  hardware identity, limit criteria, references, and baseline channel maps.
- Preserve every accepted retest attempt while exposing a simple current-value
  view.
- Keep production, engineering, training, and calibration runs distinguishable
  so non-production data cannot silently enter normal analysis.
- Keep UI, hardware communication, domain rules, and SQL access separated by
  repository boundaries.
- Keep local support logs outside the analytical database.

## Non-goals

The first database implementation will not:

- Import existing `ILM-Reads` folders in bulk.
- Store temporary, live, invalid, or unwritten meter samples.
- Store raw measured power in the analytical database.
- Store COC workbooks, diagnostic exports, or support-log JSONL records.
- Add an offline synchronization queue or local SQLite outbox.
- Infer or command switch replacement mappings.
- Store a pass/fail result that can become stale when reporting rules change.
- Replace the existing application before the database implementation is
  verified.

## Ownership model

```text
UNITS
  |
  | one unit may receive different switches over time
  v
UNIT_SWITCH_ASSIGNMENTS <----- SWITCHES
  |
  +---- IL_RUNS
  |       |
  |       +---- IL_MEASUREMENTS
  |
  +---- CHANNEL_REPLACEMENTS
  |
  +---- DESIGNATED_SPARES
```

`UNITS` represents the product under test and its main board. It does not
represent the ILM, OPM, or laser used to perform a measurement. Test-equipment
identity is captured as a historical JSON snapshot on each run.

The assignment table is required because a unit may receive a replacement
switch while the unit remains the same. Runs continue to identify the exact
unit/switch installation that produced their data.

## SQL Server conventions

- Business primary keys use `BIGINT IDENTITY(1,1)`.
- Application-generated retry identities use `UNIQUEIDENTIFIER` with unique
  constraints.
- Timestamps use UTC `DATETIME2(3)` values.
- Insertion loss uses `DECIMAL(9,4)`.
- Controlled vocabularies use short `VARCHAR` fields and `CHECK` constraints.
- Human-entered text uses `NVARCHAR`.
- JSON fields use `NVARCHAR(MAX)` with `ISJSON` checks.
- Foreign keys do not cascade deletes.
- Accepted attempts, replacements, and spare events are append-only for the
  application role.
- `SYSUTCDATETIME()` is the normal database timestamp default.

Fields are required unless explicitly marked nullable below.

## Logical schema

### `UNITS`

One record per product/main-board unit.

| Field | SQL Server type | Description |
| --- | --- | --- |
| `unit_id` | `BIGINT IDENTITY(1,1)` | Primary key |
| `main_board_serial` | `NVARCHAR(100)` | Unique main-board serial |
| `part_number` | `NVARCHAR(100) NULL` | Current part number |
| `front_panel_channel_count` | `INT NULL` | Current count parsed from the part number |
| `unit_model` | `NVARCHAR(50) NULL` | Product model or family |
| `notes` | `NVARCHAR(MAX) NULL` | Unit-level notes |
| `created_at_utc` | `DATETIME2(3)` | Creation time |
| `updated_at_utc` | `DATETIME2(3)` | Last update time |

Rules:

- `main_board_serial` is unique.
- `front_panel_channel_count`, when present, is greater than zero.
- Part number and channel count remain nullable so an explicitly authorized
  administrative exception can still be represented; normal production
  preflight is responsible for requiring them.

### `SWITCHES`

One record per physical optical switch.

| Field | SQL Server type | Description |
| --- | --- | --- |
| `switch_id` | `BIGINT IDENTITY(1,1)` | Primary key |
| `switch_serial` | `NVARCHAR(100)` | Unique switch serial |
| `switch_model` | `NVARCHAR(30)` | OSX-100, OSX-150, or another supported model |
| `firmware_version` | `NVARCHAR(50) NULL` | Detected switch firmware |
| `physical_channel_count` | `INT` | Physical switch capacity |
| `notes` | `NVARCHAR(MAX) NULL` | Switch notes |
| `created_at_utc` | `DATETIME2(3)` | Creation time |
| `updated_at_utc` | `DATETIME2(3)` | Last update time |

Rules:

- `switch_serial` is unique.
- `physical_channel_count` is greater than zero.
- The logical channel map does not belong here because it applies to a
  particular installation, not permanently to the switch.

### `UNIT_SWITCH_ASSIGNMENTS`

One record per period in which a switch is installed in a unit.

| Field | SQL Server type | Description |
| --- | --- | --- |
| `assignment_id` | `BIGINT IDENTITY(1,1)` | Primary key |
| `unit_id` | `BIGINT` | Foreign key to `UNITS` |
| `switch_id` | `BIGINT` | Foreign key to `SWITCHES` |
| `installed_at_utc` | `DATETIME2(3)` | Installation time |
| `removed_at_utc` | `DATETIME2(3) NULL` | Removal time; null while active |
| `installed_by` | `NVARCHAR(100)` | Person recording installation |
| `removed_by` | `NVARCHAR(100) NULL` | Person recording removal |
| `removal_reason` | `NVARCHAR(500) NULL` | Reason the assignment ended |
| `initial_channel_map_json` | `NVARCHAR(MAX)` | Baseline logical-to-physical map |
| `notes` | `NVARCHAR(MAX) NULL` | Assignment notes |
| `created_at_utc` | `DATETIME2(3)` | Creation time |
| `updated_at_utc` | `DATETIME2(3)` | Last update time |

Example baseline map:

```json
{
  "1": 1,
  "2": 2,
  "3": 3,
  "4": 4
}
```

Rules:

- `initial_channel_map_json` contains valid JSON.
- Removal cannot precede installation.
- Filtered unique indexes allow at most one active assignment per unit and at
  most one active assignment per switch where `removed_at_utc IS NULL`.

### `IL_RUNS`

One record per Light Workbench test run.

| Field | SQL Server type | Description |
| --- | --- | --- |
| `run_id` | `BIGINT IDENTITY(1,1)` | Primary key |
| `assignment_id` | `BIGINT` | Unit/switch assignment tested |
| `run_number` | `INT` | Operator-facing run number |
| `client_run_uuid` | `UNIQUEIDENTIFIER` | Retry-safe application identity |
| `run_started_at_utc` | `DATETIME2(3)` | Run start time |
| `run_ended_at_utc` | `DATETIME2(3) NULL` | Complete, stopped, or failed time |
| `tested_by` | `NVARCHAR(100)` | Operator |
| `wavelength_mode` | `VARCHAR(2)` | `SM` or `MM` |
| `operating_band` | `VARCHAR(20)` | O band or C band |
| `application_version` | `NVARCHAR(30)` | Light Workbench version |
| `completion_status` | `VARCHAR(20)` | Run lifecycle status |
| `run_purpose` | `VARCHAR(30)` | Purpose of the run |
| `analysis_status` | `VARCHAR(20)` | Analysis eligibility |
| `analysis_exclusion_reason` | `NVARCHAR(1000) NULL` | Reason for exclusion |
| `superseded_by_run_id` | `BIGINT NULL` | Preferred replacement run |
| `part_number_snapshot` | `NVARCHAR(100) NULL` | Part number at test time |
| `front_panel_channel_count` | `INT NULL` | Required channels at test time |
| `measurement_hardware_json` | `NVARCHAR(MAX)` | ILM/OPM/laser identity snapshot |
| `limit_snapshot_json` | `NVARCHAR(MAX)` | Exact criteria used |
| `notes` | `NVARCHAR(MAX) NULL` | Run notes |
| `created_at_utc` | `DATETIME2(3)` | Database creation time |
| `updated_at_utc` | `DATETIME2(3)` | Last update time |

`client_run_uuid` is generated before the first insertion attempt and never
changes. Retrying a create operation with the same UUID must resolve the
existing run rather than create a duplicate.

Controlled values:

| Field | Allowed values |
| --- | --- |
| `completion_status` | `in_progress`, `complete`, `stopped`, `failed` |
| `run_purpose` | `production`, `engineering`, `training`, `calibration` |
| `analysis_status` | `pending`, `included`, `excluded`, `superseded` |
| `wavelength_mode` | `SM`, `MM` |

Recommended defaults are `in_progress`, `production`, and `pending`.
`analysis_exclusion_reason` is required when analysis status is `excluded`.

Example hardware snapshot:

```json
{
  "ilm": {
    "model": "OP815",
    "serial": "0016582",
    "firmware": "1.2.3"
  }
}
```

Example limit snapshot:

```json
{
  "too_good_db": 0.5,
  "warning_db": 2.25,
  "failure_db": 2.5
}
```

Completion describes how the workflow ended. It does not describe quality.
Pass/fail and optimization remain derived from current accepted measurements,
the front-panel count, and the immutable limit snapshot.

### `IL_MEASUREMENTS`

One append-only row per accepted Write IL operation, including retests.

| Field | SQL Server type | Description |
| --- | --- | --- |
| `measurement_id` | `BIGINT IDENTITY(1,1)` | Primary key |
| `measurement_uuid` | `UNIQUEIDENTIFIER` | Retry-safe measurement identity |
| `run_id` | `BIGINT` | Foreign key to `IL_RUNS` |
| `logical_channel` | `INT` | Operator-facing channel |
| `physical_port` | `INT NULL` | Physical port when known |
| `attempt_number` | `INT` | Accepted attempt number |
| `wavelength_1_nm` | `SMALLINT` | First wavelength |
| `wavelength_1_il_db` | `DECIMAL(9,4)` | First insertion-loss value |
| `wavelength_2_nm` | `SMALLINT` | Second wavelength |
| `wavelength_2_il_db` | `DECIMAL(9,4)` | Second insertion-loss value |
| `reference_snapshot_json` | `NVARCHAR(MAX)` | Reference used for this attempt |
| `written_at_utc` | `DATETIME2(3)` | Acceptance time |
| `written_by` | `NVARCHAR(100)` | Operator |

Example reference snapshot:

```json
{
  "snapshot_id": "6fe700e0",
  "method": "calculated",
  "calculated_at_utc": "2026-10-09T18:42:15Z",
  "values_dbm": {
    "1310": -0.04,
    "1550": 0.14
  }
}
```

Rules:

- `measurement_uuid` is unique.
- `(run_id, logical_channel, attempt_number)` is unique.
- Channels, ports when present, wavelengths, and attempt numbers are positive.
- `reference_snapshot_json` contains valid JSON.
- Both wavelength results are inserted in one transaction.
- Temporary, live, invalid, and unwritten readings are never inserted.
- Raw measured power remains local engineering evidence, not analytical data.

### `CHANNEL_REPLACEMENTS`

Append-only documentation of manually performed channel replacements.

| Field | SQL Server type | Description |
| --- | --- | --- |
| `replacement_id` | `BIGINT IDENTITY(1,1)` | Primary key |
| `assignment_id` | `BIGINT` | Assignment affected |
| `logical_channel` | `INT` | Logical channel rerouted |
| `previous_physical_port` | `INT` | Previous physical port |
| `replacement_physical_port` | `INT` | New physical port |
| `reason` | `NVARCHAR(500)` | Replacement reason |
| `replaced_by` | `NVARCHAR(100)` | Person recording replacement |
| `replaced_at_utc` | `DATETIME2(3)` | Replacement time |
| `related_run_id` | `BIGINT NULL` | Associated run when applicable |
| `notes` | `NVARCHAR(MAX) NULL` | Additional notes |

All channels and ports are positive, and previous/replacement ports cannot be
equal. A replacement belongs to an assignment rather than permanently to a
unit so records from a removed switch cannot alter a later switch's map.

Light Workbench documents replacements only. It does not command the switch,
use `CLOSe?` to infer a replaced route, or verify the external mapping change.

### `DESIGNATED_SPARES`

Append-only spare designation history.

| Field | SQL Server type | Description |
| --- | --- | --- |
| `spare_event_id` | `BIGINT IDENTITY(1,1)` | Primary key |
| `assignment_id` | `BIGINT` | Associated assignment |
| `physical_port` | `INT` | Spare physical port |
| `action` | `VARCHAR(20)` | `designated` or `undesignated` |
| `recorded_by` | `NVARCHAR(100)` | Person recording action |
| `recorded_at_utc` | `DATETIME2(3)` | Action time |
| `notes` | `NVARCHAR(MAX) NULL` | Explanation |

The active spare set is derived from the newest event for each assignment and
physical port.

### `SCHEMA_MIGRATIONS`

Tracks forward-only SQL schema changes.

| Field | SQL Server type | Description |
| --- | --- | --- |
| `migration_id` | `INT` | Primary key and migration order |
| `migration_name` | `NVARCHAR(200)` | Human-readable name |
| `script_checksum` | `CHAR(64)` | SHA-256 script checksum |
| `applied_at_utc` | `DATETIME2(3)` | Time applied |
| `application_version` | `NVARCHAR(30)` | Associated application version |

The application must reject a schema newer than it supports rather than
silently ignoring fields.

## Read-only views

### `vw_CurrentILMeasurements`

Returns the highest `attempt_number` for each `(run_id, logical_channel)`.
The main readings table, limits, run status, COC preparation, Copy Raw Data,
and replacement recommendations use this view. Reading History and retest
reports query all `IL_MEASUREMENTS` rows.

### `vw_CurrentChannelMap`

Combines `UNIT_SWITCH_ASSIGNMENTS.initial_channel_map_json` with the latest
`CHANNEL_REPLACEMENTS` row for each logical channel. It returns the assignment,
unit, switch, logical channel, effective physical port, replacement state, and
latest replacement timestamp.

## Required indexes

At minimum, create indexes for:

- Unique unit main-board serial.
- Unique switch serial.
- Active assignment by unit and switch.
- Unique run UUID.
- Runs by assignment, date, completion status, purpose, and analysis status.
- Unique measurement UUID.
- Unique measurement attempt by run/channel/attempt number.
- Measurements by run and logical channel.
- Replacements by assignment, logical channel, and time.
- Spare events by assignment, physical port, and time.

Run numbers remain operator-facing. The application allocates them for the
unit inside a transaction; `client_run_uuid` is the authoritative duplicate
prevention key.

## Database-primary runtime behavior

### Starting a run

Before a production run begins, the application must:

1. Confirm database connectivity and supported schema version.
2. Resolve the unit, switch, and active assignment.
3. Validate required setup and reference state.
4. Generate `client_run_uuid`.
5. Insert the `in_progress` run and its historical snapshots.

Red Light Test and Power Measurement Diagnostics do not create production run
records and may remain usable when the database is unavailable.

### Writing a measurement

Write IL must validate and insert the complete two-wavelength attempt in one
short transaction. The application may show the reading as accepted and
advance only after commit succeeds.

If SQL Server becomes unavailable, the reading stays temporary in memory, the
operator receives actionable feedback, and the application offers a retry. It
must not use support logs as an unofficial measurement outbox.

### Application interruption

An unexpected process or workstation failure may leave a run `in_progress`.
On the next connection, Light Workbench should identify stale in-progress runs
and offer an explicit resume or close decision. It must not silently mark them
complete.

## Files that remain local

- Daily support-log JSONL and compressed archives.
- Explicit diagnostic history/trace exports.
- Generated COC workbooks.
- Explicit operator-requested CSV/JSON exports.
- Application configuration, including the database endpoint.

Existing run files may remain viewable during development, but opening one
does not upload it or make it part of the authoritative database.

## Security and operations

- Use Windows Authentication and least-privilege database roles.
- Give normal application users only the operations needed by repositories.
- Do not grant the application role arbitrary delete access to accepted data.
- Encrypt network SQL Server connections in production.
- Back up the database and test restoration before production rollout.
- Use a separate integration-test database so automated tests cannot pollute
  development or production records.
- Keep support logs local and governed by `docs/SUPPORT_LOGGING.md`.

## Capacity planning

For one 48-channel run per switch with modest JSON snapshots and a small retest
rate, plan on roughly 60-100 KB of application data and indexes per tested
switch. Approximate planning ranges are:

| Tested switches | One run per switch | Three runs per switch |
| ---: | ---: | ---: |
| 100 | 6-10 MB | 14-25 MB |
| 1,000 | 60-100 MB | 140-250 MB |
| 10,000 | 600 MB-1 GB | 1.4-2.5 GB |

Actual MDF/LDF allocation can be larger because SQL Server preallocates data
and transaction-log space. Notes, retest frequency, indexes, and JSON size also
affect growth. Capacity should be measured during the pilot rather than treated
as a fixed per-run guarantee.

## Resolved and remaining decisions

Resolved:

- SQL Server is the target engine.
- Development uses `localhost\SQLExpress`, `LWBTestDB`, and Windows
  Authentication.
- The database starts with future data; no historical bulk import is planned.
- SQL Server becomes authoritative for new run data on the database branch.
- Support logs remain local.
- The simplified eight-table schema and two read-only views are the approved
  baseline.

Remaining before production:

1. Network SQL Server host and IT ownership.
2. Windows/domain groups and permissions.
3. Backup, restore, retention, and archival policy.
4. Exact production behavior for stale `in_progress` runs.
5. Whether database reporting lives in Light Workbench or a separate read-only
   application.

## Related documents

- `docs/DATA_ARCHITECTURE.md` - current file-backed behavior and transition
  boundary.
- `docs/DATABASE_ROADMAP.md` - implementation milestones and exit criteria.
- `docs/PROJECT_LAYOUT.md` - repository and source placement.
- `docs/SUPPORT_LOGGING.md` - local engineering-log ownership.
- `docs/TESTING_AND_RELEASE.md` - required validation and release checks.
