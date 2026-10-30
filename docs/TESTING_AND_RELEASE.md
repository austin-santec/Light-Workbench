# Testing and Release

## Test layers

### Unit tests

Use for calculations, validation, parsing, persistence transformations, and
domain models. These tests should be fast and hardware-free.

### Adapter contract tests

Use the same behavioral checks for simulated and vendor adapters where
possible: connect, read, channel selection, invalid responses, and cleanup.

### Integration tests

Use for Qt worker lifecycle, controller state transitions, run continuation,
file persistence, COC export, and dialog behavior. Use fakes rather than real
hardware.

SQL Server migration and repository tests must use a dedicated disposable
integration database such as `LWBTestDB_Integration`, never the development or
production database. Cover migrations, constraints, transaction rollback, UUID
idempotency, atomic two-wavelength writes, attempt numbering, current-value
views, and database-unavailable behavior. Historical bulk-import tests are not
required by the approved clean-start design.

Database run-load performance instrumentation is hardware-free and must be
tested with fake repositories, factories, clocks, and support loggers. The
read-only benchmark is `tools/benchmark_database_run_load.py`; it must never
target a production database in automated tests or modify schema/run data.
Phase 1 baseline measurements from the host laptop are retained under
`build/database-run-load-baseline-99190-run1.json` and
`build/database-run-load-cold-baseline-99190-run1.json`. Phase 2 uses a bounded
rollback-only read session and bulk related-run measurement retrieval. Repeat
the benchmark on both the host and remote workstation after connection-scope
changes; do not infer remote Wi-Fi performance from host-local timing alone.
Phase 3 enriches the loaded context with the unit run index and related-run
snapshots. Tests must prove that automatic UI publication and repeated status
refreshes issue no repository calls, while an explicit comparison selection
still performs a fresh database load.

Example read-only source-tree benchmark:

```powershell
& 'C:\Users\Austin\AppData\Local\Programs\Python\Python311-32\python.exe' `
    tools\benchmark_database_run_load.py `
    --main-board-serial 99190 `
    --run-number 1 `
    --warmups 1 `
    --iterations 3 `
    --output-json .\build\database-run-load-baseline.json
```

Replace the interpreter path and serial/run values for the workstation being
tested. The command reads the existing per-user database configuration and
does not write to the database. The application logs remain the authoritative
place for packaged-application timing from a target computer.

For a Phase 2 comparison, retain both warm and cold output:

```powershell
python tools\benchmark_database_run_load.py --main-board-serial 99190 --run-number 1 --warmups 2 --iterations 10 --output-json .\build\database-run-load-phase2.json
python tools\benchmark_database_run_load.py --main-board-serial 99190 --run-number 1 --warmups 0 --iterations 5 --output-json .\build\database-run-load-phase2-cold.json
```

Confirm that `database_connection_count` and `database_transaction_count` are
one, `projection_measurement_query_count` is one when related runs exist, and
all measurement/routing/analysis row counts match the Phase 1 baseline. A load
session always rolls back on exit, including successful reads, and must close
before the context is published to the UI.

For Phase 3, also inspect `connection_open` and `read_session_cleanup` in the
workflow stage map and the context/publication stages in
`database.run_load_ui_completed`. Preserve row counts and status/COC results
from Phase 2. On a remote workstation, compare total workflow time with
`connection_open`; a dominant connection stage is an endpoint, authentication,
driver, or network concern rather than evidence that additional repository
queries remain.

Database configuration tests must cover the default Windows Authentication
mode and explicit SQL-password mode. Use synthetic credentials only. Assert
that SQL-password connection strings contain UID/PWD without
`Trusted_Connection`, that Windows strings contain `Trusted_Connection` without
UID/PWD, and that usernames/passwords with ODBC metacharacters are safely
quoted. Support-log and diagnostic tests must prove that passwords, PWD values,
connection strings, and settings representations never appear in output.

Administrator migrations remain Windows-authenticated even when runtime
stations use SQL-password authentication. No test may modify the live SQL
login, `LWBTestDB`, or a workstation's real `database.ini`.

Run the current migration integration tests explicitly on Windows:

```powershell
$env:LWB_TEST_SQL_CONNECTION_STRING = "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost\SQLEXPRESS;DATABASE=LWBTestDB_Integration;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;"
python -m tools.migrate_database --server "localhost\SQLEXPRESS" --database "LWBTestDB_Integration" --trust-server-certificate
python -m unittest tests.test_database_migrations tests.test_database_maintenance
Remove-Item Env:LWB_TEST_SQL_CONNECTION_STRING
```

