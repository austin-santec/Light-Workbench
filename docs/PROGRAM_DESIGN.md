# Program Design

## Purpose

Light Workbench is a Windows optical-test application. Its current primary
workflow controls a Santec OSX-150 optical switch and an ILM-100 exposed as an
OP815 power meter. It measures insertion loss at 1310 nm and 1550 nm, guides
the operator through channel testing, stores accepted readings, and provides
analysis and COC export tools.

The long-term design must also support an OPM and separate laser source. The
application should therefore describe the test capabilities rather than being
hardcoded around the current ILM hardware.

## Current runtime boundaries

The current application is centered in `ilm_app.py`, with supporting modules
for hardware, measurement workers, persistence, analysis, live readings, red
light testing, and COC export. This is a working legacy architecture that is
being refactored incrementally.

The current entry point is `ilm_app.py`. `ILMReadLoss.py` is an older console
workflow and should be treated as legacy unless a change explicitly requires
maintaining it.

Typed, vendor-neutral domain models are being introduced in `domain/models.py`.
Shared default paths and injectable path bundles are defined in
`config/app_config.py`. Existing persistence modules retain compatibility facades
while the application migrates to those models.

The hardware-run lifecycle is being extracted into
`application/run_controller.py`. The controller owns the worker thread and
exposes queued commands and UI-facing signals; `MainWindow` remains the owner
of presentation and operator prompts during this migration.

`application/live_controller.py` and `application/red_light_controller.py`
provide the same separation for the meter-only Live IL and switch-only Red
Light workflows. Red Light switch I/O no longer runs directly in the dialog's
UI thread.

`application/power_diagnostics_controller.py` provides the same worker boundary
for the non-recording Power Measurement Diagnostics tool. Its dialog can own a
meter controller and an optional independent switch controller; raw readings,
reference math, and history remain in memory and never enter run persistence.

`application/hardware_planning.py` contains the pure channel-selection rules
for hardware runs. It converts UI selections into a `HardwareRunPlan` before
hardware is created, while preserving the worker's existing full-pass and
explicit-channel behavior.

`application/hardware_session.py` groups the transient operator state for an
active hardware run, including the pending uncommitted reading and the
configured channel count. This state is separate from persisted measurements:
only the existing commit path writes a reading to the run.

`domain/measurement.py` owns the instrument-independent insertion-loss formula.
Workers provide absolute measurements and reference powers to this service,
which keeps calculation logic reusable for an integrated ILM or separate OPM
and laser source.

`domain/diagnostic_analysis.py` owns the in-memory diagnostic sample model and
variation statistics. Manual samples and automatic monitoring samples carry
different acquisition methods so repeatability and stability analysis cannot
silently mix their populations. This module has no Qt, hardware, or
persistence dependencies.

`infrastructure/diagnostic_export.py` owns the explicit CSV/JSON export of
diagnostic history. The export is initiated by the operator and is separate
from run persistence; no diagnostic file is created merely by taking readings.
The operator may optionally include the in-memory OP815 hardware trace. CSV
exports write a companion `<history-stem>-hardware-trace.csv`; JSON exports
add a `hardware_trace` object containing session metadata and chronological
events. The trace is linked to each complete history reading by measurement ID
and is never collected or written by normal production runs.

`domain/reference.py` owns the zero-reference-to-offset conversion. Live IL,
reference calculation, simulation, and hardware workflows can therefore share
the same measurement rules without importing Qt or vendor drivers.

`domain/replacements.py` owns replacement recommendations, designated-spare
selection, and normalization of manually recorded replacements. It is kept
independent of Qt, hardware adapters, and CSV/JSON file formats.

`infrastructure/run_repository.py` is the application-facing boundary for
file-backed CSV/JSON run storage and numbered-run lookup. The established
`run_data.py` and `run_persistence.py` import paths remain compatibility
facades, so the UI no longer needs to know which file-backed repository
implementation is selected.

`infrastructure/unit_repository.py` provides the corresponding boundary for
unit JSON records, unit-level replacement/spare data, and numbered run-folder
resolution. Unit identity remains separate from run-specific switch identity.

