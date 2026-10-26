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
- Append-only replacement audit history and its current effective projection
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

The current CSV and JSON formats remain supported for legacy compatibility.
Opening them does not upload their contents or make them writable database
runs. If a future file schema changes, include a
`schema_version` and provide a migration path.
Run JSON currently uses schema version 6; unit JSON uses schema version 3.
Migration helpers reject newer versions instead of silently dropping fields.

Schema version 6 stores wavelength-aware measurements without assigning SM
names to MM values. Each reading and accepted attempt records the operator-
selected mode, ordered OPM wavelengths, nominal source wavelengths and source
IDs, classification metadata, and a wavelength-keyed loss map. New records do
not claim that SM/MM was detected from hardware; historical compatibility
classifications remain readable.
Legacy `loss_1310_db` and `loss_1550_db` fields remain available only for SM
records. CSV measurement and reference headers are generated from the run's
actual OPM wavelength pair. Files without wavelength metadata or generic maps
continue to load as native SM 1310/1550 runs.

## Format responsibilities

- SQL Server: canonical structured application data for new production runs on
  the database branch.
- JSON/CSV: legacy viewing, explicit exports, and compatibility with existing
  tools; they are not an automatic authoritative write path on this branch.
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
- Manually recorded replacements and spares: persistent assignment data. For
  database runs, the logical channel, current effective port, assignment,
  related run, identity context, and UTC timestamp are derived automatically.
  The operator supplies or confirms the proposed port, reason, operator,
  optional details, and that the physical reroute was completed externally.
  Replacement history is append-only, so `logical 14: 14 -> 41 -> 43` remains
  available for audit while COC and normal UI consumers receive the effective
  `14 -> 43` projection. Corrections/reversals append another SQL row. Legacy
  void events remain readable only for file-backed compatibility.

Accepted reading history is stored separately from the latest-reading
projection. Run JSON schema version 6 contains `measurement_attempts`, an
append-only record for every accepted two-wavelength Write IL result. Each
record has a stable attempt ID, run ID, logical channel, physical port, attempt
number, both losses, UTC acceptance time, operator, write context, reference
snapshot, and the prior attempt ID when it supersedes a reading. The existing
`measurements` collection remains the latest/effective value per channel and
continues to drive the table, analysis, raw export, and COC workflows.

`View Reading History...` in the Run information box is a read-only viewer for
current and superseded attempts. It does not require connected hardware.
Temporary live readings, rejected readings, failed readings, and diagnostic
readings are not accepted attempts. Legacy runs without this collection are
loaded by synthesizing one `legacy_import` attempt per existing effective row;
the legacy file is not rewritten until a later save changes the run.

Numbered-run navigation keeps the loaded unit directory as its preferred
repository context, even when that directory is nested under a descriptive
folder or has been renamed. Before using it, the application validates the
persisted unit identity against the setup fields: matching main-board serials
are authoritative, part number is a fallback only when both serials are
missing, and switch serial is intentionally ignored because switches can be
replaced. If the context is absent or does not validate, navigation falls back
to the canonical `Documents/ILM-Reads/Unit-*` location and reports the exact
folder searched when a requested run is unavailable.

## Run completion and result assessment

The desktop UI displays two derived statuses beside the `Compare with:` control
above the readings table. `completion_status` describes whether the run
collected the channels in its own saved plan; it does not mean that the data
passes production limits. The supported completion values are
`not_started`, `in_progress`, `complete`, `incomplete`, `interrupted`, and
`unknown`. A two-channel retest can therefore be `complete` at 2/2 even when
it is not a complete standalone production dataset.

The separate result status describes the accepted readings: `pass`,
`pass_optimization_available`, `pass_review_recommended`,
`fail_recoverable`, `fail_unrecoverable`, `composite_pass_available`,
`supplemental_run`, `not_evaluated`, or `review_required`. A composite or
supplemental value remains available for compatibility with older persisted
data, but a current valid passing multi-run projection is displayed as
`composite_pass_available`, including when the loaded run is partial. The
status detail identifies the loaded run's supplemental role and contributing
run numbers. The green composite status also indicates that COC creation is
available, but it does not create a COC automatically. A composite status is
shown only when the existing validated COC preparation rules find a compatible
persisted run and a passing combination. This assessment uses the same
latest-measurement projection as COC preparation. It
never creates a COC, changes a measurement, or changes switch mapping data. It
is recalculated when readings, replacements, criteria, or compatible runs
change. A newer failing retest therefore supersedes an older passing reading
in the displayed result.

