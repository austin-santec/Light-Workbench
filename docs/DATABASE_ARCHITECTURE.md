# Database Architecture

## Status and purpose

Status: implemented through assignment-scoped iterative replacement analysis,
permanent run voiding, persistent analysis history, and read-only database
reporting. The current schema includes forward-only migrations through
`0006_authoritative_channel_roles.sql`.

Migration `0006` reclassifies only legacy measurements that are unambiguously
extra candidates: both their stored logical channel and physical port exceed
the run's front-panel channel count. Ambiguous development/test rows remain
logical-channel measurements rather than having a role fabricated during
migration.
Database-neutral repositories and the unit, assignment, run-lifecycle,
atomic-measurement, current/history query, and assignment-scoped routing
boundaries are connected to the production hardware workflow.

This document defines the implemented SQL Server schema and persistence
boundaries for the database-primary Light Workbench branch. The database was
introduced as a clean start and stores newly created runs only. Existing CSV
and JSON runs are mostly development/test or legacy data and are not scheduled
for bulk import.

On this database branch, SQL Server is authoritative for new run data. Existing
CSV/JSON files remain viewable as legacy data and are not uploaded.
Always-on engineering support logs remain local.

## Approved deployment direction

- Database engine: Microsoft SQL Server.
- Development instance: `localhost\SQLExpress`.
- Development database: `LWBTestDB`.
- Authentication: Windows Authentication by default, with explicit SQL Server
  Authentication support for workgroup deployments.
- Temporary workgroup pilot: SQL Server Mixed Mode with a dedicated least-
  privilege `lwb_app` SQL login and encrypted ODBC connections.
- Production direction: the same versioned schema on a managed network SQL
  Server using the approved authentication method and encrypted connections.
- No SQLite database, shared database file, local synchronization database, or
  historical bulk-import milestone is planned.

Database connection details belong in configuration and must not be embedded
in source code or the executable. Because the supported Light Workbench
runtime is 32-bit Python, the selected SQL Server ODBC driver and Python
database adapter must support that runtime.

Runtime endpoint and authentication settings are kept in the per-user file
`%LOCALAPPDATA%\LightWorkbench\config\database.ini`. On first database
initialization, Light Workbench creates this file with the local development
defaults if it is missing. Creation is create-only; an existing file is never
replaced by startup, an upgrade, or a rebuild. A malformed or invalid existing
file blocks database use and reports the path and validation problem rather
than silently falling back to hidden defaults. A tracked, credential-free
example is available at `config/database.ini.example`.

The default authentication mode is Windows Authentication and uses the signed-
in Windows identity. Workgroup deployments may explicitly select
`authentication = sql_password` and provide a SQL login and plaintext password
in the per-user INI. The password is never stored in source control, support
bundles, logs, error details, or connection diagnostics. The configuration
includes bounded connection and command timeouts. Connections
and cursors are short-lived and closed deterministically; write operations use
explicit commit/rollback transaction scopes.

The application performs a read-only schema preflight before database-backed
workflows. It reports unavailable servers, authentication failures, missing
databases, timeouts, insufficient permissions, and incompatible migration
history as distinct categories. The preflight never applies migrations.
Technical details recorded in local support logs exclude credentials and full
connection strings.

Application workflows depend on protocols in
`application/database_repositories.py`. Typed request and result records live
in `domain/database_records.py`. The in-memory contract implementation and the
SQL Server implementation live under `infrastructure/database/`; SQL text and
driver-specific rows do not cross that boundary. Both implementations follow
the same idempotency and current/history semantics before UI integration.

The migration tool uses `pyodbc`, Windows Authentication, and an explicitly
provided server/database target. It remains administrator-only and does not
use the shared runtime SQL login. Local integration testing uses
`LWBTestDB_Integration`; migrations must never be tested against development or
production data.

The guarded reset and backup/restore verification tools accept only
`LWBTestDB_Integration`. Backup verification restores to
`LWBTestDB_RestoreVerification`, runs `DBCC CHECKDB`, validates migration and
schema counts, and removes the temporary database and backup unless retention
is explicitly requested.

## Design goals

