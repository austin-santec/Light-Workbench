# Light Workbench Project Documentation

This is the documentation index and authority guide for developers and AI
assistants. The root [`AGENTS.md`](../AGENTS.md) defines the repository-wide
Codex workflow and uses this index to route tasks to their owning documents.

## Authority and evidence

Use each record for the question it can answer:

| Question | Owning record and limits of authority |
| --- | --- |
| What change is approved? | The current approved task and explicitly recorded decisions in the relevant design document or task handoff. A proposal or roadmap entry alone does not establish approval. |
| What was originally requested? | The original [RevB workbook](../temp%20docs/OSX_IL_Test_Software_Requirements_RevB.xlsx), when available, and its traceability in [Requirements.md](../Requirements.md). RevB is original intent, not a description of the current application or automatic approval of every original requirement. |
| How should the system be organized? | [PROGRAM_DESIGN](PROGRAM_DESIGN.md), [PROJECT_LAYOUT](PROJECT_LAYOUT.md), and the specialist architecture documents below. Separate their current-state descriptions from intended architecture and future work. |
| What is implemented? | Relevant source, SQL migrations, and tests establish the implementation at the inspected revision. Specialist documents explain that implementation; an old status label does not override the code or prove acceptance. |
| What has actually been verified? | Recorded automated-test results and manual, hardware, SQL integration, or deployment observations, with their revision, environment, and scope. [TESTING_AND_RELEASE](TESTING_AND_RELEASE.md) defines procedures, not proof that they have been performed. |
| What happened in a task, and what remains? | Task-specific results, test evidence, pending manual checks, known bugs, and open questions in the existing [codex_handoff.md](../codex_handoff.md), cross-referenced to the owning document and source/tests. Older entries require rechecking. |

`Requirements.md` contains outdated statuses and mixed-age implementation
assessments. `REQUIREMENTS_CHECKLIST.md` is a dated derivative checklist, not an
independent current acceptance record. Neither should be interpreted wholesale
as current approved behavior. Their reconciliation is deferred; this index does
not change their requirements or completion claims.
The RevB workbook is currently Git-ignored: it exists in this workspace but
may be unavailable in a fresh checkout.

If records disagree, report the conflict with file references and distinguish
observed implementation from intended behavior. Do not silently select a policy
or rewrite requirements to match code. Seek clarification before work that
depends on an unresolved decision. Treat untested behavior as unverified, even
when its code exists or a milestone says complete.

## Documentation responsibilities

The developer or agent making an approved change maintains the document that
owns the affected subject, and records implementation and verification results
in the existing handoff unless the task limits edits. The user/project owner
approves changes to requirements or design decisions; documentation edits and
passing tests do not supply that approval. Each verification record must say
who or what performed the check and what remains pending.

Use the owning records below instead of copying their behavior descriptions
into this index. Keep this file responsible for navigation, authority, and
documentation responsibilities; keep `AGENTS.md` responsible for agent workflow.

## Documentation map

- [`PROGRAM_DESIGN.md`](PROGRAM_DESIGN.md) — owns application purpose,
  boundaries, layers, workflow rules, and intended architecture.
- [`CODING_STANDARDS.md`](CODING_STANDARDS.md) — owns Python, Qt, threading,
  compatibility, and error-handling conventions.
- [`PROJECT_LAYOUT.md`](PROJECT_LAYOUT.md) — owns source-package responsibilities
  and generated-content locations.
- [`HARDWARE_ARCHITECTURE.md`](HARDWARE_ARCHITECTURE.md) — owns ILM, OPM, laser,
  switch, session, routing, measurement timing, and shutdown boundaries.
