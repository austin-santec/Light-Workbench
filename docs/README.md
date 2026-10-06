# Light Workbench Project Documentation

This folder is the design and contribution guide for Light Workbench. It is
intended for developers and AI assistants making changes to the project.

The root [`README.md`](../README.md) is the user-facing project overview. It
covers the current application workflow, deployment requirements, and operator
features. This file focuses on architecture, coding practices, testing, and
how to choose the other documents in this folder.

The root [`Requirements.md`](../Requirements.md) maps the draft OSX insertion-loss
requirements workbook to the current implementation, known gaps, decisions,
and proposed delivery milestones.
For a shorter personal task list, use
[`REQUIREMENTS_CHECKLIST.md`](REQUIREMENTS_CHECKLIST.md), which groups every
requirement into completed, partial, and not-yet-implemented work.

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

- [`SUPPORT_LOGGING.md`](SUPPORT_LOGGING.md) documents always-on local
  engineering logs, redaction, rotation, support bundles, and audit-trail
  limitations.

Model-specific quality criteria are defined in `domain/limit_profiles.py`,
stored through `infrastructure/limit_profile_repository.py`, and edited from
the session-only `Edit > Admin Mode...` / `Edit > Admin Config...` workflow.
New run JSON files snapshot the criteria so historical analysis does not change
when an administrator updates a future profile.

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
performs a final wavelength verification immediately before `ReadPower`; an
unsupported or actual-wavelength mismatch blocks the diagnostic sample. Raw
index/count convention differences are retained as trace warnings.

Final COC output is prepared from persisted run data rather than the visible
table. The operator selects a front-panel count, a base run, and optionally one
compatible replacement/retest run. Export is blocked for missing, invalid, or
formally failing values; the generated workbook uses the appropriate bundled
45- or 48-channel OSX-150 template and removes rows beyond the selected count.

The normal window includes a compact Connected hardware panel and a
`Connect Hardware...` split/menu button in the top header. The main action
connects everything required for a run; menu actions connect or disconnect
measurement hardware and the optical switch independently. Connections persist
between workflows and exclusive leases prevent simultaneous control. The panel
displays each device's transient connection state, manufacturer/model, and serial
when available. Hardware
identity is represented by vendor-neutral `DeviceInfo` models and selected by
an adapter-owned capability registry; an unverified or unknown switch model is
reported clearly and is not treated as an OSX-100/OSX-150-compatible device.

`Help > Support Logs` exposes the always-on local engineering log folder,
status, path copy, and explicit support-bundle export. Support logging uses a
bounded background queue and is isolated from measurement and persistence
behavior. Read `SUPPORT_LOGGING.md` before changing event fields or retention.

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