- Store newly accepted switch-test data in one authoritative SQL Server
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
  so production-only reporting remains intentional without conflating purpose
  with technical validity or run voiding.
- Keep UI, hardware communication, domain rules, and SQL access separated by
  repository boundaries.
- Keep local support logs outside the analytical database.

## Non-goals

The database-primary design does not:

- Import existing `ILM-Reads` folders in bulk.
- Store temporary, live, invalid, or unwritten meter samples.
- Store raw measured power in the analytical database.
- Store COC workbooks, diagnostic exports, or support-log JSONL records.
- Add an offline synchronization queue or local SQLite outbox.
- Infer or command switch replacement mappings.
- Store a mutable run pass/fail flag as measurement truth. Run/result displays
  are derived from accepted measurements and immutable snapshots; saved
  replacement-analysis classifications remain historical snapshots.

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
  |       +---- REPLACEMENT_ANALYSES
  |               |
  |               +---- REPLACEMENT_ANALYSIS_RECOMMENDATIONS
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

Assignment resolution is automatic for the normal same-pairing case and uses
one confirmation for a genuinely new hardware pairing. Reconnecting the same
unit and switch reuses their active assignment. If a switch is moved to a
different main board, a main board receives a different switch, or both sides
have conflicting active assignments, Light Workbench closes the affected active
assignments, marks their unfinished runs `stopped`, and creates one new
assignment. The operation is atomic with creation of the first run, so a
canceled confirmation or failed transaction leaves the prior assignments
unchanged. The operator does not enter a transfer reason.

Every new main-board/switch pairing starts from a fresh identity baseline:
logical channel 1 maps to physical port 1 through the unit's front-panel
count. The application does not command, delete, query, or verify the physical
module map; it assumes the required external module-map reset was completed
before installation. Baseline maps contain every front-panel logical channel
exactly once. The normal fresh-pairing map is the identity map; any later
mapping change is append-only replacement documentation.

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
| `last_reported_scpi_channel_count` | `INT` | Latest SCPI/configuration count; diagnostic routing information, not physical capacity |
| `notes` | `NVARCHAR(MAX) NULL` | Switch notes |
| `created_at_utc` | `DATETIME2(3)` | Creation time |
| `updated_at_utc` | `DATETIME2(3)` | Last update time |

Rules:

- `switch_serial` is unique.
- `last_reported_scpi_channel_count` is greater than zero.
- `UNITS.front_panel_channel_count`, derived from the part number, is the
  customer-channel boundary. No assumed total physical capacity is stored.
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
| `station_number` | `INT NULL` | Simple positive station identifier; legacy runs may be null |
| `wavelength_mode` | `VARCHAR(2)` | `SM` or `MM` |
| `operating_band` | `VARCHAR(20)` | O band or C band |
| `application_version` | `NVARCHAR(30)` | Light Workbench version |
| `completion_status` | `VARCHAR(20)` | Run lifecycle status |
| `run_purpose` | `VARCHAR(30)` | Purpose of the run |
| `analysis_status` | `VARCHAR(20)` | Analysis eligibility |
| `void_info_json` | `NVARCHAR(MAX) NULL` | Required immutable void timestamp, operator, and reason when status is `excluded` |
| `superseded_by_run_id` | `BIGINT NULL` | Preferred replacement run |
| `part_number_snapshot` | `NVARCHAR(100) NULL` | Part number at test time |
| `front_panel_channel_count` | `INT NULL` | Required channels at test time |
| `measurement_hardware_json` | `NVARCHAR(MAX)` | ILM/OPM/laser identity plus extra-channel routing provenance and known channel counts |
| `limit_snapshot_json` | `NVARCHAR(MAX)` | Exact criteria used |
| `notes` | `NVARCHAR(MAX) NULL` | Run notes |
| `created_at_utc` | `DATETIME2(3)` | Database creation time |
| `updated_at_utc` | `DATETIME2(3)` | Last update time |

`client_run_uuid` is generated before the first insertion attempt and never
changes. Retrying a create operation with the same UUID must resolve the
existing run rather than create a duplicate.

