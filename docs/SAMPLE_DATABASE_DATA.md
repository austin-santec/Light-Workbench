# Sample database data

Light Workbench includes a small, reusable seeding tool for development and
demonstration data. It is intentionally separate from normal operator runs:
it creates synthetic records in SQL Server through the same application
workflows, but it never imports local CSV/JSON history and never deletes or
refreshes database records.

## Available scenarios

The declarative scenario files are in `sample_data/scenarios/`:

| Scenario | Purpose | Contents |
| --- | --- | --- |
| `SAMPLE-OSX150-OPT-ENGINEERING` | Engineering/replacement demonstration | Two complete excluded engineering runs. Run 1 has all 36 channels; Run 2 retests logical channels 9 and 20 after documented replacements to physical ports 43 and 41. |
| `SAMPLE-OSX150-COC-DEMO` | COC and combined-run demonstration | A multi-run pattern using a separate synthetic unit. The current scenario uses two runs; both are production-shaped but explicitly excluded from production analysis so they cannot become production data accidentally. |

Both scenarios include deterministic references, limit snapshots, hardware
identity, channel maps, designated spares, replacement history, and generated
two-wavelength measurements. The sample unit serials, switch serials, and
scenario IDs all begin with `SAMPLE-` to make their purpose clear.

The engineering scenario is useful for run loading, retest history, status
display, replacement analysis, reporting, and multi-run COC creation. The
COC demonstration keeps a production-shaped purpose so it can also demonstrate
production-analysis filtering, but its explicit analysis exclusion keeps it
out of normal production reporting. Run purpose does not block COC creation;
measurement eligibility and compatibility rules do.

## Running the tool

The tool is dry-run by default:

```powershell
python tools/seed_sample_runs.py --list
python tools/seed_sample_runs.py --scenario SAMPLE-OSX150-OPT-ENGINEERING
python tools/seed_sample_runs.py --all --inspect-existing
```

The dry-run prints the configured SQL Server/database target, the selected
scenario counts, and the planned create-only writes. `--inspect-existing` also
reports whether each scenario is new, already complete, or conflicting when a
safe local SQL Server is available.

After reviewing the target and plan, apply one scenario or both:

```powershell
python tools/seed_sample_runs.py --scenario SAMPLE-OSX150-OPT-ENGINEERING --apply
python tools/seed_sample_runs.py --all --apply
```

The initial approved target is Windows-authenticated
`localhost\SQLEXPRESS` / `LWBTestDB`, loaded from the normal per-user
`database.ini`. The command refuses disabled settings, non-local servers, and
database names that do not clearly identify a test/development/local/sandbox
database. It does not accept credentials on the command line.

## Safety and repeatability

- The default action is read-only dry-run.
- `--apply` uses the database readiness check and the existing unit/switch,
  run-lifecycle, measurement, replacement, and spare workflows.
- There is no delete, truncate, refresh, or historical-import operation.
- Deterministic UUIDs make a completed scenario safe to run again. A complete
  matching scenario becomes a no-op.
- A partial scenario, mismatched sample identity, or unrelated existing run
  causes the tool to stop rather than guess how to repair it.
- Measurements are accepted two-wavelength records; raw power and local
  support-log data remain outside the database as required by the architecture.

## Adding another sample scenario

Copy an existing JSON file and give it a new `scenario_id`, unit serial, and
switch serial beginning with `SAMPLE-`. Keep the following structure:

1. Define one unit, one switch, and a complete initial logical-to-physical map.
2. Define one or more consecutive runs with UTC timestamps, a valid reference
   snapshot, a valid model/mode limit snapshot, and either explicit
   `measurements` or a deterministic `generated_measurements` block.
3. Use `overrides` for important channels that need a visible warning/failure
   or a known value. Generated values use a stable integer seed.
4. Add replacements with `related_run_number` when a later run represents a
   retest after a documented route change. Add designated spare ports only
   where the demonstration needs them.
5. Choose the run purpose that the sample is meant to demonstrate. Any valid
   purpose can be used for COC demonstrations, but set `analysis_status` to
   `excluded` and provide an explicit exclusion reason when synthetic data must
   stay out of normal production reporting.

The loader validates the scenario before writing. It checks model identity,
channel-map coverage, switch capacity, UTC timestamps, references, limits,
duplicate channels, replacement fields, and the `SAMPLE-` safety boundary.

## Verification and limitations

After applying, the tool reloads the unit, runs, measurement history, routing
snapshot, replacement history, and active spare list through the database read
model. It reports the allocated database IDs and the counts it verified.

This is synthetic demonstration data. It is not a hardware validation tool,
does not command an optical switch or ILM, and does not replace manual testing
of SQL-primary production runs. Do not seed a production database.
