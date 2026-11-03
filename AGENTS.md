# Codex workflow for Light Workbench

These instructions apply throughout this repository.

## Start with the task context

- Read [docs/README.md](docs/README.md) for documentation ownership and authority.
  Before editing, also read [PROGRAM_DESIGN](docs/PROGRAM_DESIGN.md),
  [CODING_STANDARDS](docs/CODING_STANDARDS.md), and
  [CONTRIBUTING](docs/CONTRIBUTING.md).
- Inspect the Git worktree, relevant source/tests, and task-related sections of
  [codex_handoff.md](codex_handoff.md). Treat older handoff claims as leads to
  check, not proof of current behavior. Read only the specialists needed below.

## Route specialist work

| Task | Read before changing the area |
| --- | --- |
| Application design, UI, lifecycle, or module placement | [PROGRAM_DESIGN](docs/PROGRAM_DESIGN.md), [PROJECT_LAYOUT](docs/PROJECT_LAYOUT.md); [REFACTOR_ROADMAP](docs/REFACTOR_ROADMAP.md) before reorganizing modules |
| Hardware, commands, firmware, measurement timing | [HARDWARE_ARCHITECTURE](docs/HARDWARE_ARCHITECTURE.md); [ILM_DLL_FUNCTION_REFERENCE](docs/ILM_DLL_FUNCTION_REFERENCE.md) for OP815 DLL work; [Santec agent guidance](.github/agents/santec-test-developer.agent.md) |
| SQL Server, schema, repositories, or deployment | [DATABASE_ARCHITECTURE](docs/DATABASE_ARCHITECTURE.md), relevant [DATABASE_ROADMAP](docs/DATABASE_ROADMAP.md) milestones, [TESTING_AND_RELEASE](docs/TESTING_AND_RELEASE.md) |
| Run data, references, replacements, analysis, or COC | [DATA_ARCHITECTURE](docs/DATA_ARCHITECTURE.md); also [DATABASE_ARCHITECTURE](docs/DATABASE_ARCHITECTURE.md) for database-backed paths |
| Tests, builds, packaging, or releases | [TESTING_AND_RELEASE](docs/TESTING_AND_RELEASE.md) |
| Logging or synthetic database samples | [SUPPORT_LOGGING](docs/SUPPORT_LOGGING.md) or [SAMPLE_DATABASE_DATA](docs/SAMPLE_DATABASE_DATA.md), respectively |

## Keep intent, implementation, and evidence distinct

- The current approved task and explicitly recorded approvals establish intended
  changes. Architecture documents describe design and constraints; distinguish
  sections describing current behavior from targets and proposals.
- The original RevB workbook records original intent, not necessarily current
  approved behavior. [Requirements.md](Requirements.md) contains outdated
  statuses and mixed-age assessments; its content and
  [REQUIREMENTS_CHECKLIST](docs/REQUIREMENTS_CHECKLIST.md) must not be treated
  wholesale as current requirements, implementation evidence, or acceptance.
- Inspect source, migrations, and tests for implemented behavior. Recorded test
  results establish only what was exercised in the stated environment; passing
  fake-hardware tests does not establish real firmware or deployment behavior.
- Report conflicts and uncertain decisions with file references. Do not silently
  resolve them or infer approval from code, a roadmap, or an old handoff. Seek
  clarification before proceeding with work that depends on an unresolved
  decision.

## Preserve the engineering boundaries

- Preserve unrelated work and existing behavior outside the approved scope.
  Prefer the smallest coherent change; avoid unnecessary refactoring.
- Never invent hardware commands, timing assumptions, firmware behavior, channel
  mappings, or unsupported capabilities. Use documented commands and evidence;
  keep unverified assumptions explicit. Use fakes for automated hardware tests.
- Obtain explicit user approval before destructive database changes or changes
  to hardware safety constraints. SQL integration tests use the isolated
  integration database described in TESTING_AND_RELEASE, never live run data.
  Preserve applied migration files and follow the forward-only migration process.
- Follow existing testing and release procedures in TESTING_AND_RELEASE. Report
  checks that could not run and why. For documentation-only changes, validate
  references, consistency, and the Git diff; record application tests as not run.
  Build or package only when the task calls for it; do not edit generated output.

## Leave an accurate handoff

- Report the implemented change, affected files, decisions/approval basis,
  exact checks and results (including failures/skips), manual verification
  performed or pending, unresolved issues, and the next required action.
- For implementation tasks, record a concise, task-specific result in the
  existing [codex_handoff.md](codex_handoff.md) and update the owning specialist
  document when its design or behavior changed, unless the task restricts edits.
  Include a date and commit/revision when available so later sessions can find
  the result without old chat transcripts; do not invent a commit identifier.
- Clearly label implemented facts, inferred behavior, and unverified work.
  Never call a feature fully verified while required hardware, SQL integration,
  manual, or target-deployment testing is pending. Do not mark that work closed.