For new database-backed runs, the operator enters a positive station number in
the Hardware Test Setup area. The station is stored on `IL_RUNS`, not in a
station registry. It is immutable after the run starts, is preserved through
retests and continuation, and is shown as `Not recorded` for older runs that
predate migration 0003. Loading an older run does not replace the session's
station default. Admin Mode cannot bypass the station requirement for a new
database run.

Operator-facing `run_number` is allocated per unit by the run repository. The
SQL implementation locks the unit row while it calculates the next number
across every historical assignment for that unit and inserts the run in the
same transaction. This keeps numbering continuous when a unit receives a
replacement switch and prevents cooperating clients from claiming the same
next number.

Controlled values:

| Field | Allowed values |
| --- | --- |
| `completion_status` | `in_progress`, `complete`, `stopped`, `failed` |
| `run_purpose` | `production`, `engineering`, `training`, `calibration` |
| `analysis_status` | `pending`, `included`, `excluded`, `superseded` |
| `wavelength_mode` | `SM`, `MM` |

Recommended defaults are `in_progress`, `production`, and `pending`.
`excluded` is displayed to operators as **Voided**. Voided rows require valid
`void_info_json` containing nonblank `voided_at_utc`, `voided_by`, and `reason`;
non-voided rows must keep that field null. Run purpose is descriptive and does
not implicitly void engineering, training, or calibration data. Purpose still
controls production-report filtering, while COC and assignment analysis apply
the same technical eligibility rules to every purpose.

Migration 0005 converts legacy exclusion reasons using the run's
`updated_at_utc` and `tested_by`, removes the obsolete reason column, and
expands the saved replacement-analysis result-state constraint.

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
| `logical_channel` | `INT NULL` | Customer-facing channel; null for unassigned extra candidates |
| `physical_port` | `INT` | Positive tested physical port |
| `measurement_role` | `VARCHAR(20)` | `logical_channel` or `extra_candidate` |
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
- Insertion-loss values must be present, finite, non-negative, and normalized
  to four decimal places before insertion.
- `reference_snapshot_json` contains valid JSON.
- The reference snapshot must be a non-empty object for an accepted write.
- Both wavelength results are inserted in one transaction.
- SM runs accept the 1310/1550 pair and MM runs accept the 850/1300 pair.
- Measurements may only be appended while their run remains `in_progress`.
- Temporary, live, invalid, and unwritten readings are never inserted.
- Raw measured power remains local engineering evidence, not analytical data.

The application creates an immutable pending measurement and its UUID before
the first insert attempt. The SQL repository obtains an update lock on the run
row, calculates the next attempt number for that run and logical channel, and
inserts both wavelength values in the same transaction. Cooperating concurrent
writers therefore cannot claim the same attempt number. A repeated UUID
returns the original row.

The UI may update its accepted-reading projection only after the repository
returns the committed row. If the transaction fails, the pending object and
UUID remain available for retry; the channel does not advance and no support
log or temporary reading becomes substitute storage.

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
| `source_recommendation_id` | `BIGINT NULL` | Saved analysis recommendation used for this replacement |

All channels and ports are positive, and previous/replacement ports cannot be
equal. A replacement belongs to an assignment rather than permanently to a
unit so records from a removed switch cannot alter a later switch's map.

New replacement records are accepted only for an active assignment. The
reported previous port must match that logical channel's current effective
port. A normal replacement port must be a confirmed committed extra candidate
for the same assignment, and it cannot already route another logical channel.
It is never compared with the SCPI-reported count. An
optional related run must belong to the same assignment. Replacing an already
replaced channel appends another row; earlier rows are never updated or
deleted.

Light Workbench documents replacements only. It does not command the switch,
use `CLOSe?` to infer a replaced route, or verify the external mapping change.
Replacement recommendations are also persisted as append-only analysis
snapshots. They are advisory and do not change the routing map. A completed
replacement may point to the exact recommendation that informed it through
`source_recommendation_id`; a null value means the replacement was manually
recorded without using a saved recommendation.

The database-backed editor is logical-channel centered. It resolves the
current effective physical port from `vw_CurrentChannelMap`, shows the complete
ordered SQL history, and derives assignment, related run, identity context,
and UTC time. Recommendation selection may prefill the proposed port,
category, improvement, and editable default reason, but selection is not a
write. The operator must still provide or confirm the reason and operator and
explicitly confirm that the physical reroute happened outside the application.
Optional details are stored without loss in `notes`.

