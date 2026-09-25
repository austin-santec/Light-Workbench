# Data Architecture

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
Run JSON currently uses schema version 1; unit JSON uses schema version 2.
Migration helpers reject newer versions instead of silently dropping fields.

## Format responsibilities

- JSON or a future repository/database: canonical structured application data.
- CSV: human-readable measurement export and compatibility with existing tools.
- XLSX: COC/report output only; it is not the primary application database.
- Replacement analysis: calculated presentation data.
- Manually recorded replacements and spares: persistent device data.

## Persistence rules

- Save only accepted/written readings.
- Do not create empty run files for runs with no written measurements.
- Write files atomically where possible.
- Validate serials and path components before using them in filenames.
- Preserve older run layouts while loading them.
- Avoid modifying the original COC template; create a copy for each export.
- Preserve template graphics and unrelated cell content during COC export.

## Future multi-run analysis

If analysis grows to hundreds or thousands of runs, use a repository abstraction
and consider SQLite for indexing and aggregation. CSV should remain available
as an export, but application-wide queries should not require scanning every
CSV file manually.

The current reporting groundwork follows that boundary. `domain/reporting.py`
defines typed, read-only summaries from accepted measurements, while
`infrastructure/run_query.py` reads the unit's indexed CSV runs through the
repository adapters. It is intentionally not connected to the UI yet; future
operator reports can consume these summaries without knowing whether the
underlying storage remains file-based or moves to SQLite.
