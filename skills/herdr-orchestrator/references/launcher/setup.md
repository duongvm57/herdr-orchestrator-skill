# Project setup and update

This branch writes only `.orchestration/herdr-orchestrator.toml` and
`.orchestration/workspace-protocol.md`. Launch an agent only for an included
task via the task-launch route.

## 1. Preserve and discover

Resolve repository and absolute Git-common roots. Inventory status, worktrees,
agents/panes, and destinations. Understand and preserve Human-owned or unrelated
changes; present an in-place diff.

Require `HERDR_ENV=1` and Python 3.11+; prove the Launcher control boundary:

```text
herdr agent list
herdr pane current --current
```

Stop on error. Choose configuration mode with one card:

- **Guided setup** (recommended): discover candidates, then ask each profile row.
- **Configure TOML yourself:** accept version-2 TOML from chat or
  `.orchestration/herdr-orchestrator.toml`; otherwise show that path, starter
  from `assets/config.toml`, and role/recipe fields so the Human can create or
  edit it. Strictly parse and validate live tuples, then ask only missing
  protocol decisions.

Use structured user-input when available: one question per card; 2–3 exclusive
choices with explicit labels and impacts; evidence-backed recommendation first;
free-form answer. Otherwise, or if choices do not fit, show every valid answer
as a numbered choice and request its number or free-form. Ask one question and
wait; preserve answers.

In Guided setup, intersect kinds from `herdr agent start --help` with installed,
runnable executables; omit the rest and annotate retained rows using
`herdr integration status`. Build a profile matrix: Lead, optional Supervisor,
and `fast/general/reasoning/coding/architecture/reviewer` Peer capability routes,
plus custom or omit. Each row independently selects its harness; then discover
and choose its model, reasoning/cost, access, and native arguments. Rows may
differ; reuse requires explicit Human choice. Routes describe capability/model
fit; the assignment binds the Peer disposition.

Deep-probe only configured candidates for authentication, native choices,
sandbox, network, and native-spawn control. Targeted Herdr and helper `--help`
remain command authority.

Use `scripts/herdr_orchestrator.py codex-models --output <file>` for Codex and a
bounded native mechanism elsewhere. Consume only compact metadata
from a collision-free temporary directory and remove it after one preference
query. An unavailable catalog remains `unverified` until a documented check or
Human-approved smoke proves the exact model. Obtain remaining decisions for:

- live orchestration and durable artifact languages on first setup, invalid
  existing values, or an explicit language change;
- project risk, review triggers, costly reversals, and minimum verdict proof;
- edit, commit, push, deploy, publish, and other external-effect authority; and
- scope expansion, reserved architecture, budget, and Human-only boundaries.

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

Before smoke or serialization, Codex Lead `workspace-write` args must contain
`--add-dir <absolute-git-common-dir>` and any network flag required for Herdr.
Show that boundary; add the root elsewhere only when authorized. A read-only
Peer uses mailbox cwd without writable project/Git roots; a Supervisor receives
only its notebook root.

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

Run `scripts/herdr_orchestrator.py validate-project` with the repository and
resolved `--git-common-dir`; consume its compact JSON. Recheck every recipe
live. Confirm only the two intended files changed, placeholders and
credential-like values are absent, and unrelated state remains. Present the
scoped diff and unresolved assumptions for Human review.

Setup/update is complete only when schema version 2 parses strictly; both files
exist with every required protocol section and explicit language; shallow
discovery covers the exact live kind set; every selected recipe/model/argument
and role envelope passes live validation; Lead, each Peer, and any Supervisor
have their required Herdr/evidence/Git boundaries; no credential or legacy
schema remains; the Human reviewed the diff; and no agent was launched as an
unintended side effect. No catalog, smoke, or probe residue remains.
