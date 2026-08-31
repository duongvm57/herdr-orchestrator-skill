# Project setup and update

Writes config and protocol; launch only for its included task.

## 1. Preserve and discover

Resolve the canonical root; inventory worktrees and agents/panes. Preserve
unrelated changes and present a diff. Concurrent writers use Human-trusted
sibling slots; an untrusted required slot is a `DEPENDENCY_REQUEST`.

Require `HERDR_ENV=1` and Python 3.11+; prove the Launcher control boundary:

```text
herdr agent list
herdr pane current --current
```

Stop on error. Use Human-confirmed guided rows or v4 TOML; ask missing
protocol decisions. Otherwise show the templates.

Version 3 blocks launch; approved v4 replaces it.

Run discovery once through credential-free doctor output:

```text
python3 <canonical-helper> doctor --project-root <repository-root>
```

Doctor runs bounded parallel read-only probes. Present remediation before any
authorized execution.

Without config, doctor checks every verified kind; repeated `--kind <kind>` may
narrow only this initial probe. It separates Herdr agent support, executable,
runtime binding, and direct integration. Missing optional direct integration
does not mean Herdr lacks agent support. A configured lifecycle authority with
no documented screen fallback must be current.

Use it to omit unavailable harnesses and choose role rows. Then materialize
release bytes once:

```text
python3 <canonical-helper> install-official-skill \
  --project-root <repository-root>
```

The command writes `.agents/skills/herdr/SKILL.md` and, for Claude, its
identical `.claude` mirror. With no `--kind`, it covers every configured
harness; use explicit `--kind` only before config exists. Commit them before
final doctor; use `--replace` only for doctor-reported stale bytes. Final
doctor requires matching configured-harness digests in committed files and blocks a global `herdr` skill
that shadows them. No install/check enters task launch.

Probe access/spawn only when static discovery cannot decide it. Candidate doctor
runs configured bounded model catalogs; missing adapters or projections fail closed.
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

Apply only the selected adapter's verified runtime-binding projection. The
adapter code owns provider-specific subprocess, sandbox, and shell rules; do
not promote them into a project-wide recipe requirement. Never hardcode Herdr
IDs.

Preserve native profile/authentication. Isolation means fresh evidence, not copied
credentials. Use a Human-approved residue-free smoke only when inspection cannot
prove the envelope.

Before serialization, run the complete candidate gate:

```text
python3 <canonical-helper> doctor --project-root <repository-root> \
  --config <candidate-config> --protocol <candidate-protocol>
```

This validates the project and every configured catalog. Do not pass `--kind`.
Show granted root/network capability; live-probe kinds without static rules.

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

Consume passing candidate doctor JSON. After serialization, rerun `python3
<canonical-helper> doctor --project-root <repository-root>` on canonical paths.
Confirm only two intended files changed, no placeholders/credentials appear,
and unrelated state remains. Present the diff and assumptions.

Setup completes when doctor reports `ready: true`, generated skills are
committed, role boundaries hold, the Human reviewed the credential-free diff,
and no probe residue remains. Rerun after changing Herdr, skill, harness,
model, integration, recipe, or permissions—not before each task.