Corrections, reversals, and repeated replacements append new rows. The UI does
not expose SQL history deletion or legacy void semantics. Replacement rows and
explicit spare designation/undesignation events approved in the same dialog
are validated and committed in one transaction. After commit or failure, the
application reloads the authoritative routing snapshot; no local replacement
fallback is permitted.

### `REPLACEMENT_ANALYSES`

One immutable snapshot of a completed replacement-analysis calculation. A run
may have many analyses; the latest one is the default display, while the full
history remains available for support and trend review.

| Field | SQL Server type | Description |
| --- | --- | --- |
| `analysis_id` | `BIGINT IDENTITY(1,1)` | Primary key |
| `analysis_uuid` | `UNIQUEIDENTIFIER` | Retry-safe analysis identity |
| `run_id` | `BIGINT` | Run analyzed |
| `analyzed_at_utc` | `DATETIME2(3)` | Calculation time |
| `analyzed_by` | `NVARCHAR(100)` | Operator associated with the run |
| `application_version` | `VARCHAR(30)` | Version that calculated the result |
| `source_measurement_high_watermark_id` | `BIGINT` | Maximum accepted measurement ID in the complete assignment-scoped source set; it may belong to any included run |
| `front_panel_channel_count` | `INT` | Front-panel count used |
| `wavelengths_json` | `NVARCHAR(MAX)` | Wavelength pair used |
| `criteria_json` | `NVARCHAR(MAX)` | Limit and analysis criteria snapshot |
| `result_status` | `VARCHAR(40)` | Classification of the saved calculation |
| `result_details_json` | `NVARCHAR(MAX)` | Bounded result details excluding normalized recommendations |

New `result_status` values are `optimized`, `recommendations_available`,
`verification_required`, `pass_no_viable_optimization`,
`fail_no_viable_recovery`, `incomplete_input`, and `review_required`. Legacy
`no_viable_recommendations` and `not_applicable_no_extra_ports` values remain
loadable. `result_details_json.source_snapshot` contains assignment/context
identity, included run states, every considered accepted measurement ID
(including superseded attempts and replaced-channel rows), selected measurement
IDs, replacement/spare event IDs, watermarks, and a deterministic state
fingerprint. Save-time validation confirms that the context run, included runs,
measurements, replacement history, and spare history still match atomically.
The scalar measurement high-watermark remains for compatibility and referential
integrity; freshness uses the full fingerprint. A changed source state makes
the snapshot stale but never mutates or removes it from history.

### `REPLACEMENT_ANALYSIS_RECOMMENDATIONS`

Normalized recommendation rows belonging to one saved analysis. Keeping the
candidate and measured losses in columns supports reporting without parsing
the result JSON.

| Field | SQL Server type | Description |
| --- | --- | --- |
| `recommendation_id` | `BIGINT IDENTITY(1,1)` | Primary key |
| `analysis_id` | `BIGINT` | Parent analysis |
| `recommendation_rank` | `INT` | Display/calculation order |
| `category` | `VARCHAR(20)` | `required` or `optional` |
| `logical_channel` | `INT` | Proposed logical channel |
| `current_physical_port` | `INT` | Current route |
| `candidate_physical_port` | `INT` | Measured replacement candidate |
| `current_wavelength_1_il_db` | `DECIMAL(9,4)` | Current first-wavelength loss |
| `current_wavelength_2_il_db` | `DECIMAL(9,4)` | Current second-wavelength loss |
| `candidate_wavelength_1_il_db` | `DECIMAL(9,4)` | Candidate first-wavelength loss |
| `candidate_wavelength_2_il_db` | `DECIMAL(9,4)` | Candidate second-wavelength loss |
| `current_worst_loss_db` | `DECIMAL(9,4)` | Current worst loss |
| `candidate_worst_loss_db` | `DECIMAL(9,4)` | Candidate worst loss |
| `improvement_db` | `DECIMAL(9,4)` | Projected improvement |
| `current_measurement_id` | `BIGINT NULL` | Exact logical-channel evidence used by a new recommendation |
| `candidate_measurement_id` | `BIGINT NULL` | Exact confirmed-extra evidence used by a new recommendation |

