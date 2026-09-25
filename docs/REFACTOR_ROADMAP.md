# Refactor Roadmap

This roadmap is intentionally incremental. Each phase should leave the
application usable and should be completed with tests before the next phase.

## Phase 1A — Hardware capability boundary

Status: complete.

- Add vendor-neutral `PowerMeter`, `LaserSource`, and `OpticalSwitch`
  protocols.
- Keep existing vendor modules and imports working.
- Validate common wavelength requirements in one place.
- Add contract tests.

## Phase 1B — Typed domain models and configuration

Status: complete.

- Introduce typed models for measurements, references, units, and runs.
- Introduce enums for wavelengths, run states, channel modes, and statuses.
- Centralize output, template, lookup, and application-data paths.
- Keep serialization compatibility through explicit conversion functions.

The initial models are in `domain/models.py` and centralized defaults are in
`app_config.py`. Existing persistence modules continue to expose their old
imports and field names while callers migrate incrementally.

## Phase 2 — Workflow controllers and state machine

Status: complete for the current desktop workflows.

The first increment extracts the real hardware-run thread and worker
ownership into `application/run_controller.py`. The controller provides typed
run requests, explicit lifecycle states, queued worker commands, and terminal
cleanup. The second increment adds `LiveILReadingController` and
`RedLightTestController`; Live IL and Red Light dialogs now remain presentation
boundaries while their workers and hardware sessions are managed in the
application layer.

The third increment adds `application/hardware_planning.py`. It normalizes
full-pass, single-channel, and specific-channel selections before the UI
starts a controller. The legacy `ilm_app.parse_hardware_channels` import
shape remains available through a compatibility import while callers migrate.

The fourth increment adds `application/hardware_session.py`. It groups the
operator-facing pending-reading, channel-selection, and pass-mode state that
was previously held in separate `MainWindow` attributes. Compatibility
properties keep the current UI and test seams stable while the state moves
behind the application layer.

The fifth increment makes `HardwareRunController.is_active` the authoritative
normal-run lifecycle check. `MainWindow` now routes normal commands and
shutdown through the controller; its thread/worker attributes remain only as
compatibility seams for older tests and callers.

The sixth increment adds `domain/measurement.py`. Insertion-loss calculation
now lives outside the worker and accepts instrument-neutral power mappings;
the worker remains responsible for routing, waiting, and lifecycle events.

The seventh increment adds `domain/reference.py` and moves Live IL and
simulation callers onto the shared domain measurement and reference services.
The old top-level `reference_calculation.py` remains a compatibility facade.

The eighth increment adds `domain/replacements.py` and moves replacement,
spare, and completed-replacement metadata rules into the domain layer. The old
top-level `replacement_analysis.py` remains a compatibility facade while
callers migrate.

The ninth increment adds `infrastructure/run_repository.py`. `MainWindow` now
uses the repository boundary for run CSV/JSON loading, numbered-run lookup,
and recorder creation. The existing file implementation remains compatible
behind the adapter while future storage options can be introduced there.

The tenth increment adds `infrastructure/unit_repository.py`. Unit JSON,
unit-level replacement/spare data, and numbered-run path resolution now have
the same application-facing boundary.

The eleventh increment adds `infrastructure/coc_exporter.py`. COC template
lookup, serial normalization, and XLSX export are now reached through an
application-facing exporter while preserving the existing workbook behavior.

The twelfth increment adds `domain/comparison.py` and `domain/timing.py`.
Comparison table preparation and switch-test timing now live outside the UI;
the historical `switch_timing.py` import remains a compatibility facade.

- Extract hardware-run lifecycle from `ilm_app.py`.
- Define explicit start, reading, writing, stopping, completed, failed, and
  closing states.
- Create shared controller patterns for hardware run, live reading, and red
  light workflows.
- Keep Qt widgets as observers and command senders.
- Add lifecycle regression tests using real Qt event loops and fake hardware.

## Phase 3 — Domain and infrastructure separation

Status: complete for the current file-backed architecture.

- Move insertion-loss, reference, replacement, comparison, and timing logic
  into domain services.
- Move CSV/JSON/unit/COC operations behind repository/export interfaces.
- Keep file-format conversion at the infrastructure boundary.

## Phase 4 — Hardware composition

- Status: complete for the current integrated ILM and simulated hardware paths.

- Add adapter factories/configuration.
- Support integrated ILM and OPM-plus-laser combinations.
- Add simulated laser and switch implementations.
- Keep hardware discovery and active sessions separate.

The first Phase 4 increment adds `hardware/factory.py`. Normal hardware runs,
reference calculation, Live IL, and Red Light now receive the configured meter
and switch adapters through one composition point.

The second Phase 4 increment adds `hardware/simulated.py` with contract
compatible laser and switch adapters. Future OPM-plus-laser workflows can be
developed and tested without vendor hardware.

The third Phase 4 increment adds `hardware/session.py` for composed hardware
lifecycle and partial-startup cleanup. The existing controllers continue to
own their current sessions until this shared boundary is adopted incrementally.

The fourth Phase 4 increment adopts `OpticalTestSession` in
`MeasurementWorker`. The normal switch-test worker now uses the shared
connection and cleanup path while retaining its existing adapter API.

The fifth Phase 4 increment adopts the same session in Live IL and Red Light
workers. These tools remain independent workflows, but all three hardware
paths now share partial-startup cleanup behavior.

## Phase 5 — Storage and reporting

- Status: complete for file-backed storage and reporting; SQLite remains intentionally deferred.

