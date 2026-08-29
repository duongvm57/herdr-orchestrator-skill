# Assignment and evidence ownership map

This file is a maintenance index, not a runtime route. Phase/version naming is
reserved for the execution plan and release metadata; it is never an
implementation, test, command, or symbol naming scheme. Each contract has one
authoritative home and is disclosed at the action that consumes it:

| Contract | Authoritative source | Runtime trigger |
| --- | --- | --- |
| SLP role, Assignment, and language policy | `skills/herdr-orchestrator/SKILL.md` | Every role handoff |
| Lead launch and handoff | `skills/herdr-orchestrator/references/launcher/task-launch.md` | Task launch |
| Generic pane, agent start, prompt, wait, and read | Release-matched `herdr --skill` and installed binary | Active Herdr operation |
| Lead topology, independent review, correction, Human boundaries, and verdict judgment | `skills/herdr-orchestrator/references/roles/lead.md` | Lead project judgment |
| Supervisor mandate and protocol disclosure | `skills/herdr-orchestrator/references/launcher/supervisor-attachment.md` | Explicit Supervisor attachment |

The Assignment renderer assembles Peer role/profile, bounded protocol context,
and an explicit Peer Assignment without controlling Herdr. Launcher, Lead, and
Supervisor submit and observe through the installed official Herdr skill. Peer
returns an Assignment semantic handback: `COMPLETE`, `REOPEN_REQUEST`,
`DEPENDENCY_REQUEST`, or `BLOCKED`. Supervisor returns a bounded observation,
evidence-backed question, or Human relay. Lead returns a project verdict,
escalation, or Human decision request; durable evidence remains an explicit
task artifact.

## Live-evidence lifecycle

`static/contract` checks are deterministic and do not claim real-agent
behavior. `dogfood` is exploratory real-workflow discovery. A `live-eval` is
a repeatable real-agent run in a fresh consumer project, with explicit graders,
repetitions, and a machine-readable result under ignored `.eval-results/`.

Actionable live failures belong in the project issue tracker. A new uncovered
failure may add a new regression eval. An existing accepted/frozen eval may
change only through `EVAL_REOPEN_REQUEST`; close the issue only after the fix
passes that eval. This
repository deliberately has no checked-in dogfood/failure ledger: historical
run-tree observations remain in Git history or closed issues, not a competing
backlog database.

Use `python3 scripts/run_evals.py --suite tests/evals/orchestration-evals.json`
for the pre-release real-agent suite. The runner materializes the current skill
and the release-matched `herdr --skill` into an isolated consumer project and
records bounded provenance/evidence only; it is never an active orchestration
state store.

## Eval failure discipline

Once a live-eval case has been reviewed and accepted as testing its intended
invariant, its public task, fixture semantics, topology requirement, hard
grader, threshold, repetitions, and positive and negative controls are
**FROZEN** for implementation remediation. A live failure is owned by the
implementation/mechanism by default; an eval disappearing is never an eval
fix, and a static green result is never live-eval evidence.

Classify every observed eval failure as exactly one of the following:

| Classification | Meaning | Allowed remediation |
| --- | --- | --- |
| `IMPLEMENTATION_FAILURE` | The real invariant is not achieved. | Change role instruction, Assignment flow, runtime usage, or orchestration behavior; keep the eval contract unchanged. |
| `EVAL_HARNESS_FAILURE` | Independent evidence shows the invariant achieved, but runner transport, observation, provenance, or cleanup is wrong. | Change harness mechanics only; do not weaken its grader, topology, expected behavior, threshold, or repetitions. |
| `ENVIRONMENT_FAILURE` | Herdr, provider, authentication, quota, dependency, or environment prevents the case from running. | Record `BLOCKED` or `NOT_RUN`; never convert it to `PASS`. |
| `STATIC_TEST_BUG` | A deterministic assertion rejects behavior independently shown correct because of assertion mechanics such as whitespace or path formatting. | Correct that assertion without weakening the invariant. |
| `SPEC_CONFLICT` | The eval contract conflicts with the source-of-truth or rejects semantically valid behavior. | Stop and emit `EVAL_REOPEN_REQUEST`; do not alter the eval in the remediation step. |

For an `IMPLEMENTATION_FAILURE`, production behavior may change while the
frozen eval remains untouched. For an `EVAL_HARNESS_FAILURE`, only harness
mechanics may change. Never patch production and the acceptance logic of the
same failed eval together and use that same pass as proof. Before and after
remediation, inspect `git diff -- scripts/run_evals.py tests/evals
tests/test_live_evals.py`.

Do not delete or rename a case, runner, grader, selector, negative control, or
fixture; lower topology, repetition, required-pass, or hard-fail requirements;
change expected output to match the implementation; special-case the current
implementation; replace real-agent behavior with a mock; trust an agent's
`"passed": true` self-report; or change production prose solely to satisfy a
brittle static assertion. Any such contract change requires the process below.

An `EVAL_REOPEN_REQUEST` must name the failing case and include the exact
observed evidence, tested invariant, independent evidence that the
implementation is correct, evidence that the eval is wrong, the minimal
proposed eval change, and one concrete wrong implementation that must still
FAIL after that change. Wait for Human review before applying it.
