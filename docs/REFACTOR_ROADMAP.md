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

Status: in progress.

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

Status: in progress.

- Move insertion-loss, reference, replacement, comparison, and timing logic
  into domain services.
- Move CSV/JSON/unit/COC operations behind repository/export interfaces.
- Keep file-format conversion at the infrastructure boundary.

## Phase 4 — Hardware composition

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

- Add schema versions and migration functions.
- Evaluate SQLite for multi-run analysis while preserving CSV export.
- Add query/report services for operator, timing, limit, and repeatability
  analysis.

## Phase 6 — Tooling and release quality

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