- Add schema versions and migration functions.
- Evaluate SQLite for multi-run analysis while preserving CSV export.
- Add query/report services for operator, timing, limit, and repeatability
  analysis.

## Phase 6 — Tooling and release quality

- Status: complete for source validation, CI, release layout verification, ZIP packaging, and opt-in packaged smoke testing.

- Add `pyproject.toml`, formatter, linter, type checker, and pre-commit hooks.
- Add continuous integration for tests and static checks.
- Separate source, documentation, and release artifacts.
- Add repeatable clean-machine packaging and smoke tests.

## Phase completion rule

Do not advance a phase merely because the code was moved. The phase is done
when behavior is covered by tests, documentation is updated, and the current
operator workflow remains usable.

Current Phase 5 increment: `infrastructure/schema.py` adds explicit run and
unit JSON schema versions. Legacy payloads are normalized through migration
helpers, and unsupported future versions are rejected safely.

Current Phase 5 reporting increment: `domain/reporting.py` and
`infrastructure/run_query.py` provide typed summaries and read-only indexed-run
queries without adding UI behavior.

SQLite indexing is deferred. Current Phase 5 reporting remains file-backed and
performs aggregation in memory, preserving CSV/JSON compatibility without
adding a database dependency.

The current aggregation increment adds overall and per-tester timing and
warning-limit summaries over selected saved runs. It remains a domain service
with no UI or persistence changes.

The file-backed report increment adds `infrastructure/run_reports.py`, which
collects one unit or all indexed unit folders before calling the domain
aggregator. This preserves the same separation if a different storage option
is evaluated later.

Phase 6 tooling increment: `pyproject.toml` now provides shared Black, Ruff,
and Mypy configuration plus the supported 32-bit Python runtime declaration.
The project remains a PyInstaller application rather than a pip-installable
package, and the existing Windows dependency file remains authoritative for
runtime/build installation.

The next tooling increment adds optional `requirements-dev.txt` and
`.pre-commit-config.yaml` files. Contributor checks remain opt-in and do not
become runtime or packaging dependencies.

The CI increment adds `.github/workflows/tests.yml` for configuration parsing,
source compilation, and the hardware-free unittest suite. It intentionally
does not package the Windows executable or require vendor hardware.

The release-layout increment adds `verify_release.ps1` and calls it from the
Windows build script. This catches incomplete one-folder distributions before
they are copied or zipped for deployment.

The ZIP packaging increment adds `package_release.ps1`, which verifies the
distribution, reads the application version, and creates a versioned archive
without mixing release output into the source or documentation folders.

The smoke-test increment adds `smoke_test_release.ps1` for an opt-in packaged
GUI startup check. It does not connect to hardware and is not run by the
hardware-free CI job.

The run-model increment moves `RunData` and its over-limit rules into
`domain/run_data.py` and moves CSV parsing into
`infrastructure/csv_run_loader.py`. The root `run_data.py` path remains a
compatibility facade, so existing callers continue to work while the domain
and file-format responsibilities are separated.

The run-persistence increment moves CSV/JSON recording and run filename rules
into `infrastructure/run_persistence.py`. The root `run_persistence.py` path
remains a compatibility facade, and `FileRunRepository` now imports the
infrastructure implementation directly.

The unit-persistence increment moves unit JSON records, numbered-run paths,
and shared replacement/spare normalization into
`infrastructure/unit_persistence.py`. The root `unit_persistence.py` path
remains a compatibility facade, and repository adapters import the new
infrastructure implementation directly.

The COC-export increment moves template lookup, workbook writing, and drawing
preservation into `infrastructure/coc_export.py`. The root `coc_export.py`
path remains a compatibility facade and the existing application-facing
exporter continues to preserve its public API.

The meter-adapter increment moves the integrated OP815 and simulated power
meters into `hardware/power_meter.py`. The root `power_meter.py` path remains
a compatibility facade, while the vendor-specific DLL wrapper remains isolated
in `op815_driver.py`.

The switch-adapter increment moves the OSX-150 PyVISA/SCPI implementation into
`hardware/optical_switch.py`. The root `osx150_driver.py` path remains a
compatibility facade, preserving existing imports while keeping vendor switch
communication inside the hardware package.

The lazy-factory increment removes eager vendor imports from
`hardware/factory.py`. Default OP815 and OSX-150 adapters are now imported only
when the factory creates a hardware object, improving hardware-free startup and
keeping dependency failures close to the operation that needs the dependency.

The dialog-composition increment applies the same boundary to Live IL and Red
Light. Their default hardware factories now come from `HardwareFactory`, while
tests and workstation-specific configurations can continue to inject a
factory callable directly.

The worker-placement increment moves `MeasurementWorker` into
`application/measurement_worker.py`. The root `measurement_worker.py` remains
a compatibility facade, while `HardwareRunController` and new application code
use the package-owned implementation directly.

The reference-controller increment reuses `LiveILReadingController` for the
main-window Calculate Reference workflow. The setup screen retains its
progress dialog and preflight device check, while thread creation, worker
signals, reference commands, and meter cleanup now use the same controller
lifecycle as Live IL.

The run-start increment keeps operator prompts and widget updates in
`ilm_app.py`, while `application/run_start.py` owns channel-plan normalization
and `HardwareRunRequest` preparation. Hardware adapter preflight remains
separate from worker execution, so future run-start changes can be tested
without opening a Qt window.

For the remainder of this refactor phase, one scoped step remains: perform a
final architecture audit and clean release validation.
