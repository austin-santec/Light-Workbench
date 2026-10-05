# Data Architecture

Always-on engineering support JSONL is intentionally separate from production
run persistence. It may contain temporary readings, hardware commands, and
workflow context, but it does not modify CSV/JSON/unit/COC schemas and is not an
authoritative result or immutable audit record. See `SUPPORT_LOGGING.md` for
the event schema, redaction, retention, and bundle policy.

## Unit and run ownership

A unit represents the device being built and may contain multiple tests. A run
represents one switch test of that unit.

### Unit-level data

- Main board serial
- Part number
- Completed replacement records
- Designated spare channels
- Other information that should remain consistent when the switch changes

### Run-level data

- Run number
- Switch serial
- Operating band
- Tested-by initials
- Start, stop, and accumulated switch-test timing
- Accepted channel measurements
- Run-specific metadata

Reference values are measurement-session inputs and should not be treated as
permanent unit data. Replacement analysis is derived and should be recalculated
from the current readings rather than stored as authoritative history.

## Canonical data model

New code should work with typed domain models first and serialize them second.
The storage format should not determine how business logic represents data.

The current CSV and JSON formats remain supported for compatibility. If a
future schema changes, include a `schema_version` and provide a migration path.
Run JSON currently uses schema version 3; unit JSON uses schema version 2.
Migration helpers reject newer versions instead of silently dropping fields.

## Format responsibilities

- JSON or a future repository/database: canonical structured application data.
- CSV: human-readable measurement export and compatibility with existing tools.
- Clipboard raw-data copy: transient tab-separated text from accepted readings;
  it is not persisted and excludes metadata and pending readings.
- Diagnostic history export: an explicit operator-selected CSV or JSON export
  of temporary Power Measurement Diagnostics samples; it is separate from run
  persistence and never changes the active run. The export can optionally
  include the diagnostic session's in-memory hardware trace. CSV uses a
  companion `<history-stem>-hardware-trace.csv`; JSON adds a `hardware_trace`
  object. Trace events are investigative data only and are not part of run
  persistence. Automatically suggested diagnostic filenames use local time in
  the form `diagnostic-history-YYYYMMDD-HHMMSS` with deterministic `-01`,
  `-02`, and later suffixes when a same-second export already exists.
- XLSX: COC/report output only; it is not the primary application database.
- Replacement analysis: calculated presentation data.
- Manually recorded replacements and spares: persistent device data.

## Reference authorization and audit model

Reference values are not authorized merely because numbers appear in the main
window. The application keeps a session-only reference state with these
important states: not referenced, calculating, valid calculated, valid manual
admin, and invalidated. A production run requires a valid state. Disconnecting
or changing the measurement hardware invalidates the session and requires a new
reference calculation.

`Calculate Reference` creates an immutable snapshot containing a unique ID,
both wavelength values, method, UTC timestamp, and connected meter/laser
identity. Admin Mode can create a `manual_admin` snapshot only through the
explicit `Apply Manual Reference` action. The normal reference fields are
read-only; diagnostic tools may use temporary values, and only an explicit
diagnostic Apply action can authorize a calculated diagnostic snapshot.

Every accepted measurement stores the snapshot used for its IL calculation in
JSON and in the extended CSV audit columns. The JSON also contains a unique
run-level `reference_snapshots` history. Loaded historical references are
displayed for audit context but never authorize new hardware acquisition.

## Persistence rules

- Save only accepted/written readings.
- Do not create empty run files for runs with no written measurements.
- Write files atomically where possible.
- Validate serials and path components before using them in filenames.
- Preserve older run layouts while loading them.

## Rejected measurement evidence

Calculated reference readings below **-40.0 dBm** are rejected before a
production reference snapshot is authorized; exactly -40.0 dBm is not rejected
by this rule. Negative insertion loss is evaluated after rounding to the
application's four-decimal display precision. Such samples remain temporary
screen/support evidence only: they do not replace an accepted channel or alter
CSV, JSON, COC, unit, comparison, or replacement-analysis data. The active
reference is not automatically invalidated by one negative sample.

Support logs may retain the raw evidence and a coalesced negative-reading
episode, including its start, invalid-sample count, and cleared/ended outcome.
- Avoid modifying the original COC template; create a copy for each export.
- Preserve template graphics and unrelated cell content during COC export.
- Keep clipboard exports read-only with respect to run and unit persistence.

## Future multi-run analysis

If analysis grows to hundreds or thousands of runs, use a repository abstraction
and consider a central database for indexing and aggregation. CSV should remain
available as an export, but application-wide queries should not require scanning
every CSV file manually.

The current reporting groundwork follows that boundary. `domain/reporting.py`
defines typed, read-only summaries from accepted measurements, while
`infrastructure/run_query.py` reads the unit's indexed CSV runs through the
repository adapters. It is intentionally not connected to the UI yet; future
operator reports can consume these summaries without knowing whether the
underlying storage remains file-based or moves to a central database.

The current proposal intentionally does not add SQLite. A future database
repository should write directly to the approved central database while keeping
CSV/JSON as the local record and recovery path. Database availability must not
block hardware testing or local persistence.

`domain/reporting.py` provides this aggregation through
`aggregate_run_summaries`. Timing averages exclude runs without recorded
switch-test timing, while over-limit counts remain included. Repeatability
measurements are intentionally not included because they are not persisted as
accepted switch-test readings.

`infrastructure/run_reports.py` combines the file query and domain reporting
boundaries. It can aggregate one unit or all indexed `Unit-*` folders under a
run root, which gives a future analysis screen one stable entry point without
requiring it to know the CSV layout.

The planned database extension is documented separately in
`docs/DATABASE_ARCHITECTURE.md`. Its implementation milestones are in
`docs/DATABASE_ROADMAP.md`. The database design preserves this file-backed
model: CSV and JSON remain available, accepted/written measurements are the
analytical inputs, and replacement recommendations remain derived data.

## Controlled quality criteria

Production criteria are separate from hardware-driver configuration. The
current profiles are stored at `%LOCALAPPDATA%\\LightWorkbench\\config\\limit_profiles.ini`
and can be changed only through `Edit > Admin Mode...` followed by
`Edit > Admin Config...`. Admin authorization is session-only and the
password is never persisted or written to support logs.

The shipped defaults are:

| Model | Too-good warning | Optimization warning | Formal failure |
| --- | ---: | ---: | ---: |
| OSX-100 | below 0.2000 dB | not applicable | above 0.8000 dB |
| OSX-150 | below 0.5000 dB | above 2.2500 dB | above 2.5000 dB |

Equality at any boundary is not flagged. Too-good and optimization warnings
do not turn a table row red or prevent writing a reading; only formal failures
are red and are selected by the failure-selection control. Each new run stores
the resolved model, profile name/revision, and all threshold values in its JSON
criteria snapshot. Legacy run JSON remains readable through its original
warning limit.
