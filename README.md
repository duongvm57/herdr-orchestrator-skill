# Herdr Orchestrator

Herdr Orchestrator is an explicit-only Agent Skill for running repository work
through a Human-led Project Lead and bounded independent Peers on
[Herdr](https://herdr.dev).

For a project-task invocation, the current session is only a short-lived
**Launcher**: it checks the repository and live tooling, prepares role-specific
context, starts a fresh **Project Lead**, and transfers the Human to that Lead.
The Launcher does not remain an invisible orchestration proxy.

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

The Lead receives full project context. A Peer receives its thin role, only
relevant project constraints, and one assignment. Independent judgment uses a
fresh session; correction returns to the same Engineer that owns the write.

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

OpenAI package metadata disables implicit invocation. Other Agent Skills clients
need an equivalent user-only invocation policy; otherwise explicit-only remains
an instruction rather than a mechanical gate.

## Install

You need Git, Python 3, a running Herdr server, a Launcher session inside a
Herdr-managed pane, and every configured harness/model installed and
authenticated. The Launcher's native permission profile must also allow the
Herdr socket and run-evidence writes in the repository's absolute Git common
directory. On current Codex, `workspace-write` needs
`-c sandbox_workspace_write.network_access=true` plus
`--add-dir <absolute-git-common-dir>`; these broaden network and Git-metadata
access, so choose them deliberately and verify both with bounded canaries.

Install into the harness used as Launcher:

```bash
npx skills add duongvm57/herdr-orchestrator --agent codex
```

Leads, Peers, and Supervisors do not need the skill installed; their
role-specific context is sent directly when they are created.

## Set up a repository

From the repository, invoke:

```text
$herdr-orchestrator set up orchestration for this repository
```

Setup first maps every Herdr-supported local harness by executable, version, and
integration state. It then performs deeper model, effort, access, and
native-spawn discovery only for the harnesses you select (or name in the setup
request). It shows exact native choices before asking which recipes are
permitted, then asks about cost, authority, review gates, expensive reversals,
and Human-only decisions and creates two tracked files:

- `.orchestration/herdr-orchestrator.toml` — complete native launch recipes for
  the Lead, a project-defined catalog of reusable Peer recipes, and an optional
  Supervisor;
- `.orchestration/workspace-protocol.md` — repository-specific authority,
  routing, ownership, topology, evidence, escalation, and evolution policy.

The protocol also separates live orchestration language from durable artifact
language. First setup asks the Human to confirm two nonempty values for that
repository; unrelated updates preserve a valid pair unless the Human requests a
change. The package has no language default. Authoritative embedded skill text
and technical literals remain unchanged. Selected Lead and Supervisor recipes
must prove local Herdr control access, and each recipe must prove only its
assigned evidence/commit boundary, before setup writes config.

Review the generated diff. Re-run setup after changing machine, harness, model,
or permission policy. Legacy `routes.toml` and `workers.*.toml` are unsupported.

## Run a task

```text
$herdr-orchestrator implement issue #42 and preserve my uncommitted changes
```

The Launcher validates the project contract and configured live recipes,
inventories existing agents/panes/worktrees/user changes, stores run evidence
outside the checkout, starts a fresh Lead, and transfers focus. Missing
capability stops launch at the exact entry without fallback; existing state is
preserved.

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
Reviewer. The Lead decides the number and dispositions per task and may reuse or
mix approved harness/model recipes. Configured recipes are capabilities, not a
fixed list of Peer types; agent count never substitutes for evidence.

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

Released under the [MIT License](LICENSE).
