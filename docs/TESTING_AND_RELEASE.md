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

### Manual hardware smoke tests

Required before a release that changes driver behavior, worker lifecycle, or
measurement timing. Verify the ILM, switch, driver, VISA resource ownership,
reference calculation, start/stop, and clean close behavior.

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
- Smoke-test the packaged executable separately from running the source.

## Generated files

`build/`, `dist/`, `__pycache__/`, packaged ZIP files, and local production run
data are generated artifacts. They should not be treated as source modules or
used as the location for architecture decisions.

## Release checklist

- Version updated in `app_info.py` when appropriate.
- Tests pass.
- Build succeeds.
- Packaged executable starts on a clean target machine.
- Dependency check is included.
- README and installation instructions are current.
- No production measurements or machine-specific paths are packaged.
- Release notes describe behavior changes and migration concerns.

`build_windows.ps1` calls `verify_release.ps1` automatically after copying the
support files. The verifier checks the executable, installation guide,
dependency checker, operator guide, and PyInstaller `_internal` directory.

`package_release.ps1` repeats that verification, reads the version from
`app_info.py`, and creates `releases\LightWorkbench-v<version>.zip`. It does
not build the executable; run the build script first.

`smoke_test_release.ps1` is an optional Windows GUI startup check. It verifies
the distribution, starts the packaged executable without connecting to
hardware, confirms that it remains alive through startup, and then closes it.
Run it before packaging when a clean-machine or release smoke test is needed.
