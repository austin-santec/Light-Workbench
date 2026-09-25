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

## Build rules

- Build using the documented 32-bit Python environment.
- Use `build_windows.ps1` and `ilm_app.spec` rather than ad-hoc PyInstaller
  commands.
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