New run JSON files add a `run_status` object containing the completion state,
reason, planned/completed counts, and terminal UTC timestamp. The same
additive values are available in run metadata for a future database
`completion_status` field. Older files remain loadable; when their original
channel plan cannot be reconstructed, completion is reported as `unknown`
rather than inferred from the current table filter.

## Validated COC view

A COC can use any number of compatible persisted runs. This creates a
temporary report view, not another run. For each logical channel, the newest
valid complete wavelength pair wins; individual wavelengths are never mixed.
Database recency is written UTC time, attempt number, then measurement ID.
Legacy file records without timestamps use deterministic run/attempt order.
Changed physical ports must agree with the unit's completed replacement
records. Source measurements, references, replacement records, and hardware
state remain unchanged.

The three-digit channel field in the selected context run's supported OSX-100 or
OSX-150 part number defines the confirmed front-panel count and required
logical channels `1..N`. The operator does not enter this value manually.
Every required channel must be present and valid, and each loss rounded to the
established four-decimal display precision must be below the selected model's
fail limit. OSX-100 uses 0.8000 dB; OSX-150 uses 2.5000 dB. Readings above the
front-panel count may support replacement analysis but are excluded from the
workbook.

The context run metadata records the COC output path, front-panel count, all
compatible runs considered, contributing runs, excluded-run reasons, and each
effective logical-channel/physical-port source. This provenance does not
change any source run's accepted measurement list.
Each approved model/mode uses separate templates for capacities 1-45 and
46-48; the exporter removes unused rows and updates merged ranges and print
area on the copied workbook only. Output files use the local-time name format
`COC <OSX-100 or OSX-150> <Main Board serial>_YYMMDD-HHMMSS.xlsx`, with a
numeric collision suffix when multiple exports occur in the same second.

OSX-100 SM and MM runs can be merged into their matching COC workflows.
OSX-150 MM remains reviewable and analyzable as run data, but is blocked from
COC export because no approved OSX-150 MM template/profile exists.

## Reference authorization and audit model

Reference values are not authorized merely because numbers appear in the main
window. The Reference panel is beside Hardware Controls below Current
readings, while the application keeps a session-only reference bank with these
important states:
not referenced, calculating, valid calculated, valid manual admin, and
invalidated. A production run requires a valid reference for the exact current
measurement context.

The session bank can hold separate SM (1310/1550) and MM (850/1300)
references for the connected meter/source configuration. Changing mode selects
the matching cached reference when one exists; it does not erase the other
mode's reference. Loading a run or CSV never imports its historical reference
into the active session and never invalidates the session bank. Historical
reference snapshots remain attached to their saved readings for auditability.

A confirmed ILM/power-meter disconnection clears the session reference bank and
requires a new reference after reconnection. Optical-switch-only changes do
not clear it. A transient command failure is not treated as a confirmed
disconnection. Reference recalculation is transactional: a failed replacement
calculation leaves the previous valid reference active, and partial
two-wavelength results are never applied.

`Calculate Reference` creates an immutable snapshot containing a unique ID,
both wavelength values, method, UTC timestamp, and connected meter/laser
identity. Admin Mode can create a `manual_admin` snapshot only through the
explicit `Apply Manual Reference` action. The normal reference fields are
read-only; diagnostic tools may use temporary values, and only an explicit
diagnostic Apply action can authorize a calculated diagnostic snapshot.

Every accepted measurement stores the snapshot used for its IL calculation in
JSON. The CSV uses a run-local `Reference used` value such as `Ref 1` and
stores each complete immutable snapshot once in a reference catalog beside the
metadata. A run can therefore use `Ref 1`, `Ref 2`, and later references
without repeating the values, method, timestamp, or device identity on every
measurement row. The JSON contains both the labeled `reference_snapshots`
history and an explicit `reference_catalog`; superseded accepted attempts keep
their references available for audit. Loaded historical references are
displayed for audit context but never authorize new hardware acquisition or
replace the active session reference.

## Persistence rules

- Save only accepted/written readings.
- Do not create empty run files for runs with no written measurements.
- Write files atomically where possible.
- Validate serials and path components before using them in filenames.
- Preserve older run layouts while loading them.
- Keep legacy per-row reference CSVs readable while writing new runs with a
  deduplicated run-level reference catalog.
