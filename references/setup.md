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

Stop on either error before discovery. Read targeted Herdr and agent-start help,
integration status, and both packaged helpers' `--help`; these interfaces, not
a runtime skill dump, are command authority.

Build one shallow row per live Herdr kind: executable path/presence, bounded
version, and integration state. Mark unknown mappings `unresolved`; retain
unavailable, broken, and outdated rows. Deep-probe only Human-named or
previously configured harnesses.

For each selected harness, discover authentication, native arguments, model and
reasoning choices, sandbox/tool/network controls, and native-spawn control. Use
`scripts/herdr_orchestrator.py codex-models --output <file>` for normalized
Codex data and an analogous bounded native mechanism elsewhere. Put each output
in a collision-free temporary directory outside the repository; consume compact
metadata, run one bounded preference query, then remove it on success or
failure. Raw catalogs never enter conversation or instruction context. An
unavailable catalog stays `unverified` until a documented local check or
Human-approved bounded smoke proves the exact model; marketing names, old
config, and guessed aliases are not evidence.

Show the compact selected-candidate inventory, then obtain Human decisions for:

- Lead reasoning/cost preference and exact Lead recipe;
- reusable Peer recipes with capability, cost, independence, and access
  descriptions;
- optional Supervisor recipe;
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

Read `references/workspace-protocol.md`, copy
`assets/workspace-protocol.md`, and fill all twelve sections with project facts.
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