Without that environment variable, SQL integration cases are skipped while
the hardware-free migration-runner tests still run. Never substitute
`LWBTestDB` or a production database in the integration-test command.

To prove that the integration environment can be recreated and restored, use
the guarded maintenance commands. Both commands reject any database name other
than `LWBTestDB_Integration` and require the name to be repeated explicitly:

```powershell
python -m tools.reset_integration_database --server "localhost\SQLEXPRESS" --database "LWBTestDB_Integration" --confirm-reset "LWBTestDB_Integration" --trust-server-certificate
python -m tools.verify_database_backup --server "localhost\SQLEXPRESS" --database "LWBTestDB_Integration" --confirm-database "LWBTestDB_Integration" --trust-server-certificate
```

The verification command creates a temporary SQL Server backup, restores it as
`LWBTestDB_RestoreVerification`, runs `DBCC CHECKDB`, verifies the migration
and object counts, then removes both the restored database and temporary backup.
Use `--keep-backup` only when an administrator intentionally wants to retain
that integration backup.

COC coverage must include whole-pair multi-run overrides, run/criteria/physical
port compatibility, strict 2.5000 dB publication blocking, optimization
confirmation, 45/48 template selection, row trimming, merged ranges, print
area, source-template immutability, and preservation of source run readings.

Run-purpose coverage must verify the Production default, production-report
filtering, terminal completion policy, purpose display for loaded runs,
continuation/retest preservation, and purpose-neutral COC/replacement-analysis
eligibility. Purpose alone must never create a void record. Legacy file-backed
runs without a purpose remain loadable for historical review.

Iterative replacement coverage must verify assignment isolation, newest
whole-pair selection, current-map matching, unused-extra carry-forward,
replacement chains and verification states, every persisted result state,
deterministic source fingerprints, permanent run voiding, and COC/status
consistency. Migration tests must discover migration 0005, preserve old rows,
convert excluded reasons to valid JSON, and retain legacy analysis statuses.
They must also discover migration 0006, preserve ambiguous historical rows,
and reclassify only unambiguous extra-candidate measurements.

Persistent-connection tests must verify partial connection success, duplicate
session prevention, exclusive lease conflicts, release without disconnect,
single-thread native calls, laser-safe shutdown, and application-close cleanup.

Extra-channel coverage must remain hardware-free. Verify that missing admin
configuration defaults to SCPI; SCPI extras use the exact finite configured
range, call only `set_channel()`, treat the requested configured channel as the
physical candidate identity, confirm the same logical value through `CLOSe?`,
skip accepted continuation rows, hide No More Physical Ports, and never save a
failed route. Preserve CLI coverage for exact `b0 writereg mems.ch <port>\r\n`
formatting, TCP port 2323, raw (not Telnet) transport, bounded reads, separate
initial/idle timeouts, text and binary response classification, binary hex
capture, acknowledgement/error/unverified classification, optional readback, sequential
unknown-capacity probing, retry/discard behavior, and safety-ceiling
enforcement. Both methods must verify routing serialization, part-number
front-panel planning, explicit-write-only persistence, support provenance, and
no automatic method fallback. Fake hardware/sockets must be used; CI must never
require a reachable switch LAN interface.

Extra-channel coverage must also verify the `Extra channels only` mode: a new
OSX-150 database run starts at `N + 1` without front-panel readings, a stopped
or incomplete extra-only run can resume while preserving its saved routing
method, a front-panel run cannot be continued in that mode, OSX-100 is blocked,
SCPI reaches its configured endpoint, CLI starts sequential probing, explicit
Write IL is required for persistence, and the result is supplemental rather
than a false missing-front-panel failure. No normal post-full-pass offer should
be shown for an explicitly selected extra-only run.

### Manual hardware smoke tests

Required before a release that changes driver behavior, worker lifecycle, or
measurement timing. Verify the ILM, switch, driver, VISA resource ownership,
reference calculation, start/stop, and clean close behavior.

