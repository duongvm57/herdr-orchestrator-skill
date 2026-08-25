# Project setup and update

This branch writes only `.orchestration/herdr-orchestrator.toml` and
`.orchestration/workspace-protocol.md`. Launch an agent only for an included
task via the task-launch route.

## 1. Preserve and discover

Resolve repository and Git-common roots. Inventory status, worktrees,
agents/panes, and destinations. Understand and preserve Human-owned or unrelated
changes; present an in-place diff.

Require `HERDR_ENV=1` and Python 3.11+; prove the Launcher control boundary:

```text
herdr agent list
herdr pane current --current
```

Stop on error. Choose configuration mode with one card:

- **Guided setup** (recommended): discover candidates, then ask each profile row.
- **Configure TOML yourself:** accept version-3 TOML from chat or
  `.orchestration/herdr-orchestrator.toml`; otherwise show that path, starter
  from `assets/config.toml`, and role/recipe fields so the Human can create or
  edit it. Strictly parse and validate live tuples, then ask only missing
  protocol decisions.

Use structured user-input when available: one question per card; 2–3 exclusive
choices with explicit labels/impacts; evidence-backed recommendation first;
free-form answer. Otherwise show every valid answer as a numbered choice and
request its number or free-form. Ask one question and wait; preserve answers.

In Guided setup, read verified kinds from the helper's `harness-models --help`;
intersect kinds with `herdr agent start --help` and runnable executables, and
omit the rest. Mark Herdr-only kinds unavailable and annotate retained rows using
`herdr integration status`. Build a profile matrix: Lead, optional Supervisor,
and `fast/general/reasoning/coding/architecture/reviewer` Peer capability routes,
plus custom or omit. Each row independently selects its harness; then discover
and choose its model, reasoning/cost, access, and native arguments. Rows may
differ; the Human chooses reuse and one fallback recipe. Routes describe
capability/model fit; the assignment binds the Peer disposition.

Deep-probe configured candidates for auth, native choices, access, and spawn
control. Targeted Herdr and helper `--help` remain command authority.

Run `scripts/herdr_orchestrator.py harness-models --kind <kind> --project-root
<repository-root> --output <file>` per selected kind in a temporary directory;
consume its compact projection, then remove it. OMP projects its authenticated-
provider catalog. Pi projects only effective native `enabledModels` scope and
stops if absent or stale. Missing adapters fail closed;
prove each choice with a bounded native check or approved smoke. Decide:

- live orchestration and artifact languages on first setup or change;
- project risk, review triggers, costly reversals, and minimum verdict proof;
- edit, commit, push, deploy, publish, and other external-effect authority; and
- scope expansion, reserved architecture, budget, and Human-only boundaries.

Pass choices as unchanged native argument vectors. Store no credential, secret
path/value, or inferred shared effort vocabulary. Every option needs a strict
rule in its exact harness adapter. A new harness requires native inspection and
an approved end-to-end smoke; create no placeholder, passthrough, or fallback.

## 2. Prove each role envelope

Disable native spawning. A Lead needs Herdr reachability and authorized
project/Git access. Each Peer gets only the configured workspace authority. A
read-only Peer does not receive a writable project root; a Supervisor is
project-read-only unless an explicit observation artifact root is assigned.
Check shared recipes separately per role.

Validate static controls; use a Human-approved collision-free smoke only when
inspection is insufficient. It may create, read, fsync, and remove one in-scope
probe, must reject out-of-scope writes without residue, and for control roles
runs `herdr agent list` inside the exact native boundary. Do not configure an
unenforceable envelope; state limitations precisely.

Before smoke or serialization, run `validate-project --git-common-dir`; the
selected Lead adapter checks its static evidence-root rules. Kinds without a
static rule need the live probe. Show every granted root/network capability and
grant it to other profiles only when authorized. A read-only Peer receives its
project cwd read-only; a Supervisor receives only its assigned observation scope
and optional artifact root.

Discovery is complete when the Human saw the kind map and compact inventory;
every selected executable, model, argument, spawn/access boundary is proven;
and every non-discoverable choice was supplied.

## 3. Write schema version 3 and the protocol

Copy `assets/config.toml` and replace every placeholder. Require exactly:

- `version = 3`;
- one `fallback_peer_recipe` naming an exact Peer recipe;
- one `[roles.lead]` and optional `[roles.supervisor]`, each containing only
  `kind` and `args`; and
- one or more uniquely named `[peer_recipes.<name>]`, each containing exactly
  nonempty `description`, `kind`, and `args`.

Peer recipe names identify reusable capabilities, not dispositions. Choose one
general recipe as the fallback for unmatched Assignments; its validated
harness, model, arguments, and authority remain unchanged. `kind` resolves
exactly one adapter without inheritance, translation, or legacy migration.

Read `references/launcher/workspace-protocol-authoring.md`, copy
`assets/workspace-protocol-template.md`, and fill all twelve sections with
project facts.
Keep native model/flags in TOML. Make recipe selection, ownership, candidates,
review, evidence, Human decisions, and both languages decidable. Keep the
protocol free of task paths, secrets, and global role manuals.

## 4. Validate and review

Run `scripts/herdr_orchestrator.py validate-project` with the repository and
resolved `--git-common-dir`; consume its compact JSON. Recheck every recipe
live. Confirm only the two intended files changed, placeholders and
credential-like values are absent, and unrelated state remains. Present the
scoped diff and unresolved assumptions for Human review.

Setup is complete when version 3 and all protocol sections parse; discovery and
every recipe/envelope pass live validation; role boundaries hold; the Human
reviewed a credential-free diff; no agent launched; and no probe residue remains.