The unique analysis/rank, analysis/channel, and analysis/candidate-port
constraints prevent duplicate recommendations inside one snapshot.

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

Designation and undesignation events are accepted only for an active
assignment. A normal designation requires a confirmed extra measurement above
the assignment's front-panel boundary and the port must not be actively mapped.
Repeating the already-current action is rejected rather than adding a
meaningless audit row. Spare history remains readable after an assignment is
removed.

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

Returns the highest attempt for each run and measurement identity: logical
channel for `logical_channel` rows, or physical port for `extra_candidate`
rows.
The main readings table, limits, run status, COC preparation, Copy Raw Data,
and replacement recommendations use this view. Reading History and retest
reports query all `IL_MEASUREMENTS` rows.

The database repository exposes these as one stable run snapshot: current rows
come from the view in logical-channel order, and history rows come from the
append-only table in database commit order. Both queries execute in one
transaction while the run row is held stable, preventing a concurrent retest
from appearing in only one half of the snapshot.

The application converts that snapshot into one shared read model. Table
filters may choose which current rows are visible, but comparison, Copy Raw
Data, status, analysis, COC preparation, and replacement analysis always use
the complete unfiltered current projection. Reading History alone uses every
accepted attempt. Database-origin COC inputs carry a stable run identifier
rather than inventing a local source-file path.

For replacement decisions, `domain/effective_replacement_analysis.py` builds
an assignment-scoped projection across compatible runs no later than the
selected context run. It selects one newest whole wavelength pair per logical
channel, requires the recorded effective physical port, carries forward unused
measured extras, derives replacement verification, and creates a deterministic
SHA-256 source-state fingerprint. The fingerprint and source IDs are stored in
the existing analysis JSON, so append-only analyses can be labeled current,
stale, or historical without adding mutable watermark columns.

### `vw_CurrentChannelMap`

Combines `UNIT_SWITCH_ASSIGNMENTS.initial_channel_map_json` with the latest
`CHANNEL_REPLACEMENTS` row for each logical channel. It returns the assignment,
unit, switch, logical channel, effective physical port, replacement state, and
latest replacement timestamp.

The routing repository reads this view in logical-channel order and exposes
the append-only replacement and spare histories in database commit order. A
single stable routing snapshot returns the effective map, both histories, and
the active designated-spare set. This snapshot is scoped by `assignment_id`,
so replacing a physical switch starts from the new assignment's baseline map
without discarding or applying the old switch's history.

Existing active spares are presented as retained by default. Analysis-derived
spare suggestions may be preselected for review, but neither recommendation
generation nor opening the editor writes an event. An existing spare is
undesignated only by an explicit operator selection saved as a new append-only
event.

### `vw_ConfirmedExtraPorts`

Returns the newest eligible `extra_candidate` measurement for each
`(assignment_id, physical_port)`. Voided and superseded runs are excluded. The
view is the read-only source for normal replacement-candidate and spare
validation. Stopping discovery does not assert that every higher port is
absent.

### `vw_ReplacementRecommendationUsage`

Joins each normalized recommendation to any replacement record that cites it
through `source_recommendation_id`. This makes recommendation adoption
reportable without treating an advisory calculation as proof that the physical
reroute occurred. A recommendation with no matching replacement is simply
shown as unused.

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

Before a database-backed run begins, the application must:

1. Confirm database connectivity and supported schema version.
2. Resolve the unit, switch, and active assignment. A conflicting pairing is
   confirmed once and then handled atomically with run creation.
3. Validate required setup and reference state.
4. Generate `client_run_uuid`.
5. Insert the `in_progress` run and its historical snapshots.

When a new hardware pairing is confirmed, the same transaction also stops any
unfinished runs on the assignments being closed, records their end timestamp,
closes those assignments, creates the fresh identity map, and inserts the new
`in_progress` run. Historical runs, accepted measurements, replacement events,
spare events, and saved analyses remain attached to their original assignment;
none are carried into the new pairing.

