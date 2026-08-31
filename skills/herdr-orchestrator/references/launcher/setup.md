# Project setup and update

This branch writes `.orchestration/herdr-orchestrator.toml` and
`.orchestration/workspace-protocol.md`. Launch an agent only for an included task.

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
- **Configure TOML yourself:** accept version-4 TOML from chat or
  `.orchestration/herdr-orchestrator.toml`; otherwise show that path, starter
  from `assets/config.toml`, and role/recipe fields so the Human can create or
  edit it. Strictly parse and validate live tuples, then ask only missing
  protocol decisions.

Version 3 blocks launch; Human-approved v4 replaces it.

Use structured input when available; otherwise number answers.

In Guided setup, intersect helper-verified kinds, `herdr agent start --help`,
and runnable executables; omit the rest and mark Herdr-only kinds unavailable.
Build Lead, optional Supervisor, and applicable Peer capability rows. Each row
independently selects harness, model/cost, access, and native args; the Human
chooses reuse and one fallback. Recipes express capability/model fit; the
Assignment binds Peer disposition.

Probe auth, native choices, access, and spawn control; Herdr/helper
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
artifact root is assigned. An adapter-specific Herdr IPC requirement may need a
broader technical sandbox envelope; disclose it precisely without describing
it as a role-authority ACL.

Apply only the selected adapter's verified runtime-binding projection. Do not
promote one harness's subprocess, home, or shell behavior into a project-wide
recipe requirement. When present, read the selected adapter's concise
`references/harnesses/<kind>-runtime-binding.md` before serializing its native
recipe. Never hardcode Herdr IDs.

Production preserves the installed native harness profile and authentication.
Isolation means a fresh consumer checkout/evidence state, not copied credentials
or an implied new profile. Use a Human-approved, residue-free smoke only when
inspection cannot prove the selected envelope.

Before serialization, validate temporary candidate config/protocol with
`validate-project --project-root <repository-root> --config <candidate-config>
--protocol <candidate-protocol>`. Show every granted root/network capability;
kinds without a static rule need the live probe.

## 3. Write schema version 4 and the protocol

Copy `assets/config.toml` and replace every placeholder. Require exactly:

- `version = 4` and `assessment_after_cycles = 2` unless Human approves a
  different temporary convergence-assessment guard;
- one `[roles.lead]` and optional `[roles.supervisor]`, each containing
  `kind`, `args`, `cost_class`, and optional boolean `approval_required`; and
- one or more uniquely named `[peer_recipes.<name>]`, each containing exactly
  nonempty `description`, `kind`, `args`, `cost_class = "standard"|"elevated"`,
  and optional boolean `approval_required`; and
- `[routing.engineer]`, `[routing.reviewer]`, `[routing.architect]`, and
  `[routing.default]`, each with an exact `default_recipe` and nonempty
  `allowed_recipes` from the peer recipe names.

Peer recipe names identify reusable capabilities, not dispositions. Custom
dispositions use the explicit `default` route; there is no hidden fallback.
`kind` resolves
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

Setup is complete when version 4 and all protocol sections parse; discovery and
every recipe/envelope pass live validation; role boundaries hold; the Human
reviewed a credential-free diff; no agent or probe residue remains.
