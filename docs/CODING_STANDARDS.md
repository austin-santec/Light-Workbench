# Coding Standards

## Python baseline

- Target Python 3.11 32-bit on Windows because the current vendor OP815 DLL is
  32-bit.
- Use standard-library typing, dataclasses, enums, and pathlib where practical.
- New public functions and methods should have type annotations.
- Prefer small functions with one responsibility.
- Keep hardware, UI, and persistence dependencies out of pure domain modules.

## Naming

- Use `snake_case` for modules, functions, and local variables.
- Use `PascalCase` for classes.
- Use `UPPER_SNAKE_CASE` for constants.
- Use explicit names such as `logical_channel`, `physical_port`,
  `reference_power_dbm`, and `insertion_loss_db`.
- Do not use `old_port` or `new_port` in new user-facing code; use the current
  technician terminology, `Current Port` and `Replacement Port`.

## Types and models

- Prefer dataclasses or typed models over unstructured dictionaries for new
  domain data.
- Use enums for finite states such as run state, wavelength, channel mode, and
  measurement status.
- Keep serialized field names stable when backward compatibility matters.
- Validate data at boundaries: UI input, hardware responses, and file loading.

## Errors

- Use specific exceptions for hardware, persistence, configuration, and
  measurement failures.
- Translate service exceptions into user-friendly messages in the controller
  or UI boundary.
- Do not show `QMessageBox` dialogs from low-level drivers or domain services.
- Do not use broad `except Exception` unless it is at a deliberate process or
  worker boundary and the error is logged/reported.
- Cleanup errors must not silently hide the original operation failure.

## Qt and threading

- Never perform blocking hardware calls on the UI thread.
- A worker owns the hardware session it opens and closes.
- Stop signals must wake every worker wait condition.
- Emit terminal worker signals only after hardware cleanup is complete.
- UI objects must not outlive or directly destroy active worker resources.
- Add a regression test for every lifecycle or shutdown bug.

## Comments and documentation

- Comment decisions, hardware quirks, compatibility behavior, and safety rules.
- Avoid comments that merely repeat the code.
- Update docstrings when public behavior changes.
- Update the appropriate document in `docs/` when architecture or conventions
  change.

## Compatibility

- Preserve existing imports temporarily when moving modules; re-export names
  through compatibility facades where practical.
- Do not change CSV, JSON, or COC field meanings without a migration or an
  explicit user-facing change.
- Keep vendor-specific behavior inside adapters.

