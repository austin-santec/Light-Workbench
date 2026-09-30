# Light Workbench Project Documentation

This folder is the design and contribution guide for Light Workbench. It is
intended for developers and AI assistants making changes to the project.

The root [`README.md`](../README.md) is the user-facing project overview. It
covers the current application workflow, deployment requirements, and operator
features. This file focuses on architecture, coding practices, testing, and
how to choose the other documents in this folder.

## Documentation map

- [`PROGRAM_DESIGN.md`](PROGRAM_DESIGN.md) — application purpose, boundaries,
  layers, and workflow ownership.
- [`CODING_STANDARDS.md`](CODING_STANDARDS.md) — Python, Qt, threading,
  compatibility, and error-handling conventions.
- [`PROJECT_LAYOUT.md`](PROJECT_LAYOUT.md) — source-package responsibilities
  and generated-content locations.
- [`HARDWARE_ARCHITECTURE.md`](HARDWARE_ARCHITECTURE.md) — ILM, OPM, laser,
  switch, session, and shutdown boundaries.
- [`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md) — units, runs, persistence,
  exports, and compatibility rules.
- [`DATABASE_ARCHITECTURE.md`](DATABASE_ARCHITECTURE.md) — planned local and
  central database design, synchronization, run eligibility, and reporting.
- [`DATABASE_ROADMAP.md`](DATABASE_ROADMAP.md) — staged database milestones,
  tests, rollout steps, and exit criteria.
- [`TESTING_AND_RELEASE.md`](TESTING_AND_RELEASE.md) — test commands, build,
  packaging, and release checks.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — change workflow and review questions.
- [`REFACTOR_ROADMAP.md`](REFACTOR_ROADMAP.md) — incremental refactor history
  and remaining architecture work.

The current release version is maintained in `config/app_info.py`; do not
duplicate it in this index. The current desktop entry point is `ilm_app.py`,
while `ILMReadLoss.py` remains a supported legacy console workflow.

The non-recording `Tools > Power Measurement Diagnostics...` workflow follows
the hardware and lifecycle boundaries described here while displaying
absolute power and exact insertion-loss math. Its manual and monitoring
samples are analyzed separately for temporary repeatability and stability
statistics. Diagnostic history can be explicitly exported as CSV or JSON with
an optional in-memory OP815 hardware trace; this trace is never part of normal
run persistence.

Diagnostic history exports use local-time names in the form
`diagnostic-history-YYYYMMDD-HHMMSS.csv` or `.json`, with deterministic numeric
collision suffixes for automatically suggested names. The OP815 adapter also
performs a final wavelength verification immediately before `ReadPower`; a
failed verification blocks the diagnostic sample.

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
5. `PROJECT_LAYOUT.md` when adding files or deciding where a responsibility
   belongs.

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
