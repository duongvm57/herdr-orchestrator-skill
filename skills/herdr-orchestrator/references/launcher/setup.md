# Project setup and update

This branch produces exactly two tracked project files:
`.orchestration/herdr-orchestrator.toml` and
`.orchestration/workspace-protocol.md`. It does not launch an agent unless the
same explicit invocation also contains a task, which is handled afterward by
the task-launch route.

## 1. Preserve and discover

Resolve the repository root and absolute Git common directory. Inventory status,
worktrees, agents/panes, and both destinations. Preserve Human-owned files and
unrelated changes; understand them and present an in-place diff.

Require `HERDR_ENV=1` and Python 3.11+, then prove the Launcher's live control
boundary first:

```text
herdr agent list
herdr pane current --current
```

Stop on either error. Use `herdr agent start --help` for supported kinds and
command lookup plus a bounded version probe for installed, runnable executables.
Inventory only their intersection. Omit unsupported and absent executables;
annotate retained rows with `herdr integration status`, including broken,
outdated, or `unresolved` mappings. Targeted Herdr and helper `--help` remain
command authority.

Show the inventory, then use the harness's structured user-input tool when
available. Ask one unresolved decision at a time: 2–3 mutually exclusive choices,
an evidence-backed recommended choice first, concise impacts, and a free-form
answer. Sequence dependent recipe choices and skip supplied answers. Never
replace available cards with combined prose or invent choices.

If unavailable or all valid choices cannot fit, use ordinary chat with every
numbered choice plus a free-form answer; ask one question and wait for its answer.

Select each recipe's harness from installed rows first; then discover and choose its model,
reasoning/cost, access, and native arguments. Configure the Lead,
one or more basic Peer capability profiles, then the optional Supervisor. Reuse
a deep inventory when profiles share a harness. Deep-probe only selected or
previously configured harnesses for authentication, native choices, sandbox,
network, and native-spawn control.

For Codex use `scripts/herdr_orchestrator.py codex-models --output <file>`; use
an analogous bounded native mechanism elsewhere. Consume only compact metadata
from a collision-free temporary directory and remove it after one preference
query. An unavailable catalog remains `unverified` until a documented check or
Human-approved smoke proves the exact model. Obtain remaining decisions for:

- live orchestration and durable artifact languages on first setup, invalid
  existing values, or an explicit language change;
- project risk, review triggers, costly reversals, and minimum verdict proof;
- edit, commit, push, deploy, publish, and other external-effect authority; and
- scope expansion, reserved architecture, budget, and Human-only boundaries.

On first setup the Human explicitly confirms both language values. On unrelated
updates, preserve an existing valid pair unless the Human requests a change.

Translate choices into native argument vectors passed unchanged. Store no
credential, secret path/value, or inferred shared effort vocabulary.
Every option must have a strict helper schema for its exact kind; an unsupported
option requires a package update, never arbitrary passthrough or fallback.

## 2. Prove each role envelope

Disable native spawning for every recipe. A Lead needs Herdr reachability,
bounded run-evidence writes, and only authorized project/Git access. Each Peer
gets one exclusive lossless report boundary and otherwise only its owned
workspace. A read-only Peer uses mailbox cwd with project/Git outside writable
roots; a Supervisor is project-read-only and notebook-write-only. Shared
harness/model choices still need separate role checks.

Validate static controls; use a Human-approved collision-free smoke only when
inspection is insufficient. It may create, read, fsync, and remove one in-scope
probe, must reject out-of-scope writes without residue, and for control roles
runs `herdr agent list` inside the exact native boundary. Do not configure an
unenforceable envelope; state limitations precisely.

For current Codex `workspace-write`, allow native network access when required
for the Herdr Unix socket. Add the absolute Git common directory only to a Lead
or commit-capable Peer whose authority requires it, and show that broadened
boundary. A project-read-only Peer instead uses mailbox cwd with no checkout or
common-directory writable root; a Supervisor receives only each exact notebook
root.

Discovery is complete when the shallow kind map and compact deep inventory were
shown; every selected kind, executable, native argument, model, spawn control,
Herdr boundary, evidence boundary, and applicable Git boundary is proven; and
the Human supplied every non-discoverable choice.

## 3. Write schema version 2 and the protocol

Copy `assets/config.toml` and replace every placeholder. Require exactly:

- `version = 2`;
- one `[roles.lead]` and optional `[roles.supervisor]`, each containing only
  `kind` and `args`; and
- one or more uniquely named `[peer_recipes.<name>]`, each containing exactly
  nonempty `description`, `kind`, and `args`.

Peer recipe names identify reusable capabilities, not dispositions. There is no
fallback, inheritance, profile lookup, adapter, or legacy-schema migration.

Read `references/launcher/workspace-protocol-authoring.md`, copy
`assets/workspace-protocol-template.md`, and fill all twelve sections with
project facts.
Keep native model/flags in TOML. Make recipe selection, one-writer ownership,
stable-candidate identity, independent-review triggers, evidence, Human-only
decisions, and both communication languages decidable. The protocol contains
project tactics, not task-specific file lists, secrets, or global role manuals.

## 4. Validate and review

Run `scripts/herdr_orchestrator.py validate-project` on the repository and
consume its compact JSON result. Recheck every final recipe against live local
capabilities. Confirm only the two intended files changed,
all placeholders and credential-like values are absent, and unrelated state is
preserved. Present the scoped diff and unresolved assumptions for Human review.

Setup/update is complete only when schema version 2 parses strictly; both files
exist with every required protocol section and explicit language; shallow
discovery covers the exact live kind set; every selected recipe/model/argument
and role envelope passes live validation; Lead, each Peer, and any Supervisor
have their required Herdr/evidence/Git boundaries; no credential or legacy
schema remains; the Human reviewed the diff; and no agent was launched as an
unintended side effect. No catalog, smoke, or probe residue remains.