- Database replacement records are assignment-scoped documentation. Legacy
  file-backed replacement records remain unit-level for compatibility. The replacement workflow
  does not use `CLOSe?`, change switch mappings, identify routed logical
  channels, or verify a manually performed hardware change. General
  `CLOSe?` behavior elsewhere remains a separate hardware concern.
- Database replacement analyses are append-only snapshots tied to the run and
  the highest accepted measurement included. The latest snapshot is restored
  when a database run is loaded; a newer retest marks it stale and requires a
  new calculation. Normalized recommendations retain their measured evidence,
  while result details and criteria remain JSON snapshots.
- A completed replacement may reference the recommendation that informed it
  through `source_recommendation_id`. This records recommendation usage without
  claiming that Light Workbench commanded or verified the physical reroute.
  Optional operator details use `CHANNEL_REPLACEMENTS.notes`; no local routing
  fallback is created if the database write fails.

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

## Extra physical-port attempts

Optional engineering-interface probes above the part-number-derived
front-panel count are not database records. Route attempts, unverified routes,
temporary readings, retries, invalid/dark results, No More Physical Ports, and
Stop Extra Testing remain local support evidence only. The program never
updates authoritative switch capacity from one of these outcomes.

An extra candidate enters `IL_MEASUREMENTS` only after a complete valid
two-wavelength sample and explicit Write IL. It uses the candidate number as
both `logical_channel` and `physical_port`, matching the existing extra-reading
convention; its spare-candidate meaning is derived because it is greater than
the run's immutable front-panel count. The normal atomic commit, append-only
attempt history, reference snapshot, and operator identity rules are unchanged.
Extra rows are available to replacement analysis but are excluded from
front-panel completion and direct COC rows.

The optional phase has a transient/support state of `not_offered`, `declined`,
`in_progress`, `completed`, `stopped`, `failed`,
`end_of_installed_ports_reported`, or `safety_ceiling_reached`. A phase failure
does not delete or invalidate accepted front-panel data, and final required-run
quality remains based on front-panel channels.

## Planned SQL Server persistence

The database-focused development branch uses SQL Server as the authoritative
store for future run data after the Milestone 9 cutover. Existing CSV/JSON runs
are mainly development and test data; no historical bulk-import milestone is
planned. CSV and JSON may remain
explicit export or view formats, but application-wide queries should not
require scanning run folders after the database cutover.

The current reporting groundwork follows that boundary. `domain/reporting.py`
defines typed, read-only summaries from accepted measurements, while
`infrastructure/run_query.py` reads the unit's indexed CSV runs through the
repository adapters. It is intentionally not connected to the UI yet; future
operator reports can consume these summaries without knowing whether the
underlying storage remains file-based or moves to a central database.

The approved design intentionally does not add SQLite, a shared database file,
or a local synchronization outbox. SQL Server writes belong behind repository
interfaces. Once the database branch cuts over, production Start Run requires a
successful database/schema preflight and an accepted Write IL operation is not
complete until its atomic two-wavelength transaction commits. Red Light Test
and Power Measurement Diagnostics may remain available without the run
database because they do not create production run records.

`domain/reporting.py` provides this aggregation through
`aggregate_run_summaries`. Timing averages exclude runs without recorded
switch-test timing, while over-limit counts remain included. Repeatability
measurements are intentionally not included because they are not persisted as
accepted switch-test readings.

`infrastructure/run_reports.py` combines the file query and domain reporting
boundaries. It can aggregate one unit or all indexed `Unit-*` folders under a
run root, which gives a future analysis screen one stable entry point without
requiring it to know the CSV layout.

The approved schema is documented in `docs/DATABASE_ARCHITECTURE.md`; staged
implementation is in `docs/DATABASE_ROADMAP.md`. It stores future units,
switches, assignments, runs, accepted attempts, replacement records, and spare
events. Support logs and raw power remain local. Database-backed replacement
analysis is stored as append-only snapshots with normalized recommendations;
file-backed legacy runs retain session-local analysis behavior.

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
warning limit. Loading a run restores that snapshot for both SM and MM; the
active connected switch is not used to reinterpret historical data. Legacy
runs without a snapshot infer a model from persisted metadata and the mode
from the run wavelengths. If a snapshot is contradictory or a safe model/mode
profile cannot be found, limits are unavailable and the run remains viewable
without an unsafe OSX-150 fallback. Legacy SM files may still use their
original single warning limit when no better identity is available.