Red Light Test and Power Measurement Diagnostics do not create run
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

The supported stale-run decisions are:

- Resume, which leaves the same run UUID and `in_progress` record intact.
- Close as stopped, for an operator-ended incomplete run.
- Close as failed, for a technical end state.

All close decisions record `run_ended_at_utc`. Measurement quality is never
inferred from the selected completion state.

An operator-selected continuation or retest explicitly reopens the retained
run as `in_progress` and clears its prior end timestamp before another accepted
attempt can be appended. Finishing the resumed workflow writes a new terminal
status and end timestamp. Accepted attempts remain append-only throughout this
lifecycle transition.

## Files that remain local

- Daily support-log JSONL and compressed archives.
- Explicit diagnostic history/trace exports.
- Generated COC workbooks.
- Explicit operator-requested CSV/JSON exports.
- Application configuration, including the database endpoint.

Existing run files remain viewable, but opening one does not upload it or make
it part of the authoritative database. A legacy file-backed run cannot be
continued or retested as if it were a database run.

For database-backed COC export, the operator explicitly chooses the output
folder because there is no authoritative local run directory. COC files remain
derived exports and are not written back as run storage.

## Read-only reporting

`Tools > Database Reports...` uses a read-only application reporting service
over the same repository and run-projection boundaries as the production UI.
It does not issue run, measurement, assignment, replacement, or spare writes.
The report includes:

- joined unit, switch, and assignment history;
- run history filtered by model, mode, operator, UTC date, completion status,
  purpose, and analysis status;
- complete accepted channel/attempt history, including superseded retests;
- retest counts and frequency;
- assignment replacement history with the outcome of the linked run reading;
- pass/fail and optimization results derived from current accepted readings
  and the immutable limit snapshot saved with that run; and
- explicit CSV export of the currently selected report tab.

Normal production metrics include only `production` runs whose
`analysis_status` is `included` and which have not been superseded. Pending,
excluded, superseded, engineering, training, and calibration data is available
only when the operator explicitly selects the broader troubleshooting scope.
CSV reports are local derived outputs, never authoritative storage or an
automatic synchronization mechanism.

## Security and operations

- Use Windows Authentication by default and least-privilege database roles.
- For workgroup deployments, use a dedicated SQL login mapped only to
  `lwb_app_writer`; never use `sa`, `sysadmin`, or `db_owner` for the runtime.
- SQL-password credentials are intentionally plaintext in the per-user INI for
  the approved temporary deployment model. Keep that file out of source
  control, support bundles, and shared folders.
- The shared SQL login identifies the application deployment, not an individual
  station. Station number and tester fields remain the application-level
  attribution fields.
- Rotate the shared password by updating the SQL login and every workstation's
  per-user INI.
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
- The database was introduced as a clean start; no historical bulk import is
  planned.
- SQL Server is authoritative for new run data on the database branch.
- Support logs remain local.
- The ten-table schema and four read-only views are the approved
  baseline.
- Read-only reporting lives in Light Workbench and uses application/repository
  boundaries rather than SQL in Qt presentation code.

Remaining before production:

1. Network SQL Server host and IT ownership.
2. Windows/domain groups and permissions.
3. Backup, restore, retention, and archival policy.
4. Exact production behavior for stale `in_progress` runs.

## Related documents

- `docs/DATA_ARCHITECTURE.md` - current SQL-primary data behavior and legacy
  file-compatibility boundary.
- `docs/DATABASE_ROADMAP.md` - implementation milestones and exit criteria.
- `docs/PROJECT_LAYOUT.md` - repository and source placement.
- `docs/SUPPORT_LOGGING.md` - local engineering-log ownership.
- `docs/TESTING_AND_RELEASE.md` - required validation and release checks.
Run purpose is selected when a new run begins and is persisted in `IL_RUNS`.
Production is the default; Engineering, Training, and Calibration are retained
for provenance and reporting but are not implicitly voided. Completion and
analysis are separate: a completed run is finalized as included, while stopped
or failed runs remain pending. Continuations and retests inherit the original
purpose. COC export is purpose-neutral: all purposes may contribute when they
satisfy the same assignment, measurement, compatibility, routing, and limit
requirements.
