# Project setup and update

This branch writes only `.orchestration/herdr-orchestrator.toml` and
`.orchestration/workspace-protocol.md`. Launch an agent only for an included
task via the task-launch route.

## 1. Preserve and discover

Resolve the canonical repository root. Inventory status, worktrees,
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

Use structured user input when available: one question/card, 2–3 choices,
evidence-backed recommendation first, and free-form. Otherwise number answers.

In Guided setup, intersect helper-verified kinds, `herdr agent start --help`,
and runnable executables; omit the rest and mark Herdr-only kinds unavailable.
Build Lead, optional Supervisor, and applicable Peer capability rows. Each row
independently selects harness, model/cost, access, and native args; the Human
chooses reuse and one fallback. Recipes express capability/model fit; the
Assignment binds Peer disposition.

Deep-probe auth, native choices, access, and spawn control; Herdr/helper
`--help` remains authority. Per selected kind, run `harness-models` in a
temporary directory, consume its compact projection, then remove it. Missing
adapters fail closed; prove each choice with a bounded native check or smoke.
Decide:

- live orchestration and artifact languages on first setup or change;
- project risk, review triggers, costly reversals, and minimum verdict proof;
- edit, commit, push, deploy, publish, and other external-effect authority; and
- scope expansion, reserved architecture, budget, and Human-only boundaries.

Pass unchanged native vectors. Store no credential, secret path/value, or
inferred shared effort. Each option needs an exact adapter rule; a new harness
needs native inspection and approved end-to-end smoke, never a placeholder or
fallback. Approval-gated routes set `approval_required = true`; validation
rejects `--ask-for-approval never`. Recreate the session after any process-
startup policy change.

## 2. Prove each role envelope

Disable native spawning. A Lead needs Herdr reachability and authorized
project/Git access. Each Peer gets only the configured workspace authority. A
read-only Peer does not receive a writable project root; a Supervisor is
governance/project-read-only by role authority unless an explicit observation
artifact root is assigned. Codex Herdr observation needs
`--sandbox workspace-write` and
`--config sandbox_workspace_write.network_access=true`; this grants a broader
filesystem envelope for IPC and must not be described as a technical read-only
ACL.

Apply only the selected adapter's verified runtime-binding projection. Do not
promote one harness's subprocess, home, or shell behavior into a project-wide
recipe requirement. When present, read the selected adapter's concise
`references/harnesses/<kind>-runtime-binding.md` before serializing its native
recipe. Never hardcode Herdr IDs.

Normal production and dogfood launch preserves the user's installed native
harness profile, configuration, and authenticated provider setup. Isolation
means a fresh consumer repository/worktree and clean orchestration/evidence
state, not a fresh harness profile home, credential copy, or login preparation.
A Human/project may request harness-profile isolation as a separate capability;
it is never implied by this orchestration contract.

Validate static controls; use a Human-approved collision-free smoke only when
inspection is insufficient. It may create, read, fsync, and remove one in-scope
probe, must reject out-of-scope writes without residue, and for control roles
runs `herdr agent list` inside the exact native boundary. Do not configure an
unenforceable envelope; state limitations precisely.

Before smoke or serialization, write candidate config and protocol files in a
temporary directory, then run `validate-project --project-root <repository-root>
--config <candidate-config> --protocol <candidate-protocol>`. Kinds without a
static rule need the live probe. Show every
granted root/network capability and grant it to other profiles only when
authorized. A read-only Peer receives its project cwd read-only; a Supervisor
receives only its assigned observation scope and optional artifact root by role
policy; disclose any broader technical sandbox access required for Herdr IPC.

Discovery is complete when the Human saw the kind map and compact inventory;
every selected executable, model, argument, spawn/access boundary is proven;
and every non-discoverable choice was supplied.

## 3. Write schema version 3 and the protocol

Copy `assets/config.toml` and replace every placeholder. Require exactly:

- `version = 3`;
- one `fallback_peer_recipe` naming an exact Peer recipe;
- one `[roles.lead]` and optional `[roles.supervisor]`, each containing only
  `kind`, `args`, and optional boolean `approval_required`; and
- one or more uniquely named `[peer_recipes.<name>]`, each containing exactly
  nonempty `description`, `kind`, `args`, and optional boolean
  `approval_required`.

Peer recipe names identify reusable capabilities, not dispositions. Choose one
general recipe as the fallback for unmatched Assignments; its validated
harness, model, arguments, and authority remain unchanged. `kind` resolves
exactly one adapter without inheritance, translation, or legacy migration.
Set `approval_required = true` only for a route that actually needs an
approval-gated MCP/tool; such a route must not contain `--ask-for-approval
never` and needs a fresh session if the provider fixes approval policy at
startup.

Read `references/launcher/workspace-protocol-authoring.md`, copy
`assets/workspace-protocol-template.md`, and fill all twelve sections with
project facts.
Keep native model/flags in TOML. Make recipe selection, ownership, candidates,
review, evidence, Human decisions, and both languages decidable. Keep the
protocol free of task paths, secrets, and global role manuals.

## 4. Validate and review

Run `python3 <canonical-helper> validate-project --project-root
<repository-root> --config <candidate-config> --protocol <candidate-protocol>`;
consume its compact JSON before serialization. After serialization, rerun the
default canonical-path validation. Recheck every recipe live. Confirm only the
two intended files changed, placeholders and
credential-like values are absent, and unrelated state remains. Present the
scoped diff and unresolved assumptions for Human review.

Setup is complete when version 3 and all protocol sections parse; discovery and
every recipe/envelope pass live validation; role boundaries hold; the Human
reviewed a credential-free diff; no agent or probe residue remains.