`infrastructure/coc_exporter.py` provides the COC/report boundary for part
lookup, serial normalization, and XLSX generation. Template preservation and
graphics restoration remain infrastructure concerns rather than UI logic.

`domain/comparison.py` owns read-only measurement indexing and comparison-value
formatting. `domain/timing.py` owns switch-test session duration and metadata
rules; Live IL and Red Light tools do not instantiate that timer.

`domain/raw_export.py` owns pure formatting of accepted measurements for
clipboard transfer. It produces Excel-compatible tab-separated text and has no
Qt, filesystem, or hardware dependencies.

`domain/run_data.py` owns the loaded-run model and over-limit rules. CSV
formatting and compatibility parsing live in
`infrastructure/csv_run_loader.py`; the root `run_data.py` module remains a
compatibility facade for existing imports.

`infrastructure/run_persistence.py` owns run folder naming, atomic CSV/JSON
recording, continuation renaming, and legacy JSON loading. The root
`run_persistence.py` module remains a compatibility facade for older callers.

`infrastructure/unit_persistence.py` owns unit JSON records, numbered-run
paths, and normalization of shared replacements and designated spares. The
root `unit_persistence.py` module remains a compatibility facade.

`infrastructure/coc_export.py` owns template lookup, COC workbook creation,
merged-cell mapping, and preservation of the template's drawing package. The
root `coc_export.py` module remains a compatibility facade, while
`infrastructure/coc_exporter.py` remains the application-facing adapter.

`hardware/factory.py` is the composition point for selecting concrete meter
and switch adapters. The current default remains the integrated Santec ILM and
OSX-150, while a future OPM-plus-laser setup can be introduced without
spreading vendor selection through the UI.

`HardwareRunController.is_active` is the authoritative lifecycle check for a
normal hardware run. The main window uses it for command routing, tool guards,
and shutdown; legacy thread/worker references remain only as compatibility
fallbacks during the migration.

## Target layers

```text
UI widgets and dialogs
        ↓
Application controllers and workflow state
        ↓
Domain models and measurement/analysis services
        ↓
Hardware and persistence interfaces
        ↓
Vendor adapters, files, and external instruments
```

### UI layer

Responsible for displaying state, collecting operator input, and sending user
commands to controllers. UI code should not calculate insertion loss, write
CSV files, or call vendor drivers directly.

The main window remains in `ilm_app.py` as the application entry point. The
standalone Live IL and Red Light dialogs live in `ui/`; their root-level module
names remain compatibility facades for existing callers.

The Power Measurement Diagnostics dialog places its in-memory variation
analysis beside the history table in a resizable splitter. The panel is
presentation-only and can be hidden without clearing readings or analysis
results; collection, statistics, and export behavior remain in their existing
application/domain/infrastructure boundaries.

The panel also provides a presentation-only `Copy Analysis` action for the
currently displayed formatted summary. It does not create a file or alter
diagnostic history.

### Application layer

Responsible for workflows such as a hardware run, live IL reading, red light
testing, repeatability testing, and comparison runs. It owns state transitions,
worker lifecycle, cancellation, and user-facing error events.

### Domain layer

Responsible for instrument-independent concepts and rules: measurements,
references, insertion-loss calculation, limit analysis, replacements, spares,
run identity, and unit identity.

### Infrastructure layer

Responsible for concrete hardware drivers, VISA/DLL communication, CSV/JSON
storage, XLSX export, configuration paths, and packaging. A future indexed
storage option may be evaluated here without changing domain reporting.

## Important workflow rules

- Only accepted or written measurements belong in the saved run data.
- A read that is not written may update the screen but must not alter persisted
  run results.
- Live IL reading and red light testing are independent tools and must not add
  switch-test timing or run measurements.
- A run belongs to a unit, but switch identity is run-specific.
- Replacements and designated spares are device-level information and are
  shared across runs for that unit.
- Replacement analysis is derived guidance, not a record of what the operator
  actually changed. Manually recorded replacements are authoritative.
- Existing run formats should remain readable when storage changes.

## Refactoring strategy

Use an incremental migration. Move one responsibility behind a stable
interface, add regression tests, and then update callers. Avoid a complete
rewrite because the current behavior has been tested in the field and includes
many important operator workflows.
