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

Persistent-connection tests must verify partial connection success, duplicate
session prevention, exclusive lease conflicts, release without disconnect,
single-thread native calls, laser-safe shutdown, and application-close cleanup.

Extra-channel coverage must remain hardware-free. Verify that missing admin
configuration defaults to SCPI; SCPI extras use the exact finite configured
range, call only `set_channel()`, retain returned physical ports separately,
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
firmware, including `CLOSe?` physical-port results and failure handling. For
direct physical-port routing, additionally verify TCP/2323 framing and
termination on both supported models/firmware families, capture actual success
and error responses, confirm whether an approved readback exists, test the
operator-confirmed unverified path, and prove that returning to a normal
channel uses `CLOSe` and its existing `CLOSe?` verification.

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
- Treat every file in `infrastructure/database/sql_migrations/` as a required
  immutable runtime resource. `ilm_app.spec` discovers the `.sql` files
  dynamically and places them under
  `_internal/infrastructure/database/sql_migrations/` in the one-folder build.
- Smoke-test the packaged executable separately from running the source.

## Generated files

`build/`, `dist/`, `__pycache__/`, packaged ZIP files, and local production run
data are generated artifacts. They should not be treated as source modules or
used as the location for architecture decisions.

## Release checklist

- Version updated in `config/app_info.py` when appropriate.
- Support logging tests cover JSONL validity, date/size rollover, compression,
  indefinite retention, over-size warnings, redaction, bounded queues, fallback writing,
  trace fan-out, bundles, and UI dialogs without using real hardware.
- Tests pass.
- Production Start Run preflight tests cover normal-operator field blocking,
  channel-mode validation, reference authorization, the Admin metadata-only
  exception, and no-file/no-hardware-side-effect failures.
- Build succeeds.
- Packaged executable starts on a clean target machine.
- Dependency check is included.
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

`package_release.ps1` repeats that verification, reads the version from
`config\app_info.py`, and creates `releases\LightWorkbench-v<version>.zip`. It does
not build the executable; run the build script first.

`smoke_test_release.ps1` is an optional Windows GUI startup check. It verifies
the distribution, starts the packaged executable without connecting to
hardware, confirms that it remains alive through startup, and then closes it.
Run it before packaging when a clean-machine or release smoke test is needed.