For SCPI-mapped extras, verify the configured range on representative OSX-150
firmware, including `CLOSe?` logical-channel confirmation and mismatch failure
handling. Confirm that no test treats its response as a physical port. For
direct physical-port routing, additionally verify TCP/2323 framing and
termination on both supported models/firmware families, capture actual success
and error responses, confirm whether an approved readback exists, test the
operator-confirmed unverified path, and prove that returning to a normal
channel uses `CLOSe` and logical `CLOSe?` confirmation.

## Required checks

```powershell
python -m unittest discover -s tests
python -m py_compile path\to\changed_module.py
git diff --check
```

The full test suite should pass before building an executable.

The repository workflow at `.github/workflows/tests.yml` repeats the
hardware-free test suite and static validation on push and pull request. It
uses Linux CI intentionally because these checks use simulated/fake hardware;
the real OP815 DLL and Windows packaging remain local Windows release steps.

## Optional contributor checks

Install the optional tools with `python -m pip install -r
requirements-dev.txt`. Then run the checks directly or install the local
pre-commit hooks:

```powershell
python -m black --check --config pyproject.toml .
python -m ruff check --config pyproject.toml .
python -m mypy --config-file pyproject.toml
python -m pre_commit install
python -m pre_commit run --all-files
```

These checks are development conveniences only. They are not required on a
machine that only runs the packaged executable.

## Build rules

- Build using the documented 32-bit Python environment.
- Use `build_windows.ps1` and `ilm_app.spec` rather than ad-hoc PyInstaller
  commands.
- Run `verify_release.ps1` against `dist\LightWorkbench` before creating a
  deployment ZIP.
- Use `package_release.ps1` to create the versioned ZIP after the distribution
  has been manually smoke-tested.
- Build from a clean or controlled environment when preparing a release.
- Verify that support files, templates, assets, documentation, and
  `OP815M.dll` are present beside/in the packaged application as intended.
- Require the Microsoft Visual C++ 2015-2022 Redistributable (x86) on build and
  target computers. Do not package application-local `VCRUNTIME140.dll`,
  `MSVCP140.dll`, or `MSVCP140_1.dll`; stale private copies can force ODBC
  Driver 18 to load an incompatible runtime and fail with a generic `HY000`.
- Treat every file in `infrastructure/database/sql_migrations/` as a required
  immutable runtime resource. `ilm_app.spec` discovers the `.sql` files
  dynamically and places them under
  `_internal/infrastructure/database/sql_migrations/` in the one-folder build.
- Smoke-test the packaged executable separately from running the source.

## Generated files

`build/`, `dist/`, `__pycache__/`, packaged ZIP files, explicit exports, and
legacy/sample local run data are generated artifacts. They should not be
treated as source modules or used as the location for architecture decisions.

## Release checklist

- Version updated in `config/app_info.py` when appropriate.
- Support logging tests cover JSONL validity, date/size rollover, compression,
  indefinite retention, over-size warnings, redaction, bounded queues, fallback writing,
  trace fan-out, bundles, and UI dialogs without using real hardware.
- Tests pass.
- Start Run preflight tests cover normal-operator field blocking,
  channel-mode validation, reference authorization, the Admin metadata-only
  exception, and no-file/no-hardware-side-effect failures.
- Build succeeds.
- Packaged executable starts on a clean target machine.
- Dependency check is included.
- `Check Dependencies.cmd` reports a missing system x86 Visual C++ runtime
  before attempting to launch the packaged application.
- README and installation instructions are current.
- No production measurements or machine-specific paths are packaged.
- Release notes describe behavior changes and migration concerns.

`build_windows.ps1` calls `verify_release.ps1` automatically after copying the
support files. The verifier checks the executable, installation guide,
dependency checker, operator guide, PyInstaller `_internal` directory, and COC
templates. It also requires the source and packaged SQL migration directories
to exist, verifies that the source set is nonempty, and compares every packaged
migration with source by filename and SHA-256 hash. Missing, altered, or stale
packaged migrations fail verification; the verifier never repairs a release.
The verifier also rejects application-local Visual C++ runtime DLLs that could
override the supported system x86 redistributable.

`package_release.ps1` repeats that verification, reads the version from
`config\app_info.py`, and creates `releases\LightWorkbench-v<version>.zip`. It does
not build the executable; run the build script first.

`smoke_test_release.ps1` is an optional Windows GUI startup check. It verifies
the distribution, starts the packaged executable without connecting to
hardware, confirms that it remains alive through startup, and then closes it.
Run it before packaging when a clean-machine or release smoke test is needed.
