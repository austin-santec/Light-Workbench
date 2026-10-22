# Project Layout

This project is a Windows PyQt application with a hardware-free test suite.
The layout is intentionally incremental: the current UI and compatibility
modules remain at the repository root while new responsibilities are placed in
packages.

## Source responsibilities

```text
ilm_app.py, ILMReadLoss.py       Application entry points
application/                     Workflow controllers, persistent hardware ownership/leases, measurement workers, support logging, run-start preflight/planning boundaries, and diagnostic tracing
config/                          Application paths and user-facing release metadata
ui/                              Qt dialogs, status panels, and presentation workers
tools/                           Optional dependency and environment diagnostics
domain/                          Vendor-neutral models and business rules
hardware/                        Hardware contracts, identity, adapters, factories, and sessions
infrastructure/                  File/SQL persistence, migrations, support logs, loaders, exports, queries, and reports
tests/                            Hardware-free automated tests
```

The root-level driver, persistence, analysis, and UI modules are compatibility
surfaces or legacy entry points. New code should normally be added to the
appropriate package first, then exposed through a root-level facade only when
existing imports need to remain compatible.

## Non-source content

```text
assets/                          Application images and icon
Templates/                       COC templates used by the exporter
docs/                            Architecture and contributor documentation
docs/ILM_DLL_FUNCTION_REFERENCE.md  OP815M.dll command inventory and usage rules
dist/LightWorkbench/             Generated one-folder executable distribution
build/                           Generated PyInstaller intermediates
releases/                        Generated versioned deployment ZIPs
IL-Reads/                        Local production run data
```

`build`, `dist`, `releases`, `__pycache__`, and `IL-Reads` are generated or
machine-specific content. They are not architecture boundaries and should not
be used as source locations. The release scripts keep deployment output in
`dist` and `releases` without mixing it into `docs` or application packages.

## Change placement guide

- UI display, dialogs, and Qt signal wiring: `ilm_app.py` or `ui/`.
- Workflow state, worker ownership, and asynchronous metadata lookup:
  `application/`.
- Persistent connection serialization and exclusive hardware leases:
  `application/hardware_connection.py` and `domain/hardware_connection.py`.
- Calculations, validation, and rules that do not need Qt or hardware:
  `domain/`.
- Accepted reading/retest identity, immutable attempt chains, and current
  measurement projection: `domain/measurement_attempts.py` and
  `domain/run_data.py`.
- Two-part run completion/result assessment and stable status labels:
  `domain/run_status.py`.
- Operator-selected SM/MM OPM/source profiles and legacy classification support:
  `domain/wavelengths.py`. UI and hardware adapters consume the resolved
  configuration rather than duplicating wavelength maps. Hardware identity is
  not used to infer the selected mode.
- OSX-100/OSX-150 part-number parsing and front-panel channel-count resolution:
  `domain/part_numbers.py`. This count remains separate from the switch's
  configured physical-channel count.
- Multi-run COC merging and publication rules: `domain/coc_preparation.py`;
  repository coordination: `application/coc_workflow.py`; operator selection:
  `ui/coc_export_dialog.py`; workbook mechanics: `infrastructure/coc_export.py`.
- Model-specific insertion-loss criteria: `domain/limit_profiles.py`.
- Stable run-purpose values and production-analysis policy:
  `domain/run_purpose.py`.
- Vendor-neutral contracts and composed hardware lifecycle: `hardware/`.
- Hardware identity/status presentation: `hardware/device_identity.py` and
  `ui/hardware_status.py`.
- CSV/JSON/XLSX/filesystem adapters and SQL Server infrastructure:
  `infrastructure/`. Forward-only migration logic is in
  `infrastructure/database/migrations.py`; immutable SQL scripts are in
  `infrastructure/database/sql_migrations/`; guarded integration reset and
  backup/restore operations are in `infrastructure/database/maintenance.py`.
  Database SQL remains private to this layer. Repository contracts, SQL-primary
  orchestration, and read-only reporting live under `application/`; reporting
  records/CSV formatting live under `domain/`; the report dialog lives in
  `ui/database_reports.py`. Database replacement editor state and atomic
  change orchestration live in `application/replacement_persistence_workflow.py`;
  its SQL-aware dialog lives in `ui/database_replacements.py`.
- Administrator criteria INI persistence: `infrastructure/limit_profile_repository.py`.
- Session-only administrator authorization and dialogs:
  `application/admin_session.py` and `ui/admin_config.py`.
- Read-only accepted-reading history presentation and clipboard/export actions:
  `ui/reading_history.py`.
- Reference authorization lifecycle:
  `application/reference_session.py` and `domain/reference.py`; run-local
  reference labels and deduplication: `domain/reference_catalog.py`.
- Typed support events: `domain/support_events.py`; queue/correlation ownership:
  `application/support_logging.py`; rotation/redaction/bundles:
  `infrastructure/support_log_writer.py` and `infrastructure/support_bundle.py`;
  support dialogs: `ui/support_logs.py`.
- Compatibility behavior for older callers: existing root-level facades.
- Packaging and deployment behavior: `ilm_app.spec` and the PowerShell release
  scripts, not application runtime modules. SQL migrations are required runtime
  resources: `ilm_app.spec` discovers every source `.sql` migration through
  `tools/release_resources.py` and packages it under
  `_internal/infrastructure/database/sql_migrations/`. Release verification
  requires the packaged filenames and SHA-256 hashes to match source.
