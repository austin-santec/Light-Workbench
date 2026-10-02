# Project Layout

This project is a Windows PyQt application with a hardware-free test suite.
The layout is intentionally incremental: the current UI and compatibility
modules remain at the repository root while new responsibilities are placed in
packages.

## Source responsibilities

```text
ilm_app.py, ILMReadLoss.py       Application entry points
application/                     Workflow controllers, persistent hardware ownership/leases, measurement workers, support logging, run-start boundaries, and diagnostic tracing
config/                          Application paths and user-facing release metadata
ui/                              Qt dialogs, status panels, and presentation workers
tools/                           Optional dependency and environment diagnostics
domain/                          Vendor-neutral models and business rules
hardware/                        Hardware contracts, identity, adapters, factories, and sessions
infrastructure/                  File repositories, CSV/unit persistence, support-log writing/bundles, loaders, COC/diagnostic export, queries, and reports
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
- Workflow state and worker ownership: `application/`.
- Persistent connection serialization and exclusive hardware leases:
  `application/hardware_connection.py` and `domain/hardware_connection.py`.
- Calculations, validation, and rules that do not need Qt or hardware:
  `domain/`.
- Vendor-neutral contracts and composed hardware lifecycle: `hardware/`.
- Hardware identity/status presentation: `hardware/device_identity.py` and
  `ui/hardware_status.py`.
- CSV/JSON/XLSX/filesystem and future storage adapters: `infrastructure/`.
- Typed support events: `domain/support_events.py`; queue/correlation ownership:
  `application/support_logging.py`; rotation/redaction/bundles:
  `infrastructure/support_log_writer.py` and `infrastructure/support_bundle.py`;
  support dialogs: `ui/support_logs.py`.
- Compatibility behavior for older callers: existing root-level facades.
- Packaging and deployment behavior: `ilm_app.spec` and the PowerShell release
  scripts, not application runtime modules.
