# Light Workbench Project Documentation

This folder is the design and contribution guide for Light Workbench. It is
intended for developers and AI assistants making changes to the project.

## Required reading before code changes

Before modifying code, review:

1. `PROGRAM_DESIGN.md` for the application purpose, boundaries, and target
   architecture.
2. `CODING_STANDARDS.md` for implementation and naming conventions.
3. The most relevant specialist document:
   - `HARDWARE_ARCHITECTURE.md` for ILM, OPM, laser, or switch work.
   - `DATA_ARCHITECTURE.md` for runs, units, CSV, JSON, or COC work.
   - `TESTING_AND_RELEASE.md` for tests, packaging, or executable changes.
4. `REFACTOR_ROADMAP.md` before moving or reorganizing modules.

The current source files and automated tests remain the final authority when
these documents do not yet describe an existing behavior. Update the relevant
document when a design decision changes.

## Project principles

- Preserve field-tested behavior unless a change explicitly requests a
  behavior change.
- Keep UI, workflow orchestration, business rules, persistence, and hardware
  communication separate.
- Depend on hardware capabilities and interfaces, not vendor implementations.
- Prefer small, reviewable changes with regression tests.
- Keep generated build output separate from source code.
- Do not place real production run data in the source repository.

## Change checklist

Before submitting a change:

- Read the relevant documents in this folder.
- Identify whether the change affects UI, workflow state, domain logic,
  persistence, hardware, or packaging.
- Add or update tests at the lowest practical layer.
- Preserve backward compatibility for existing run files when possible.
- Run `python -m unittest discover -s tests`.
- Run `python -m py_compile` for changed Python modules.
- Run `git diff --check`.
- Update README or the relevant document when user behavior or architecture
  changes.
- Rebuild the executable only after source tests pass and the user requests a
  distributable build.

