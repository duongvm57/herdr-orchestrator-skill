# Herdr Skills

This multi-skill repository contains composable Agent Skills for governed
repository work:

| Skill | Purpose | Required? |
|---|---|---|
| `herdr-orchestrator` | Launch a Human-led Project Lead and bounded independent Peers on [Herdr](https://herdr.dev). | Yes, for orchestration |
| `ocr-peer-reviewer` | Let an independent Reviewer use [OpenCodeReview](https://github.com/alibaba/open-code-review) for file selection and rule resolution. | No; direct Peer review remains available |

Herdr Orchestrator is explicit-only. For a project-task invocation, the current
session is only a short-lived **Launcher**: it checks the repository and live
tooling, prepares role-specific context, starts a fresh **Project Lead**, and
transfers the Human to that Lead. The Launcher does not remain an invisible
orchestration proxy.

`ocr-peer-reviewer` is model-invoked only when installed and applicable. Its
absence is not an orchestration error: a Reviewer uses direct exact-candidate
review.

## Orchestration mindset

The goal is not more agents. It is better ownership, independent judgment, and
evidence.

- The **Human** owns intent, cost/risk boundaries, irreversible choices,
  publication, external effects, and project-reserved trade-offs.
- The **Lead** holds macro context, chooses the smallest useful topology,
  assigns one owner per moving scope, resolves dependencies, and issues the
  project verdict.
- A **Peer** owns one bounded outcome. It may confirm, challenge, request a
  dependency, reopen a failed premise, or report `BLOCKED` with evidence.
- A **Supervisor** is optional fresh governance requested by the Human. It
  observes and asks questions without becoming a second Lead or accepting work.

Every agent receives only three ordered instruction layers:

```text
Role Profile → Workspace Protocol → Assignment
```

The Lead receives full project config, protocol, task, and only the
orchestration guidance required by the current branch. A Peer receives its thin
role, only relevant project constraints, and one assignment. Independent
judgment uses a fresh session; correction returns to the same Engineer that owns
the write.

Every moving write scope has one writer. Review binds to an exact stable
candidate: a commit or deterministic base/diff/artifact digest. `done`, an idle
agent, a successful exit, or passing tests are attention signals—not acceptance.

## What constrains a run

Markdown cannot guarantee model obedience.

- Herdr supplies agent and pane lifecycle truth.
- Git and worktrees provide inspectable artifact and workspace identity.
- Harness-native sandbox, approval, and tool controls constrain capabilities.
- Saved context, assignments, reports, and receipts make decisions auditable.
- Fresh review and Human gates test claims prompts cannot enforce.

The skill provides no daemon, queue, retry engine, semantic parentage,
authorization, tamper-proof evidence, or automatic acceptance. Behavioral
confidence requires repeated real runs against the supported harness/model
versions.

OpenAI package metadata marks the skill explicit-only, and its entrypoint
requires explicit Human invocation.

## Install

You need Git, Python 3.11+, a running Herdr server, a Launcher session inside a
Herdr-managed pane, and Codex installed and authenticated. The Launcher's native
permission profile must also allow the Herdr socket and run-evidence writes in
the selected repository's absolute Git common directory. The current setup
supports Codex first; later harnesses require their own normalized authority adapter and
runtime proof.

Use the standard multi-skill installer:

```bash
npx skills@latest add duongvm57/herdr-orchestrator
```

Choose `herdr-orchestrator`, and optionally choose `ocr-peer-reviewer`. The
installer also asks which supported agents receive each selected skill. Install
the orchestrator into the Launcher harness; install the OCR add-on into any
Peer-capable harness where you want OCR-backed review.

Leads, Peers, and Supervisors do not need `herdr-orchestrator` installed; their
role-specific context is sent directly when they are created. A Reviewer that
does not discover `ocr-peer-reviewer` continues with direct review. Every
Reviewer report records the procedure actually used and an OCR status. An
OCR-backed review preserves raw `preview.json` and `rules.json` beside its inbox
report and records both SHA-256 digests.

The optional OCR path also needs the `ocr` CLI. Delegation mode uses the host
Peer for reasoning and needs no OCR-side LLM provider:

```bash
npm install -g @alibaba-group/open-code-review
# or: brew install open-code-review
ocr version
```

See OpenCodeReview's [installation](https://github.com/alibaba/open-code-review/blob/main/pages/src/content/docs/en/installation.md)
and [delegation-mode](https://github.com/alibaba/open-code-review/blob/main/pages/src/content/docs/en/integrations/delegate.md)
documentation for other platforms and current CLI details.

## Set up a repository

From the repository, invoke:

```text
$herdr-orchestrator set up orchestration for this repository
```

The deterministic setup engine discovers Git repositories and the Codex runtime,
normalizes native controls, solves each role's closed-world authority, and asks
only unresolved Human decisions: role profile, commit/architecture authority,
Lead write authority, both communication languages, and exact model/reasoning
bindings. Model options are native inventory facts, not quality or price
rankings.

After static validation and deterministic native allow/deny probes, setup shows
one immutable candidate and its digests. Exact Human acceptance publishes a
complete generation under `.orchestration/setup/generations/` and atomically
activates it through `.orchestration/setup/current.json`. That Activation
Manifest is the only runtime configuration authority. A partial, stale,
tampered, or unaccepted generation cannot launch.

Re-run setup after changing the machine, Codex installation, model, authority,
or policy. Setup is resumable through project-local typed state and never relies
on conversation memory.

## Run a task

```text
$herdr-orchestrator implement issue #42 and preserve my uncommitted changes
```

The Launcher verifies the accepted generation and receipts,
inventories existing agents/panes/worktrees/user changes, stores run evidence
outside the checkout, binds the logical Lead template to exact run paths,
starts a fresh Lead, and transfers focus. Missing capability stops launch
without runtime substitution; existing state is preserved.

Fresh-agent panes are placed by a deterministic helper using only panes
registered to that run. Layout code is not injected; the Lead receives only the
helper and state paths needed to request Peer panes. When the display is full, a
completed run-created Peer pane may be retired after its evidence is durable so
a required fresh replacement can use that space; pre-existing panes and an
Engineer awaiting correction remain protected. Each split or retirement intent
is persisted before Herdr mutates panes, allowing deterministic crash recovery
and rejecting unexplained pane disappearance.

After handoff, work with the Lead. A tiny task may need zero or one Peer.
Architecture-sensitive work may use a fresh Architect, one Engineer, and a fresh
Reviewer. The Lead decides the number and dispositions per task, then selects a
compatible accepted role envelope: `engineer` for bounded project mutation or
`reviewer` for project-read/evidence-write work. Runtime binding compiles exact
workspace, Git-common, evidence, and notebook paths per Assignment. No match
fails closed and returns to Human-approved setup.

## Request a Supervisor

A configured Supervisor is never started automatically:

```text
$herdr-orchestrator attach a Supervisor to run <run-id> and Lead <lead-name>
```

Refocus an installed Launcher session before invoking that command; the fresh
Lead does not need or invoke the skill.

The Launcher binds a fresh project-read-only Supervisor to exact Lead/project/run
identities. It observes evidence, asks open questions, and relays exact Human
decisions. It never creates Peers, edits project code, or issues a project
verdict.

## Evidence and verdicts

Run evidence is stored outside the checkout at:

```text
<git-common-dir>/herdr-orchestrator/runs/<run-id>/
```

This evidence is local and untracked: it does not follow a clone and is absent
from backups that capture only tracked content. Exact tasks and context may be
sensitive, so protect, retain, export, or remove each run under project policy.
`launcher-handoff.md` transfers ledger ownership from Launcher to Lead; it is
not a general filesystem lock.

It records intended context, delivery receipts, assignments, Peer reports,
stable candidates, verification, review, Human decision requests, Supervisor
observations, and the Lead verdict. Each Peer returns its full report through an
exclusive writable file boundary; terminal snapshots are only status/debug
signals. These records are assertions to compare with Herdr, Git, the
filesystem, and raw command results—not proof by themselves.

```text
Engineer proves writes
→ Reviewer falsifies the exact candidate when required
→ Lead inspects the complete evidence chain and issues the project verdict
→ Human resolves owner-only decisions
```

## Update project policy

```text
$herdr-orchestrator update this repository's orchestration protocol
```

A Supervisor observation remains evidence. It becomes policy only through an
explicit update invocation and a Human-reviewed tracked diff.

## License

Herdr Orchestrator and the repository-maintained support code are released
under the [MIT License](LICENSE). The adapted `ocr-peer-reviewer` skill is
released under [Apache-2.0](skills/ocr-peer-reviewer/LICENSE); its upstream
attribution and modification notice are in
[skills/ocr-peer-reviewer/NOTICE](skills/ocr-peer-reviewer/NOTICE).
