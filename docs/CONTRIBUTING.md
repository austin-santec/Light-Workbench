# Contributing to Light Workbench

## Before starting

Review `docs/README.md`, `PROGRAM_DESIGN.md`, and the specialist document for
the area being changed. Inspect existing tests and preserve uncommitted user
work; do not reset, delete, or overwrite unrelated changes.

## For every change

1. State the intended behavior and affected layer.
2. Make the smallest coherent change.
3. Keep vendor-specific details in adapters.
4. Add a regression test or explain why testing is not practical.
5. Update documentation if the public workflow or architecture changes.
6. Run the required checks from `TESTING_AND_RELEASE.md`.

## Guidance for AI-assisted changes

An AI assistant working on this project should:

- Read the relevant Markdown files in `docs/` before editing.
- Inspect the current source and tests rather than relying only on summaries.
- Treat existing uncommitted changes as user-owned.
- Avoid broad rewrites when an incremental extraction is possible.
- Avoid changing hardware behavior without a fake-device test and an explicit
  hardware smoke-test note.
- Report assumptions, changed files, tests run, and any remaining manual steps.
- Do not rebuild or replace the executable unless requested or required by the
  task.

## Review questions

- Does this belong in UI, application, domain, or infrastructure code?
- Could this work with an OPM and separate laser?
- Does it preserve existing run-file compatibility?
- Is cleanup safe if the user closes the window or stops a run?
- Is the behavior covered without requiring connected hardware?
- Does the change need a version, README, or release-package update?