- [`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md) — owns units, runs, references,
  replacement/COC rules, persistence, exports, and legacy-file compatibility.
- [`DATABASE_ARCHITECTURE.md`](DATABASE_ARCHITECTURE.md) — owns the SQL
  Server-primary schema for new runs, including unit/switch
  assignments, accepted attempts, replacements, spares, and analysis
  eligibility.
- [`DATABASE_ROADMAP.md`](DATABASE_ROADMAP.md) — owns database milestone
  planning/history, local setup, and rollout exit criteria. Read completed
  milestones as historical records, not fresh verification of a deployment.
  Historical bulk import is intentionally out of scope.
- [`SAMPLE_DATABASE_DATA.md`](SAMPLE_DATABASE_DATA.md) — owns guarded synthetic
  database scenarios, seeding commands, and safety rules.
- [`TESTING_AND_RELEASE.md`](TESTING_AND_RELEASE.md) — owns verification
  procedures, test commands, build,
  packaging, and release checks.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — owns contribution workflow and review
  questions, alongside the agent-specific policy in `AGENTS.md`.
- [`REFACTOR_ROADMAP.md`](REFACTOR_ROADMAP.md) — owns incremental refactor
  history and remaining architecture work. Completed phases are historical;
  remaining phases are plans, not automatically authorized tasks.

- [`SUPPORT_LOGGING.md`](SUPPORT_LOGGING.md) owns always-on local
  engineering logs, redaction, rotation, support bundles, and audit-trail
  limitations.

- [`ILM_DLL_FUNCTION_REFERENCE.md`](ILM_DLL_FUNCTION_REFERENCE.md) owns
  OP815M.dll exports, verified diagnostics, and commands prohibited in
  production measurements.

## Current application and legacy navigation

The desktop entry point is [`ilm_app.py`](../ilm_app.py); release identity is
maintained in [`config/app_info.py`](../config/app_info.py). The database branch
stores new runs in SQL Server; existing CSV/JSON files remain legacy review
inputs. See DATABASE_ARCHITECTURE and DATA_ARCHITECTURE for storage ownership.

- Application layout, connected-hardware controls, Clear Workspace, and
  workflow ownership: [PROGRAM_DESIGN](PROGRAM_DESIGN.md).
- SM/MM selection, session references, remote/local control, diagnostics,
  timing profiles, and extra-channel routing: [HARDWARE_ARCHITECTURE](HARDWARE_ARCHITECTURE.md)
  and [DATA_ARCHITECTURE](DATA_ARCHITECTURE.md).
- Model/mode criteria, latest-measurement selection, replacement analysis, and
  model/mode/capacity-specific COC export: [DATA_ARCHITECTURE](DATA_ARCHITECTURE.md)
  and [DATABASE_ARCHITECTURE](DATABASE_ARCHITECTURE.md).
- Local engineering logs, diagnostic evidence, and support bundles:
  [SUPPORT_LOGGING](SUPPORT_LOGGING.md); measurement diagnostics are also
  described in HARDWARE_ARCHITECTURE.
- Hardware development guidance:
  [.github/agents/santec-test-developer.agent.md](../.github/agents/santec-test-developer.agent.md).

The root [README.md](../README.md) owns the user-facing overview, but currently
mixes desktop, legacy console, and older local-file workflows. Use its section
scope carefully and check current specialist documents/source when it
conflicts with the database workflow. [ILM_READING_GUIDE.html](../ILM_READING_GUIDE.html)
is the operator guide; [README_INSTALL.txt](../README_INSTALL.txt) covers
installation. [`ILMReadLoss.py`](../ILMReadLoss.py) is the legacy console entry
point; its CSV workflow does not define current desktop persistence. These
operator documents are separate from developer policy and are unchanged by
this governance phase.

DATABASE_ROADMAP and REFACTOR_ROADMAP own their respective planning histories,
not a universal current task list. `codex_handoff.md` remains the existing
implementation/issue handoff, with some older claims requiring rechecking.
No new tracker or decision directory is required.

## Required reading before code changes

Follow the startup and specialist routing in [AGENTS.md](../AGENTS.md):

1. Start with this index; before editing, read PROGRAM_DESIGN,
   CODING_STANDARDS, and CONTRIBUTING.
2. Read the specialist documents for the affected area and relevant existing
   handoff entries. Check PROJECT_LAYOUT for file placement and REFACTOR_ROADMAP
   before reorganizing modules.
3. Inspect the relevant source, tests, and worktree. Use the authority rules
   above to report conflicting intent, implementation, or evidence.

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
- Follow TESTING_AND_RELEASE for code tests, compilation, SQL integration, and
  applicable manual/release checks. For documentation-only edits, validate
  references, consistency, and `git diff --check`; report application tests as
  not run because application behavior was unchanged.
- Update README or the relevant document when user behavior or architecture
  changes.
- Rebuild the executable only after source tests pass and the user requests a
  distributable build.
- Record implementation results, exact test outcomes, pending manual/hardware/
  deployment checks, and unresolved issues in the existing handoff unless the
  task restricts edits. Distinguish implemented, inferred, and unverified work;
  do not call a feature fully verified or close it while required checks remain.
